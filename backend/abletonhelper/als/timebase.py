"""Seconds <-> Ableton time, in exactly one place.

Live's arrangement time is in BEATS for most fields. Whether an UNWARPED
clip's Loop fields follow that rule is the one thing this project refuses
to assume -- `als/inspect.py` measures it from a real template and
`TimeBase.from_report()` below is configured by that measurement rather
than by a constant baked in here.

If you are tempted to hardcode `beats = seconds * bpm / 60` for loop
fields: run the inspector first.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Units = Literal["beats", "seconds", "unknown"]


@dataclass(frozen=True)
class TimeBase:
    tempo: float
    time_signature: int = 4
    # How this template encodes unwarped-clip loop fields.
    loop_units: Units = "unknown"

    # -- arrangement position (always beats in Live) -------------------

    def seconds_to_beats(self, seconds: float) -> float:
        return seconds * self.tempo / 60.0

    def beats_to_seconds(self, beats: float) -> float:
        return beats * 60.0 / self.tempo

    def seconds_to_bars(self, seconds: float) -> float:
        return self.seconds_to_beats(seconds) / self.time_signature

    def bars_to_seconds(self, bars: float) -> float:
        return self.beats_to_seconds(bars * self.time_signature)

    # -- clip loop fields (template-dependent) -------------------------

    def loop_value(self, seconds: float) -> float:
        """Encode a duration for Loop/LoopEnd etc. in this template's units."""
        if self.loop_units == "seconds":
            return seconds
        if self.loop_units == "beats":
            return self.seconds_to_beats(seconds)
        raise RuntimeError(
            "loop_units is 'unknown' -- run `abletonhelper inspect <template.als>` "
            "and pass the measured units. Refusing to guess, because a wrong "
            "guess produces a set that looks fine and plays wrong."
        )

    def loop_seconds(self, value: float) -> float:
        if self.loop_units == "seconds":
            return value
        if self.loop_units == "beats":
            return self.beats_to_seconds(value)
        raise RuntimeError("loop_units is 'unknown'")

    @classmethod
    def from_report(cls, report) -> "TimeBase":
        """Build from an inspect.TemplateReport, reading the measured verdict."""
        units: Units = "unknown"
        for clip in report.clips:
            v = clip.timebase_verdict
            if v.startswith("BEATS"):
                units = "beats"
                break
            if v.startswith("SECONDS"):
                units = "seconds"
                break
        meter = 4
        try:
            meter = int(report.time_signature) if report.time_signature else 4
        except (TypeError, ValueError):
            meter = 4
        return cls(tempo=report.tempo or 120.0, time_signature=meter, loop_units=units)
