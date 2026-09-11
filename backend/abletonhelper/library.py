"""Song library: discovering stems on disk and running analysis."""

from __future__ import annotations

import uuid
from pathlib import Path

from .analysis.base import AnalysisInput, AnalysisResult
from .analysis import registry
from .config import settings
from .db import Song, session
from .jobs import Progress

AUDIO_EXT = {".wav", ".aif", ".aiff", ".flac", ".mp3", ".m4a", ".ogg"}

# Filename fragments -> canonical stem role. First match wins.
STEM_HINTS = [
    ("drum", "drums"), ("kick", "drums"), ("snare", "drums"), ("perc", "drums"),
    ("bass", "bass"),
    ("vox", "vocals"), ("vocal", "vocals"), ("lead v", "vocals"),
    ("gtr", "guitar"), ("guitar", "guitar"),
    ("key", "keys"), ("piano", "keys"), ("synth", "keys"), ("pad", "keys"),
    ("click", "click"), ("cue", "cue"), ("mix", "mix"),
]


def classify_stem(filename: str) -> str:
    low = filename.lower()
    for frag, role in STEM_HINTS:
        if frag in low:
            return role
    return "other"


def scan_song_folder(folder: Path) -> dict[str, str]:
    """Map role -> path for every audio file in a song folder.

    Roles collide (two guitar stems); later files get a numeric suffix so
    nothing is silently dropped.
    """
    stems: dict[str, str] = {}
    for f in sorted(folder.iterdir()):
        if not f.is_file() or f.suffix.lower() not in AUDIO_EXT:
            continue
        role = classify_stem(f.name)
        key, n = role, 2
        while key in stems:
            key, n = f"{role}{n}", n + 1
        stems[key] = str(f.relative_to(folder))
    return stems


def import_folder(folder: Path, name: str | None = None) -> Song:
    folder = folder.resolve()
    if not folder.is_dir():
        raise NotADirectoryError(folder)
    stems = scan_song_folder(folder)
    if not stems:
        raise ValueError(f"no audio files found in {folder}")

    import json
    song = Song(
        id=str(uuid.uuid4()),
        name=name or folder.name,
        folder=str(folder),
        stems_json=json.dumps(stems),
    )
    with session() as s:
        s.add(song)
        s.commit()
    return song


def analysis_input(song: Song) -> AnalysisInput:
    folder = Path(song.folder)
    stems = {k: folder / v for k, v in song.stems.items()}
    # Analyse the mix when there is one, else the densest stem available.
    mix = stems.get("mix")
    if mix is None:
        for pref in ("other", "keys", "guitar", "bass", "drums"):
            if pref in stems:
                mix = stems[pref]
                break
    return AnalysisInput(mix=mix, stems=stems)


def analyze_song(song_id: str, backend: str | None = None,
                 progress: Progress | None = None) -> dict:
    with session() as s:
        song = s.get(Song, song_id)
        if song is None:
            raise KeyError(f"no such song {song_id}")

    if progress:
        progress(0.05, "loading audio")

    inp = analysis_input(song)
    result: AnalysisResult = registry.analyze(
        inp, backend=backend or settings.analysis_backend
    )

    if progress:
        progress(0.9, "writing analysis")

    out = settings.analysis_cache / f"{song_id}.json"
    result.write_json(out)

    with session() as s:
        song = s.get(Song, song_id)
        song.tempo = result.tempo
        song.key = result.key
        song.duration = result.duration
        song.analysis_path = str(out)
        s.commit()

    return {
        "song_id": song_id,
        "tempo": result.tempo,
        "key": result.key,
        "duration": result.duration,
        "n_sections": len(result.sections),
        "n_chords": len(result.chords),
        "backend": result.backend,
        "analysis_path": str(out),
    }


def load_analysis(song: Song) -> AnalysisResult | None:
    if not song.analysis_path:
        return None
    p = Path(song.analysis_path)
    return AnalysisResult.read_json(p) if p.exists() else None
