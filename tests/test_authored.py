"""Authored inputs beat detected ones. These are the ground-truth paths."""

import mido
import pytest
from mido import Message, MetaMessage, MidiFile, MidiTrack

from abletonhelper.analysis.lyrics import find_lrc, parse_lrc
from abletonhelper.analysis.sections import (canonical_label, find_sections_file,
                                             parse_sections_file,
                                             sections_from_midi_markers)


# --- sections from a text file -----------------------------------------

@pytest.mark.parametrize("written,canon", [
    ("Intro", "intro"), ("Verse 1", "verse"), ("Verse 2", "verse"),
    ("Chorus", "chorus"), ("Chorus 2 (big)", "chorus"),
    ("Pre-Chorus", "prechorus"), ("PreChorus", "prechorus"),
    ("Middle 8", "bridge"), ("Bridge", "bridge"),
    ("Gtr Solo", "solo"), ("Outro", "outro"), ("Coda", "outro"),
    ("Count-in", "intro"), ("Drop", "breakdown"),
    ("Nonsense", "unknown"),
])
def test_label_aliases(written, canon):
    assert canonical_label(written) == canon


def test_prechorus_not_swallowed_by_chorus():
    """Longest alias wins, or every pre-chorus becomes a chorus."""
    assert canonical_label("Pre-Chorus 1") == "prechorus"


def _write(tmp_path, text, name="sections.txt"):
    p = tmp_path / name
    p.write_text(text)
    return p


def test_parse_mmss(tmp_path):
    p = _write(tmp_path, "0:00 Intro\n0:08 Verse 1\n0:24 Chorus\n")
    secs = parse_sections_file(p, duration=40.0)
    assert [s.label for s in secs] == ["intro", "verse", "chorus"]
    assert [s.start for s in secs] == [0.0, 8.0, 24.0]
    assert secs[-1].end == 40.0


def test_keeps_authored_name_for_display(tmp_path):
    p = _write(tmp_path, "0:00 Intro\n0:08 Verse 1\n")
    secs = parse_sections_file(p, duration=20.0)
    assert secs[1].label == "verse"      # canonical, for logic
    assert secs[1].name == "Verse 1"     # authored, for display
    assert secs[1].display == "Verse 1"


def test_authored_sections_are_full_confidence(tmp_path):
    p = _write(tmp_path, "0:00 Intro\n0:08 Chorus\n")
    assert all(s.confidence == 1.0 for s in parse_sections_file(p, 20.0))


def test_plain_seconds_and_fractions(tmp_path):
    p = _write(tmp_path, "0 Intro\n8.5 Verse\n24.25 Chorus\n")
    secs = parse_sections_file(p, duration=40.0)
    assert [s.start for s in secs] == [0.0, 8.5, 24.25]


def test_separators_and_comments(tmp_path):
    p = _write(tmp_path,
               "# my arrangement\n"
               "0:00,Intro\n"
               "0:08\tVerse 1\n"
               "0:24 = Chorus\n"
               "\n"
               "0:40 Outro   # the long one\n")
    secs = parse_sections_file(p, duration=60.0)
    assert [s.label for s in secs] == ["intro", "verse", "chorus", "outro"]


def test_out_of_order_marks_are_sorted(tmp_path):
    p = _write(tmp_path, "0:24 Chorus\n0:00 Intro\n0:08 Verse\n")
    secs = parse_sections_file(p, duration=40.0)
    assert [s.start for s in secs] == [0.0, 8.0, 24.0]


def test_trailing_mark_dropped_without_duration(tmp_path):
    p = _write(tmp_path, "0:00 Intro\n0:08 Outro\n")
    assert len(parse_sections_file(p, duration=None)) == 1


def test_find_sections_file(tmp_path):
    (tmp_path / "sections.txt").write_text("0:00 Intro\n")
    assert find_sections_file(tmp_path).name == "sections.txt"


# --- sections from MIDI markers ----------------------------------------

@pytest.fixture
def marked_midi(tmp_path):
    mid = MidiFile(ticks_per_beat=480)
    tr = MidiTrack(); mid.tracks.append(tr)
    tr.append(MetaMessage("set_tempo", tempo=mido.bpm2tempo(120), time=0))
    # 120 BPM -> 480 ticks = 0.5 s
    tr.append(MetaMessage("marker", text="Intro", time=0))
    tr.append(MetaMessage("marker", text="Verse 1", time=480 * 8))    # 4 s
    tr.append(MetaMessage("marker", text="Chorus", time=480 * 8))     # 8 s
    p = tmp_path / "marked.mid"
    mid.save(p)
    return p


def test_midi_markers(marked_midi):
    secs = sections_from_midi_markers(marked_midi, duration=12.0)
    assert [s.label for s in secs] == ["intro", "verse", "chorus"]
    assert [s.start for s in secs] == [0.0, 4.0, 8.0]
    assert secs[-1].end == 12.0


def test_midi_without_markers_returns_nothing(tmp_path):
    mid = MidiFile(ticks_per_beat=480)
    tr = MidiTrack(); mid.tracks.append(tr)
    tr.append(Message("note_on", note=60, velocity=80, time=0))
    tr.append(Message("note_off", note=60, velocity=0, time=480))
    p = tmp_path / "plain.mid"
    mid.save(p)
    assert sections_from_midi_markers(p, duration=2.0) == []


# --- lyrics -------------------------------------------------------------

LRC = """[ar:The Band]
[ti:A Song]
[00:00.00]
[00:12.50]First line here
[00:15.30]Second line
[00:18.00][01:02.40]A line that comes back
"""


def test_parse_lrc(tmp_path):
    p = tmp_path / "song.lrc"
    p.write_text(LRC)
    doc = parse_lrc(p, duration=70.0)
    assert doc.meta["ar"] == "The Band"
    assert doc.meta["ti"] == "A Song"
    assert [l.text for l in doc.lines] == [
        "First line here", "Second line",
        "A line that comes back", "A line that comes back"]
    assert doc.lines[0].start == pytest.approx(12.5)
    assert doc.lines[0].end == pytest.approx(15.3)
    assert doc.lines[-1].start == pytest.approx(62.4)
    assert doc.lines[-1].end == 70.0


def test_lrc_offset_shifts_timing(tmp_path):
    p = tmp_path / "off.lrc"
    p.write_text("[offset:+500]\n[00:10.00]Line\n[00:12.00]Next\n")
    doc = parse_lrc(p, duration=20.0)
    assert doc.lines[0].start == pytest.approx(9.5)


def test_lrc_millisecond_precision(tmp_path):
    p = tmp_path / "ms.lrc"
    p.write_text("[00:10.250]Line\n[00:12.500]Next\n")
    doc = parse_lrc(p, duration=20.0)
    assert doc.lines[0].start == pytest.approx(10.25)


def test_enhanced_lrc_word_tags_stripped(tmp_path):
    p = tmp_path / "enh.lrc"
    p.write_text("[00:10.00]<00:10.00>Hello <00:10.50>world\n[00:12.00]Next\n")
    doc = parse_lrc(p, duration=20.0)
    assert doc.lines[0].text == "Hello world"


def test_line_at(tmp_path):
    p = tmp_path / "song.lrc"
    p.write_text(LRC)
    doc = parse_lrc(p, duration=70.0)
    assert doc.line_at(13.0).text == "First line here"
    assert doc.line_at(0.5) is None


def test_find_lrc(tmp_path):
    (tmp_path / "MySong.lrc").write_text("[00:01.00]x\n")
    assert find_lrc(tmp_path).name == "MySong.lrc"
