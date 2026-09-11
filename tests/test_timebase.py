"""The assumption this project most refuses to make."""

import gzip

import pytest

from abletonhelper.als.inspect import inspect, timebase_evidence
from abletonhelper.als.timebase import TimeBase

TPL = """<?xml version="1.0" encoding="UTF-8"?>
<Ableton MajorVersion="5" MinorVersion="12.0_12049" Creator="Ableton Live 12.1.5">
 <LiveSet><Tracks><AudioTrack Id="8">
   <Name><EffectiveName Value="Stem 1"/></Name>
   <AudioClip Id="0">
     <Name Value="kick"/>
     <CurrentStart Value="0"/><CurrentEnd Value="{le}"/>
     <Loop><LoopStart Value="0"/><LoopEnd Value="{le}"/>
       <StartRelative Value="0"/>
       <HiddenLoopStart Value="0"/><HiddenLoopEnd Value="{le}"/></Loop>
     <IsWarped Value="false"/>
     <SampleRef><FileRef><Name Value="k.wav"/><Path Value="/tmp/k.wav"/></FileRef>
       <DefaultDuration Value="352800"/><DefaultSampleRate Value="44100"/></SampleRef>
   </AudioClip>
 </AudioTrack></Tracks>
 <MasterTrack><DeviceChain><Mixer><Tempo><Manual Value="{bpm}"/></Tempo>
 </Mixer></DeviceChain></MasterTrack></LiveSet></Ableton>"""


def _write(tmp_path, le, bpm=120):
    p = tmp_path / "t.als"
    p.write_bytes(gzip.compress(TPL.format(le=le, bpm=bpm).encode()))
    return p


# sample is 352800/44100 = 8.0 s; at 120 BPM that is 16 beats

def test_detects_seconds_encoding(tmp_path):
    r = inspect(_write(tmp_path, 8.0))
    assert r.clips[0].timebase_verdict.startswith("SECONDS")


def test_detects_beats_encoding(tmp_path):
    r = inspect(_write(tmp_path, 16.0))
    assert r.clips[0].timebase_verdict.startswith("BEATS")


def test_ambiguous_at_60_bpm(tmp_path):
    """At 60 BPM a beat is a second and the test cannot discriminate."""
    r = inspect(_write(tmp_path, 8.0, bpm=60))
    assert r.clips[0].timebase_verdict.startswith("AMBIGUOUS")


def test_trimmed_clip_is_inconclusive_not_wrong(tmp_path):
    r = inspect(_write(tmp_path, 5.5))
    assert r.clips[0].timebase_verdict.startswith("INCONCLUSIVE")


def test_reads_sample_metadata(tmp_path):
    c = inspect(_write(tmp_path, 8.0)).clips[0]
    assert c.sample_seconds == pytest.approx(8.0)
    assert c.is_warped is False
    assert c.sample_path == "/tmp/k.wav"


def test_timebase_refuses_to_guess():
    tb = TimeBase(tempo=120, loop_units="unknown")
    with pytest.raises(RuntimeError, match="Refusing to guess"):
        tb.loop_value(8.0)


def test_timebase_converts_when_known():
    assert TimeBase(120, loop_units="seconds").loop_value(8.0) == pytest.approx(8.0)
    assert TimeBase(120, loop_units="beats").loop_value(8.0) == pytest.approx(16.0)


def test_from_report_picks_up_measurement(tmp_path):
    tb = TimeBase.from_report(inspect(_write(tmp_path, 16.0)))
    assert tb.loop_units == "beats"
    assert tb.tempo == pytest.approx(120.0)


def test_evidence_without_tempo_is_honest():
    assert "cannot test" in timebase_evidence(8.0, 8.0, None, False)
