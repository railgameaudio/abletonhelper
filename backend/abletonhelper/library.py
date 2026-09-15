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
MIDI_EXT = {".mid", ".midi"}

# A MIDI file whose name contains one of these is taken as the chord
# source. Logic exports every track into one file, so we also filter by
# track name inside it -- see midi_chords.chords_from_midi.
CHORD_MIDI_HINTS = ("chord", "harmony", "prog")

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


def find_chord_midi(folder: Path) -> Path | None:
    """The MIDI file to take chords from, if the song folder has one.

    Prefers a file named for chords; falls back to a lone MIDI file.
    """
    midis = [f for f in sorted(folder.iterdir())
             if f.is_file() and f.suffix.lower() in MIDI_EXT]
    if not midis:
        return None
    for f in midis:
        if any(h in f.name.lower() for h in CHORD_MIDI_HINTS):
            return f
    return midis[0] if len(midis) == 1 else None


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

    # An authored chord track beats anything detected from audio.
    chord_midi = find_chord_midi(Path(song.folder))
    if chord_midi is not None:
        if progress:
            progress(0.85, f"reading chords from {chord_midi.name}")
        try:
            from .analysis.midi_chords import chords_from_midi, explain
            # Track selection is automatic: a lone chord track needs no
            # name match, and a multi-track export is narrowed by name.
            authored = chords_from_midi(chord_midi)
            if authored:
                result.meta["chords_track_choice"] = explain(chord_midi)
                result.chords = authored
                result.meta["chords_source"] = str(chord_midi)
                result.meta["chords_authored"] = True
        except Exception as e:
            result.meta["chord_midi_error"] = f"{type(e).__name__}: {e}"

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
