"""Authored song sections.

Detected sections are the weakest signal this project produces. When the
arrangement is marked by hand -- in Logic, or in a text file -- that is
ground truth and it replaces detection entirely.

Two sources, tried in order:

1. **Marker events inside the MIDI file** you already supply for chords.
   Standard MIDI carries `marker` and `cue_point` meta events, and Logic
   writes its arrangement markers into them on export. Zero extra work
   when it does.
2. **A plain text file** in the song folder. Always available, whatever
   the DAW decides to export.

       0:00   Intro
       0:08   Verse 1
       0:24   Chorus
       1:12   Bridge
       2:04   Outro

   Times may be `mm:ss`, `mm:ss.cc`, or plain seconds. Separator is
   whitespace, a comma, a tab or `=`; `#` starts a comment.
"""

from __future__ import annotations

import re
from pathlib import Path

from .base import CANONICAL_LABELS, Section

# Written form -> canonical label. Longest match wins, so "prechorus"
# is not swallowed by "chorus".
_ALIASES: list[tuple[str, str]] = [
    ("pre-chorus", "prechorus"), ("prechorus", "prechorus"), ("pre chorus", "prechorus"),
    ("chorus", "chorus"), ("hook", "chorus"), ("refrain", "chorus"),
    ("verse", "verse"),
    ("intro", "intro"), ("count-in", "intro"), ("countin", "intro"), ("count in", "intro"),
    ("outro", "outro"), ("ending", "outro"), ("coda", "outro"),
    ("bridge", "bridge"), ("middle 8", "bridge"), ("middle8", "bridge"),
    ("breakdown", "breakdown"), ("break", "breakdown"), ("drop", "breakdown"),
    ("solo", "solo"),
    ("instrumental", "instrumental"), ("inst", "instrumental"), ("interlude", "instrumental"),
    ("silence", "silence"), ("tacet", "silence"),
]

_TIME_RE = re.compile(r"^(?:(\d{1,3}):)?(\d{1,3})(?:[.:](\d{1,3}))?$")
_SPLIT_RE = re.compile(r"[\s,\t=]+")


def canonical_label(name: str) -> str:
    """Map an authored marker name onto a canonical label."""
    low = name.strip().lower()
    for written, canon in sorted(_ALIASES, key=lambda p: -len(p[0])):
        if written in low:
            return canon
    return low if low in CANONICAL_LABELS else "unknown"


def _parse_time(token: str) -> float | None:
    m = _TIME_RE.match(token.strip())
    if not m:
        return None
    minutes, seconds, frac = m.group(1), m.group(2), m.group(3)
    total = (int(minutes) * 60 if minutes else 0) + int(seconds)
    if frac:
        total += int(frac) / (100.0 if len(frac) == 2 else
                              1000.0 if len(frac) == 3 else 10.0)
    return float(total)


def _close(marks: list[tuple[float, str]], duration: float | None) -> list[Section]:
    """Turn (time, name) marks into closed spans."""
    marks = sorted(marks, key=lambda p: p[0])
    out: list[Section] = []
    for i, (start, name) in enumerate(marks):
        if i + 1 < len(marks):
            end = marks[i + 1][0]
        elif duration is not None and duration > start:
            end = duration
        else:
            continue            # trailing mark with no length; drop it
        if end <= start:
            continue
        out.append(Section(start=start, end=end, label=canonical_label(name),
                           confidence=1.0, name=name.strip()))
    return out


def parse_sections_file(path: str | Path,
                        duration: float | None = None) -> list[Section]:
    raw = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    marks: list[tuple[float, str]] = []
    for line in raw.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = _SPLIT_RE.split(line, maxsplit=1)
        if len(parts) < 2:
            continue
        t = _parse_time(parts[0])
        if t is None:
            continue
        marks.append((t, parts[1].strip()))
    return _close(marks, duration)


def sections_from_midi_markers(path: str | Path,
                               duration: float | None = None) -> list[Section]:
    """Read marker / cue_point meta events out of a MIDI file."""
    import mido

    mid = mido.MidiFile(str(path))
    tpb = mid.ticks_per_beat or 480

    tempo_changes: list[tuple[int, int]] = []
    for track in mid.tracks:
        t = 0
        for msg in track:
            t += msg.time
            if msg.type == "set_tempo":
                tempo_changes.append((t, msg.tempo))
    tempo_changes.sort()
    if not tempo_changes or tempo_changes[0][0] != 0:
        tempo_changes.insert(0, (0, 500000))

    def tick_to_sec(tick: int) -> float:
        secs, last_tick, last_tempo = 0.0, 0, tempo_changes[0][1]
        for change_tick, tempo in tempo_changes:
            if change_tick >= tick:
                break
            secs += (change_tick - last_tick) / tpb * (last_tempo / 1e6)
            last_tick, last_tempo = change_tick, tempo
        secs += (tick - last_tick) / tpb * (last_tempo / 1e6)
        return secs

    marks: list[tuple[float, str]] = []
    for track in mid.tracks:
        t = 0
        for msg in track:
            t += msg.time
            if msg.type in ("marker", "cue_marker"):
                text = getattr(msg, "text", "") or ""
                if text.strip():
                    marks.append((tick_to_sec(t), text))
    return _close(marks, duration)


def find_sections_file(folder: Path) -> Path | None:
    for name in ("sections.txt", "sections.csv", "arrangement.txt", "markers.txt"):
        p = folder / name
        if p.exists():
            return p
    hits = [f for f in sorted(folder.iterdir())
            if f.is_file() and "section" in f.name.lower()
            and f.suffix.lower() in (".txt", ".csv", ".tsv")]
    return hits[0] if len(hits) == 1 else None
