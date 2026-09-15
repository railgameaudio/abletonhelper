"""Chords from an authored MIDI file (e.g. exported from Logic).

Detected chords are a guess. A chord track someone actually played is
ground truth, so when a song folder contains a .mid it wins over anything
the audio analyzer produced.

Output is the same `ChordSpan` list the audio path produces, so nothing
downstream needs to know where the chords came from -- only the
confidence differs (authored spans ship at 0.99).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .base import ChordSpan

PITCHES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
FLATS = {"C#": "Db", "D#": "Eb", "F#": "Gb", "G#": "Ab", "A#": "Bb"}

# Interval sets from the root. Order matters only for tie-breaking:
# earlier entries are "simpler" and win when scores are equal.
QUALITIES: list[tuple[str, frozenset[int]]] = [
    ("",        frozenset({0, 4, 7})),          # major
    ("m",       frozenset({0, 3, 7})),
    ("5",       frozenset({0, 7})),             # power chord
    ("dim",     frozenset({0, 3, 6})),
    ("aug",     frozenset({0, 4, 8})),
    ("sus4",    frozenset({0, 5, 7})),
    ("sus2",    frozenset({0, 2, 7})),
    ("6",       frozenset({0, 4, 7, 9})),
    ("m6",      frozenset({0, 3, 7, 9})),
    ("7",       frozenset({0, 4, 7, 10})),
    ("maj7",    frozenset({0, 4, 7, 11})),
    ("m7",      frozenset({0, 3, 7, 10})),
    ("mMaj7",   frozenset({0, 3, 7, 11})),
    ("m7b5",    frozenset({0, 3, 6, 10})),
    ("dim7",    frozenset({0, 3, 6, 9})),
    ("7sus4",   frozenset({0, 5, 7, 10})),
    ("add9",    frozenset({0, 2, 4, 7})),
    ("madd9",   frozenset({0, 2, 3, 7})),
    ("9",       frozenset({0, 2, 4, 7, 10})),
    ("maj9",    frozenset({0, 2, 4, 7, 11})),
    ("m9",      frozenset({0, 2, 3, 7, 10})),
]


def name_chord(pitches: list[int], prefer_flats: bool = False) -> str:
    """Name a set of MIDI note numbers.

    Scores every (root, quality) pair: matched tones earn, missing and
    extra tones cost. The lowest sounding note becomes a slash bass when
    it is not the root.
    """
    if not pitches:
        return "N"
    pcs = frozenset(p % 12 for p in pitches)
    bass_pc = min(pitches) % 12

    best: tuple[float, int, int, str] | None = None
    for root in range(12):
        for order, (suffix, template) in enumerate(QUALITIES):
            shifted = frozenset((i + root) % 12 for i in template)
            matched = len(pcs & shifted)
            missing = len(shifted - pcs)
            extra = len(pcs - shifted)
            score = matched - 1.1 * missing - 0.9 * extra
            if root == bass_pc:
                score += 0.35        # root position is the likelier reading
            # Prefer simpler spellings on a tie: lower order, fewer tones.
            cand = (score, -order, -len(template), suffix)
            if best is None or cand > best:
                best = cand
                best_root, best_suffix = root, suffix

    if best is None or best[0] <= 0:
        return "N"

    def spell(pc: int) -> str:
        n = PITCHES[pc]
        return FLATS.get(n, n) if prefer_flats else n

    label = f"{spell(best_root)}{best_suffix}"
    if bass_pc != best_root:
        label += f"/{spell(bass_pc)}"
    return label


@dataclass
class _Note:
    start: float        # seconds
    end: float
    pitch: int


def _read_notes(path: Path, track_filter: str | None = None
                ) -> tuple[list[_Note], float]:
    """Flatten a MIDI file to absolute-time notes. Returns (notes, length)."""
    import mido

    mid = mido.MidiFile(str(path))
    tpb = mid.ticks_per_beat or 480

    # Build a tempo map first: tick -> seconds needs every set_tempo event.
    tempo_changes: list[tuple[int, int]] = []
    for track in mid.tracks:
        t = 0
        for msg in track:
            t += msg.time
            if msg.type == "set_tempo":
                tempo_changes.append((t, msg.tempo))
    tempo_changes.sort()
    if not tempo_changes or tempo_changes[0][0] != 0:
        tempo_changes.insert(0, (0, 500000))      # MIDI default, 120 BPM

    def tick_to_sec(tick: int) -> float:
        secs, last_tick, last_tempo = 0.0, 0, tempo_changes[0][1]
        for change_tick, tempo in tempo_changes:
            if change_tick >= tick:
                break
            secs += (change_tick - last_tick) / tpb * (last_tempo / 1e6)
            last_tick, last_tempo = change_tick, tempo
        secs += (tick - last_tick) / tpb * (last_tempo / 1e6)
        return secs

    notes: list[_Note] = []
    end_tick = 0
    for track in mid.tracks:
        name = ""
        for msg in track:
            if msg.type == "track_name":
                name = msg.name
                break
        if track_filter and track_filter.lower() not in name.lower():
            continue

        t = 0
        open_notes: dict[int, int] = {}
        for msg in track:
            t += msg.time
            if msg.type == "note_on" and msg.velocity > 0:
                open_notes[msg.note] = t
            elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
                start = open_notes.pop(msg.note, None)
                if start is not None and t > start:
                    notes.append(_Note(tick_to_sec(start), tick_to_sec(t), msg.note))
                    end_tick = max(end_tick, t)

    notes.sort(key=lambda n: (n.start, n.pitch))
    return notes, tick_to_sec(end_tick)


def chords_from_midi(path: str | Path, track_filter: str | None = None,
                     grid_seconds: float = 0.125,
                     min_span: float = 0.4,
                     prefer_flats: bool = False) -> list[ChordSpan]:
    """Extract chord spans from a MIDI file.

    `track_filter` picks tracks whose name contains it (e.g. "chord"),
    which matters because a Logic export often carries every instrument.
    """
    path = Path(path)
    notes, length = _read_notes(path, track_filter)
    if not notes:
        return []

    # Sample the sounding pitch set on a grid, name it, then merge runs.
    spans: list[ChordSpan] = []
    t = 0.0
    while t < length:
        sounding = [n.pitch for n in notes if n.start <= t < n.end]
        label = name_chord(sounding, prefer_flats) if sounding else "N"
        if spans and spans[-1].chord == label:
            spans[-1] = ChordSpan(spans[-1].start, t + grid_seconds, label, 0.99)
        else:
            spans.append(ChordSpan(t, t + grid_seconds, label, 0.99))
        t += grid_seconds

    # Drop grace-note flickers: absorb anything too short into its neighbour.
    merged: list[ChordSpan] = []
    for span in spans:
        if merged and (span.end - span.start) < min_span and span.chord != "N":
            merged[-1] = ChordSpan(merged[-1].start, span.end, merged[-1].chord, 0.99)
        elif merged and merged[-1].chord == span.chord:
            merged[-1] = ChordSpan(merged[-1].start, span.end, span.chord, 0.99)
        else:
            merged.append(span)

    return [s for s in merged if s.chord != "N"]


def list_tracks(path: str | Path) -> list[dict]:
    """Track names and note counts -- so a user can pick the chord track."""
    import mido

    mid = mido.MidiFile(str(path))
    out = []
    for i, track in enumerate(mid.tracks):
        name = ""
        notes = 0
        for msg in track:
            if msg.type == "track_name" and not name:
                name = msg.name
            if msg.type == "note_on" and msg.velocity > 0:
                notes += 1
        out.append({"index": i, "name": name, "notes": notes})
    return out
