import pytest

from abletonhelper.analysis import registry
from abletonhelper.analysis.base import AnalysisInput, AnalysisResult, Section
from abletonhelper.analysis.librosa_backend import LibrosaAnalyzer
from abletonhelper.library import classify_stem


def test_result_json_roundtrip(tmp_path):
    r = AnalysisResult(source="s", duration=10.0, backend="b", backend_version="1")
    r.sections = [Section(0.0, 4.0, "intro", 0.5)]
    p = r.write_json(tmp_path / "a.json")
    back = AnalysisResult.read_json(p)
    assert back.sections[0].label == "intro"
    assert back.sections[0].duration == pytest.approx(4.0)


def test_section_at():
    r = AnalysisResult(source="s", duration=10, backend="b", backend_version="1")
    r.sections = [Section(0, 5, "intro"), Section(5, 10, "verse")]
    assert r.section_at(2).label == "intro"
    assert r.section_at(7).label == "verse"
    assert r.section_at(99) is None


def test_bar_times_falls_back_to_beats():
    r = AnalysisResult(source="s", duration=8, backend="b", backend_version="1")
    r.beats = [0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5]
    assert r.bar_times() == [0, 2.0]


@pytest.mark.parametrize("name,expected", [
    ("01_Kick.wav", "drums"), ("Bass DI.wav", "bass"),
    ("LeadVox.wav", "vocals"), ("Gtr L.wav", "guitar"),
    ("Click.wav", "click"), ("Pad Synth.wav", "keys"),
    ("something.wav", "other"),
])
def test_stem_classification(name, expected):
    assert classify_stem(name) == expected


def test_tempo_from_grid_beats_the_median():
    """Frame quantisation makes the median inter-beat interval wrong.

    Regression guard: gaps alternating 0.488/0.511 average to 0.4998
    (120.05 BPM) but their median is 0.511 (117.4 BPM).
    """
    beats = []
    t = 0.0
    for i in range(80):
        beats.append(t)
        t += 0.488 if i % 2 else 0.511
    bpm = LibrosaAnalyzer._tempo_from_grid(beats, fallback=0.0)
    assert bpm == pytest.approx(120.1, abs=0.5)


def test_librosa_tempo_and_key(click_track):
    r = LibrosaAnalyzer().analyze(AnalysisInput(mix=click_track))
    assert r.tempo == pytest.approx(120.0, abs=1.0)
    assert r.key == "C major"
    assert r.duration == pytest.approx(12.0, abs=0.1)
    assert len(r.beats) > 20


def test_registry_reports_status():
    st = registry.status()
    assert st["librosa"]["available"] is True
    assert "allin1" in st


def test_registry_unknown_backend():
    with pytest.raises(KeyError):
        registry.get("nope")


# --- authored chords from MIDI ------------------------------------------

import mido
from mido import Message, MetaMessage, MidiFile, MidiTrack

from abletonhelper.analysis.midi_chords import (chords_from_midi, list_tracks,
                                                name_chord)

C = 60


@pytest.mark.parametrize("pitches,want", [
    ([C, C + 4, C + 7], "C"),
    ([C, C + 3, C + 7], "Cm"),
    ([C, C + 4, C + 7, C + 11], "Cmaj7"),
    ([C, C + 3, C + 7, C + 10], "Cm7"),
    ([C, C + 4, C + 7, C + 10], "C7"),
    ([C, C + 3, C + 6], "Cdim"),
    ([C, C + 4, C + 8], "Caug"),
    ([C, C + 5, C + 7], "Csus4"),
    ([C, C + 2, C + 7], "Csus2"),
    ([C, C + 4, C + 7, C + 9], "C6"),
    ([C, C + 3, C + 6, C + 10], "Cm7b5"),
    ([C, C + 7], "C5"),
    ([C, C + 2, C + 4, C + 7], "Cadd9"),
    ([], "N"),
])
def test_chord_naming(pitches, want):
    assert name_chord(pitches) == want


def test_inversions_become_slash_chords():
    assert name_chord([C + 4, C + 7, C + 12]) == "C/E"
    assert name_chord([C + 7, C + 12, C + 16]) == "C/G"


def test_root_position_has_no_slash():
    assert name_chord([62, 65, 69]) == "Dm"


def test_flat_spelling():
    assert name_chord([C + 1, C + 5, C + 8], prefer_flats=True) == "Db"
    assert name_chord([C + 1, C + 5, C + 8]) == "C#"


@pytest.fixture
def logic_style_midi(tmp_path):
    """Multi-track export: tempo track, a bass track, a chord track."""
    tpb = 480
    mid = MidiFile(ticks_per_beat=tpb)

    meta = MidiTrack(); mid.tracks.append(meta)
    meta.append(MetaMessage("set_tempo", tempo=mido.bpm2tempo(120), time=0))
    meta.append(MetaMessage("track_name", name="Tempo", time=0))

    bass = MidiTrack(); mid.tracks.append(bass)
    bass.append(MetaMessage("track_name", name="Bass DI", time=0))
    for _ in range(8):
        bass.append(Message("note_on", note=36, velocity=90, time=0))
        bass.append(Message("note_off", note=36, velocity=0, time=tpb * 2))

    ch = MidiTrack(); mid.tracks.append(ch)
    ch.append(MetaMessage("track_name", name="Chords", time=0))
    for notes in ([57, 60, 64, 67], [53, 57, 60, 64],
                  [48, 60, 64, 67], [55, 59, 62, 65]):
        for n in notes:
            ch.append(Message("note_on", note=n, velocity=80, time=0))
        for j, n in enumerate(notes):
            ch.append(Message("note_off", note=n, velocity=0,
                              time=tpb * 4 if j == 0 else 0))

    p = tmp_path / "song.mid"
    mid.save(p)
    return p


def test_reads_chord_track(logic_style_midi):
    got = chords_from_midi(logic_style_midi, track_filter="chord")
    assert [c.chord for c in got] == ["Am7", "Fmaj7", "C", "G7"]


def test_spans_are_two_bars_at_120bpm(logic_style_midi):
    got = chords_from_midi(logic_style_midi, track_filter="chord")
    assert got[0].start == pytest.approx(0.0)
    assert got[0].end == pytest.approx(2.0, abs=0.13)


def test_authored_chords_are_high_confidence(logic_style_midi):
    got = chords_from_midi(logic_style_midi, track_filter="chord")
    assert all(c.confidence > 0.9 for c in got)


def test_unfiltered_read_is_polluted_by_other_tracks(logic_style_midi):
    """Why track_filter exists: a sustained bass note rewrites the chord."""
    everything = [c.chord for c in chords_from_midi(logic_style_midi)]
    assert everything != ["Am7", "Fmaj7", "C", "G7"]
    assert everything[0] == "C6"


def test_list_tracks(logic_style_midi):
    tracks = list_tracks(logic_style_midi)
    assert [t["name"] for t in tracks] == ["Tempo", "Bass DI", "Chords"]
    assert tracks[2]["notes"] == 16


def test_find_chord_midi_prefers_named_file(tmp_path, logic_style_midi):
    import shutil
    from abletonhelper.library import find_chord_midi
    shutil.copy(logic_style_midi, tmp_path / "Chords.mid")
    shutil.copy(logic_style_midi, tmp_path / "Drums.mid")
    assert find_chord_midi(tmp_path).name == "Chords.mid"


def test_find_chord_midi_ambiguous_returns_none(tmp_path, logic_style_midi):
    import shutil
    from abletonhelper.library import find_chord_midi
    shutil.copy(logic_style_midi, tmp_path / "a.mid")
    shutil.copy(logic_style_midi, tmp_path / "b.mid")
    assert find_chord_midi(tmp_path) is None
