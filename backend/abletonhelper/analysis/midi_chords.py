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


def select_tracks(path: Path, track_filter: str | None = None,
                  all_tracks: bool = False) -> tuple[list[int], str]:
    """Decide which track indices to read. Returns (indices, why).

    Rules, in order:
      all_tracks=True      -> every track with notes
      track_filter given   -> tracks whose name contains it
      exactly one has notes-> that one, whatever it is called
      a name looks chordy  -> those
      otherwise            -> everything, and say so

    The single-track case is the common one: a chord track exported on
    its own needs no name matching, and insisting on one would break a
    file whose only track is called "Track 1".
    """
    tracks = list_tracks(path)
    with_notes = [t for t in tracks if t["notes"] > 0]
    if not with_notes:
        return [], "no track contains notes"

    if all_tracks:
        return [t["index"] for t in with_notes], "reading every track (forced)"

    if track_filter:
        hit = [t["index"] for t in with_notes
               if track_filter.lower() in (t["name"] or "").lower()]
        if hit:
            return hit, f"name contains {track_filter!r}"
        return ([t["index"] for t in with_notes],
                f"no track name contains {track_filter!r}; read everything")

    if len(with_notes) == 1:
        t = with_notes[0]
        return [t["index"]], f"only track with notes ({t['name'] or 'unnamed'!r})"

    hit = [t["index"] for t in with_notes
           if any(h in (t["name"] or "").lower() for h in ("chord", "harmony", "prog"))]
    if hit:
        return hit, "track name looks like a chord track"

    return ([t["index"] for t in with_notes],
            "several tracks with notes and none named for chords; "
            "read everything -- pass track_filter to narrow")


def _read_notes(path: Path, keep: list[int] | None = None
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
    for idx, track in enumerate(mid.tracks):
        if keep is not None and idx not in keep:
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
                     all_tracks: bool = False,
                     min_span: float = 0.25,
                     prefer_flats: bool = False) -> list[ChordSpan]:
    """Extract chord spans from a MIDI file.

    Segments at note boundaries rather than on a fixed grid, so a block
    chord's span is exactly the notes' own start and end -- no
    quantisation error at the change points.
    """
    path = Path(path)
    keep, _why = select_tracks(path, track_filter, all_tracks)
    if not keep:
        return []
    notes, length = _read_notes(path, keep)
    if not notes:
        return []

    # Every onset and offset is a potential chord change; nothing else is.
    edges = sorted({n.start for n in notes} | {n.end for n in notes})

    spans: list[ChordSpan] = []
    for a, b in zip(edges[:-1], edges[1:]):
        if b <= a:
            continue
        mid_point = (a + b) / 2.0
        sounding = [n.pitch for n in notes if n.start <= mid_point < n.end]
        if not sounding:
            continue
        label = name_chord(sounding, prefer_flats)
        if label == "N":
            continue
        if spans and spans[-1].chord == label and abs(spans[-1].end - a) < 1e-6:
            spans[-1] = ChordSpan(spans[-1].start, b, label, 0.99)
        else:
            spans.append(ChordSpan(a, b, label, 0.99))

    # Absorb flickers: a voicing changing mid-chord (a passing note, a
    # released doubling) can name one very short span. Fold it back.
    merged: list[ChordSpan] = []
    for span in spans:
        if merged and (span.end - span.start) < min_span:
            merged[-1] = ChordSpan(merged[-1].start, span.end,
                                   merged[-1].chord, 0.99)
        elif merged and merged[-1].chord == span.chord:
            merged[-1] = ChordSpan(merged[-1].start, span.end, span.chord, 0.99)
        else:
            merged.append(span)
    return merged


def explain(path: str | Path, track_filter: str | None = None,
            all_tracks: bool = False) -> str:
    """Why these tracks were chosen -- for the CLI and for debugging."""
    keep, why = select_tracks(Path(path), track_filter, all_tracks)
    names = {t["index"]: t["name"] for t in list_tracks(path)}
    picked = ", ".join(f"[{i}] {names.get(i) or 'unnamed'}" for i in keep) or "none"
    return f"{why}  ->  {picked}"


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
