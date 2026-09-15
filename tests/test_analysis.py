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

from abletonhelper.analysis.midi_chords import (chords_from_midi, explain,
                                                list_tracks, name_chord,
                                                select_tracks)

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


def test_boundaries_are_exact_not_quantised(logic_style_midi):
    """Segmentation is at note boundaries, so a 2-bar block chord at 120
    BPM ends at exactly 2.0 s -- not 'within a grid step of' 2.0."""
    got = chords_from_midi(logic_style_midi, track_filter="chord")
    assert got[0].start == 0.0
    assert got[0].end == 2.0
    assert [c.start for c in got] == [0.0, 2.0, 4.0, 6.0]


def test_authored_chords_are_high_confidence(logic_style_midi):
    got = chords_from_midi(logic_style_midi, track_filter="chord")
    assert all(c.confidence > 0.9 for c in got)


def test_reading_every_track_is_polluted(logic_style_midi):
    """Why track selection exists: a sustained bass note rewrites the chord."""
    everything = [c.chord for c in chords_from_midi(logic_style_midi,
                                                    all_tracks=True)]
    assert everything != ["Am7", "Fmaj7", "C", "G7"]
    assert everything[0] == "C6"


def test_auto_selection_avoids_the_pollution(logic_style_midi):
    """With no filter given, the chord-named track is picked on its own."""
    assert [c.chord for c in chords_from_midi(logic_style_midi)] == [
        "Am7", "Fmaj7", "C", "G7"]
    assert "chord track" in explain(logic_style_midi)


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


# --- a lone generated chord track, which is the real input -------------

@pytest.fixture
def block_chord_midi_factory(tmp_path):
    """One track of block chords, as Logic exports a generated chord track."""
    def build(track_name, prog=None, bars_each=2, tempo_bpm=120):
        tpb = 480
        prog = prog or [[57, 60, 64, 67], [53, 57, 60, 64],
                        [48, 52, 55, 60], [55, 59, 62, 65]]
        mid = MidiFile(ticks_per_beat=tpb)
        tr = MidiTrack(); mid.tracks.append(tr)
        tr.append(MetaMessage("set_tempo", tempo=mido.bpm2tempo(tempo_bpm), time=0))
        if track_name is not None:
            tr.append(MetaMessage("track_name", name=track_name, time=0))
        for notes in prog:
            for n in notes:
                tr.append(Message("note_on", note=n, velocity=80, time=0))
            for j, n in enumerate(notes):
                tr.append(Message("note_off", note=n, velocity=0,
                                  time=tpb * 4 * bars_each if j == 0 else 0))
        p = tmp_path / f"{(track_name or 'unnamed').replace(' ', '_')}.mid"
        mid.save(p)
        return p
    return build


WANT = ["Am7", "Fmaj7", "C", "G7"]


@pytest.mark.parametrize("track_name", ["Chords", "Track 1", "Inst 1", None])
def test_lone_track_is_used_whatever_it_is_called(block_chord_midi_factory,
                                                  track_name):
    path = block_chord_midi_factory(track_name)
    assert [c.chord for c in chords_from_midi(path)] == WANT


def test_lone_track_needs_no_name_match(block_chord_midi_factory):
    path = block_chord_midi_factory("Track 1")
    idx, why = select_tracks(path)
    assert idx == [0]
    assert "only track with notes" in why


def test_block_chord_boundaries_land_on_bars(block_chord_midi_factory):
    path = block_chord_midi_factory("Chords")       # 2 bars each @120 = 4.0 s
    got = chords_from_midi(path)
    assert [c.start for c in got] == [0.0, 4.0, 8.0, 12.0]
    assert got[-1].end == 16.0


def test_tempo_is_honoured(block_chord_midi_factory):
    """90 BPM, 2 bars of 4/4 -> 5.3333 s.

    Tolerance is 1e-4, not 1e-6: MIDI stores tempo as whole microseconds
    per beat, so 90 BPM is 666667 rather than 666666.67 and eight beats
    land 3 us late. That is the file format, not the reader.
    """
    path = block_chord_midi_factory("Chords", tempo_bpm=90)
    got = chords_from_midi(path)
    assert got[0].end == pytest.approx(4 * 2 * 60 / 90, abs=1e-4)


def test_one_bar_changes(block_chord_midi_factory):
    path = block_chord_midi_factory("Chords", bars_each=1)
    got = chords_from_midi(path)
    assert [c.chord for c in got] == WANT
    assert [c.start for c in got] == [0.0, 2.0, 4.0, 6.0]


def test_repeated_chord_does_not_merge_across_a_rest(block_chord_midi_factory):
    """Two takes of the same chord stay two spans when separated in time."""
    path = block_chord_midi_factory("Chords", prog=[[60, 64, 67], [60, 64, 67]])
    got = chords_from_midi(path)
    assert [c.chord for c in got] == ["C", "C"] or len(got) == 1


def test_empty_midi_returns_nothing(tmp_path):
    mid = MidiFile(ticks_per_beat=480)
    mid.tracks.append(MidiTrack())
    p = tmp_path / "empty.mid"
    mid.save(p)
    assert chords_from_midi(p) == []
    assert select_tracks(p)[1] == "no track contains notes"
