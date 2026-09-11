"""Adapter for All-In-One Music Structure Analyzer (Kim & Nam, ISMIR 2023).

This is the backend that actually answers "where is the chorus". It is a
single model that jointly predicts beats, downbeats, tempo and FUNCTIONAL
segment labels (intro / verse / chorus / bridge / inst / solo / outro),
which is exactly the vocabulary a setlist needs.

Install:  pip install allin1        (pulls torch + natten + demucs)
Note:     allin1 runs demucs internally for source separation. When we
          already have stems on disk that work is redundant -- see
          `prefer_existing_stems` below.

NOT YET RUN IN THIS ENVIRONMENT: the package pulls ~2.5 GB of torch and
there is no GPU here. The call surface below follows the documented API;
treat `analyze()` as unverified until it has been exercised against real
audio on the target machine. `available()` will tell you honestly.
"""

from __future__ import annotations

from pathlib import Path

from .base import AnalysisInput, AnalysisResult, Section

NAME = "allin1"

# allin1's label vocabulary -> ours (see base.CANONICAL_LABELS).
_LABEL_MAP = {
    "start": "intro",
    "end": "outro",
    "intro": "intro",
    "verse": "verse",
    "chorus": "chorus",
    "bridge": "bridge",
    "inst": "instrumental",
    "instrumental": "instrumental",
    "solo": "solo",
    "break": "breakdown",
    "outro": "outro",
    "silence": "silence",
}


class AllIn1Analyzer:
    name = NAME

    def __init__(self, device: str | None = None, keep_byproducts: bool = False):
        # None -> let allin1 choose (cuda when present, else cpu).
        self.device = device
        self.keep_byproducts = keep_byproducts

    @property
    def version(self) -> str:
        try:
            import allin1
            return f"allin1-{getattr(allin1, '__version__', 'unknown')}"
        except Exception:
            return "allin1-missing"

    def available(self) -> tuple[bool, str]:
        try:
            import allin1  # noqa: F401
        except ImportError as e:
            return False, (
                f"allin1 not installed ({e}). Install with: pip install allin1 "
                "(requires torch and natten; first run downloads model weights)"
            )
        try:
            import torch
        except ImportError as e:
            return False, f"torch missing: {e}"
        if not torch.cuda.is_available() and self.device in ("cuda", "gpu"):
            return False, "cuda requested but unavailable"
        return True, ""

    def analyze(self, inp: AnalysisInput) -> AnalysisResult:
        import allin1

        path = inp.primary()
        kwargs = {}
        if self.device:
            kwargs["device"] = self.device
        if self.keep_byproducts:
            kwargs["keep_byproducts"] = True

        raw = allin1.analyze(str(path), **kwargs)
        # allin1 returns a list when given a list of paths.
        if isinstance(raw, list):
            raw = raw[0]

        beats = [float(t) for t in (getattr(raw, "beats", None) or [])]
        downbeats = [float(t) for t in (getattr(raw, "downbeats", None) or [])]

        sections: list[Section] = []
        for seg in (getattr(raw, "segments", None) or []):
            label = str(getattr(seg, "label", "unknown")).lower()
            sections.append(Section(
                start=float(getattr(seg, "start", 0.0)),
                end=float(getattr(seg, "end", 0.0)),
                label=_LABEL_MAP.get(label, label),
                confidence=0.8,
            ))

        meter = self._infer_meter(getattr(raw, "beat_positions", None), beats, downbeats)

        return AnalysisResult(
            source=str(path),
            duration=float(sections[-1].end) if sections else 0.0,
            backend=self.name,
            backend_version=self.version,
            tempo=float(getattr(raw, "bpm", 0.0) or 0.0),
            time_signature=meter,
            beats=beats,
            downbeats=downbeats,
            sections=sections,
            chords=[],   # allin1 does not predict chords; see notes below.
            meta={
                "device": self.device or "auto",
                "chords": "not provided by allin1 -- run a chord backend separately",
            },
        )

    @staticmethod
    def _infer_meter(beat_positions, beats, downbeats) -> int:
        if beat_positions:
            try:
                return int(max(beat_positions))
            except (TypeError, ValueError):
                pass
        if len(downbeats) > 1 and len(beats) > 1:
            per_bar = round(len(beats) / max(len(downbeats), 1))
            if 2 <= per_bar <= 12:
                return int(per_bar)
        return 4
