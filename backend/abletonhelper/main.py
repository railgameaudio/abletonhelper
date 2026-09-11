from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import jobs, library
from .analysis import registry
from .als import inspect as als_inspect
from .config import settings
from .db import SetList, SetListItem, Song, init_db, session

app = FastAPI(title="abletonhelper", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    init_db()


# ---------------------------------------------------------------- health

@app.get("/api/health")
def health() -> dict:
    tpl = settings.template_path
    return {
        "ok": True,
        "single_user": settings.single_user,
        "backends": registry.status(),
        "template": {
            "path": str(tpl),
            "present": tpl.exists(),
        },
    }


# ----------------------------------------------------------------- songs

class ImportRequest(BaseModel):
    folder: str
    name: str | None = None


def _song_dict(s: Song) -> dict:
    return {
        "id": s.id, "name": s.name, "folder": s.folder, "stems": s.stems,
        "tempo": s.tempo, "key": s.key, "duration": s.duration,
        "analyzed": bool(s.analysis_path),
    }


@app.get("/api/songs")
def list_songs() -> list[dict]:
    with session() as s:
        return [_song_dict(x) for x in s.query(Song).order_by(Song.created_at).all()]


@app.post("/api/songs/import")
def import_song(req: ImportRequest) -> dict:
    try:
        song = library.import_folder(Path(req.folder), req.name)
    except (NotADirectoryError, ValueError) as e:
        raise HTTPException(400, str(e))
    return _song_dict(song)


@app.post("/api/songs/scan")
def scan_library() -> dict:
    """Import every subfolder of songs_dir that isn't already known."""
    root = settings.songs_dir
    if not root.is_dir():
        raise HTTPException(400, f"{root} is not a directory")
    added = []
    with session() as s:
        known = {x.folder for x in s.query(Song).all()}
    for sub in sorted(p for p in root.iterdir() if p.is_dir()):
        if str(sub.resolve()) in known:
            continue
        try:
            added.append(_song_dict(library.import_folder(sub)))
        except ValueError:
            continue        # folder with no audio; skip quietly
    return {"added": added, "count": len(added)}


@app.get("/api/songs/{song_id}")
def get_song(song_id: str) -> dict:
    with session() as s:
        song = s.get(Song, song_id)
        if song is None:
            raise HTTPException(404, "no such song")
        d = _song_dict(song)
    analysis = library.load_analysis(song)
    d["analysis"] = analysis.to_dict() if analysis else None
    return d


@app.delete("/api/songs/{song_id}")
def delete_song(song_id: str) -> dict:
    with session() as s:
        song = s.get(Song, song_id)
        if song is None:
            raise HTTPException(404, "no such song")
        s.delete(song)
        s.commit()
    return {"deleted": song_id}


# -------------------------------------------------------------- analysis

class AnalyzeRequest(BaseModel):
    backend: str | None = None


@app.post("/api/songs/{song_id}/analyze")
def analyze(song_id: str, req: AnalyzeRequest | None = None) -> dict:
    with session() as s:
        if s.get(Song, song_id) is None:
            raise HTTPException(404, "no such song")
    backend = req.backend if req else None
    job_id = jobs.submit(
        "analyze",
        lambda p: library.analyze_song(song_id, backend=backend, progress=p),
        target_id=song_id,
    )
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "no such job")
    return job


# -------------------------------------------------------------- setlists

class SetListRequest(BaseModel):
    name: str
    song_ids: list[str] = []


@app.get("/api/setlists")
def list_setlists() -> list[dict]:
    with session() as s:
        out = []
        for sl in s.query(SetList).order_by(SetList.created_at).all():
            out.append({
                "id": sl.id, "name": sl.name,
                "song_ids": [i.song_id for i in sl.items],
            })
        return out


@app.post("/api/setlists")
def create_setlist(req: SetListRequest) -> dict:
    sl = SetList(id=str(uuid.uuid4()), name=req.name)
    with session() as s:
        s.add(sl)
        for i, sid in enumerate(req.song_ids):
            s.add(SetListItem(id=str(uuid.uuid4()), setlist_id=sl.id,
                              song_id=sid, position=i))
        s.commit()
    return {"id": sl.id, "name": sl.name, "song_ids": req.song_ids}


@app.put("/api/setlists/{setlist_id}")
def update_setlist(setlist_id: str, req: SetListRequest) -> dict:
    with session() as s:
        sl = s.get(SetList, setlist_id)
        if sl is None:
            raise HTTPException(404, "no such setlist")
        sl.name = req.name
        for item in list(sl.items):
            s.delete(item)
        s.flush()
        for i, sid in enumerate(req.song_ids):
            s.add(SetListItem(id=str(uuid.uuid4()), setlist_id=sl.id,
                              song_id=sid, position=i))
        s.commit()
    return {"id": setlist_id, "name": req.name, "song_ids": req.song_ids}


# -------------------------------------------------------------- template

@app.get("/api/template/inspect")
def inspect_template(path: str | None = None) -> dict:
    p = Path(path) if path else settings.template_path
    if not p.exists():
        raise HTTPException(404, f"{p} not found")
    return als_inspect.inspect(p).to_dict()
