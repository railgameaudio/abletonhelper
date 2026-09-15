"""Timed lyrics from .lrc files.

LRC is the karaoke format: a timestamp per line, optional metadata tags,
optional per-word timings. It is chosen here over transcription or forced
alignment for one reason -- it cannot be subtly wrong. What the file says
is what you get, and the person who wrote it decided the timing.

    [ar:The Band]
    [offset:+500]
    [00:12.50]First line
    [00:15.30][01:42.10]A line that recurs

Parsed into `LyricLine` spans in seconds, consistent with everything else
in `AnalysisResult`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# [mm:ss.xx] / [mm:ss.xxx] / [mm:ss] -- possibly several on one line.
_TIME = re.compile(r"\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]")
# [key:value] metadata, but not a timestamp (which starts with digits+colon).
_META = re.compile(r"^\[([a-zA-Z#]+):(.*)\]$")
# Enhanced-LRC per-word timings: <00:12.50>
_WORD = re.compile(r"<\d{1,3}:\d{1,2}(?:[.:]\d{1,3})?>")


@dataclass(frozen=True)
class LyricLine:
    start: float
    end: float
    text: str

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class LyricsDoc:
    lines: list[LyricLine] = field(default_factory=list)
    meta: dict[str, str] = field(default_factory=dict)

    def line_at(self, t: float) -> LyricLine | None:
        for line in self.lines:
            if line.start <= t < line.end:
                return line
        return None


def _to_seconds(m: re.Match) -> float:
    minutes, seconds, frac = m.group(1), m.group(2), m.group(3)
    total = int(minutes) * 60 + int(seconds)
    if frac:
        # Two digits are centiseconds, three are milliseconds.
        total += int(frac) / (100.0 if len(frac) == 2 else
                              1000.0 if len(frac) == 3 else 10.0)
    return total


def parse_lrc(path: str | Path, duration: float | None = None,
              tail_seconds: float = 4.0) -> LyricsDoc:
    """Parse an .lrc file into timed lines.

    A line runs until the next one starts. The last line runs to
    `duration` when the song length is known, else `tail_seconds`.
    An `[offset:]` tag shifts every timestamp, per the LRC convention
    (positive offset means the lyrics should appear earlier).
    """
    raw = Path(path).read_text(encoding="utf-8-sig", errors="replace")

    meta: dict[str, str] = {}
    stamped: list[tuple[float, str]] = []

    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        times = list(_TIME.finditer(line))
        if not times:
            m = _META.match(line)
            if m:
                meta[m.group(1).lower()] = m.group(2).strip()
            continue

        # Text is whatever follows the last timestamp.
        text = line[times[-1].end():]
        text = _WORD.sub("", text).strip()
        for t in times:
            stamped.append((_to_seconds(t), text))

    offset = 0.0
    if "offset" in meta:
        try:
            offset = int(meta["offset"].replace("+", "")) / 1000.0
        except ValueError:
            offset = 0.0

    stamped.sort(key=lambda p: p[0])
    lines: list[LyricLine] = []
    for i, (start, text) in enumerate(stamped):
        start = max(0.0, start - offset)
        if i + 1 < len(stamped):
            end = max(start, stamped[i + 1][0] - offset)
        elif duration is not None:
            end = max(start, duration)
        else:
            end = start + tail_seconds
        # Empty text marks an instrumental gap; keep it as a boundary only.
        if text:
            lines.append(LyricLine(start, end, text))

    return LyricsDoc(lines=lines, meta=meta)


def find_lrc(folder: Path) -> Path | None:
    """The .lrc in a song folder, if there is exactly one obvious choice."""
    hits = [f for f in sorted(folder.iterdir())
            if f.is_file() and f.suffix.lower() == ".lrc"]
    if len(hits) == 1:
        return hits[0]
    for f in hits:
        if "lyric" in f.name.lower():
            return f
    return None


def to_plain_text(doc: LyricsDoc) -> str:
    return "\n".join(line.text for line in doc.lines)
