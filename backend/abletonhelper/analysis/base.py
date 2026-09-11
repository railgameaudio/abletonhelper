"""Analysis contract.

Everything downstream -- the setlist builder, the .als writer, the UI
timeline -- consumes `AnalysisResult` and nothing else. Backends are
swappable precisely because this is the only surface they expose.

Time is ALWAYS in seconds here. Conversion to Ableton beats happens in
one place (als/timebase.py) so the beats-vs-seconds question is answered
once rather than at every call site.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Protocol, Sequence


SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Section:
    """A functional span of the song: intro / verse / chorus / ..."""

    start: float
    end: float
    label: str
    confidence: float = 0.0

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass(frozen=True)
class ChordSpan:
    start: float
    end: float
    # Harte-style label: "C:maj", "A:min", "G:7", or "N" for no-chord.
    chord: str
    confidence: float = 0.0


@dataclass
class AnalysisResult:
    source: str                       # path of what was analysed
    duration: float                   # seconds
    backend: str                      # which analyzer produced this
    backend_version: str

    tempo: float = 0.0                # global BPM estimate
    time_signature: int = 4           # beats per bar
    key: str | None = None

    beats: list[float] = field(default_factory=list)
    downbeats: list[float] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    chords: list[ChordSpan] = field(default_factory=list)

    # Free-form backend diagnostics; never load-bearing.
    meta: dict = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION

    # -- serialisation ------------------------------------------------

    def to_dict(self) -> dict:
        return asdict(self)

    def write_json(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2))
        return path

    @classmethod
    def from_dict(cls, d: dict) -> "AnalysisResult":
        d = dict(d)
        d["sections"] = [Section(**s) for s in d.get("sections", [])]
        d["chords"] = [ChordSpan(**c) for c in d.get("chords", [])]
        d.pop("schema_version", None)
        return cls(**d)

    @classmethod
    def read_json(cls, path: str | Path) -> "AnalysisResult":
        return cls.from_dict(json.loads(Path(path).read_text()))

    # -- convenience --------------------------------------------------

    def section_at(self, t: float) -> Section | None:
        for s in self.sections:
            if s.start <= t < s.end:
                return s
        return None

    def bar_times(self) -> list[float]:
        """Downbeats if the backend gave us any, else inferred from beats."""
        if self.downbeats:
            return list(self.downbeats)
        n = self.time_signature
        return [t for i, t in enumerate(self.beats) if i % n == 0]


@dataclass(frozen=True)
class AnalysisInput:
    """What to analyse.

    `mix` is a single audio file. `stems` is an optional mapping of
    stem-name -> path (e.g. {"drums": ..., "bass": ...}). When stems are
    supplied a backend may use them directly and skip source separation,
    which is both faster and more accurate than separating a mixdown.
    """

    mix: Path | None = None
    stems: dict[str, Path] = field(default_factory=dict)

    def primary(self) -> Path:
        if self.mix is not None:
            return self.mix
        if self.stems:
            return next(iter(self.stems.values()))
        raise ValueError("AnalysisInput has neither a mix nor any stems")


class Analyzer(Protocol):
    """Implemented by every backend in this package."""

    name: str
    version: str

    def available(self) -> tuple[bool, str]:
        """(is_usable, human-readable reason when not)."""
        ...

    def analyze(self, inp: AnalysisInput) -> AnalysisResult:
        ...


# Labels the setlist builder understands. Backends must map onto these.
CANONICAL_LABELS: Sequence[str] = (
    "intro", "verse", "prechorus", "chorus", "bridge",
    "instrumental", "solo", "breakdown", "outro", "silence",
)
