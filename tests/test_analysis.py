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
