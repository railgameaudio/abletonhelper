"""Backend selection and the combined analyzer.

Nothing outside this module should instantiate a backend directly.
"""

from __future__ import annotations

from .base import AnalysisInput, AnalysisResult, Analyzer
from .allin1_backend import AllIn1Analyzer
from .librosa_backend import LibrosaAnalyzer

_BUILDERS = {
    "librosa": LibrosaAnalyzer,
    "allin1": AllIn1Analyzer,
}

# Order matters: first available wins when backend="auto".
PREFERENCE = ("allin1", "librosa")


def get(name: str, **kwargs) -> Analyzer:
    if name not in _BUILDERS:
        raise KeyError(f"unknown backend {name!r}; have {sorted(_BUILDERS)}")
    return _BUILDERS[name](**kwargs)


def status() -> dict[str, dict]:
    """What is usable right now, and why not when it isn't."""
    out = {}
    for name in _BUILDERS:
        a = _BUILDERS[name]()
        ok, reason = a.available()
        out[name] = {"available": ok, "reason": reason, "version": a.version}
    return out


def resolve(name: str = "auto") -> Analyzer:
    if name != "auto":
        return get(name)
    for candidate in PREFERENCE:
        a = _BUILDERS[candidate]()
        if a.available()[0]:
            return a
    raise RuntimeError("no analysis backend available; pip install librosa")


def analyze(inp: AnalysisInput, backend: str = "auto") -> AnalysisResult:
    """Run `backend`, then fill gaps from the fallback.

    allin1 gives the best sections but no chords; librosa gives decent
    chords but weak sections. When the chosen backend leaves chords empty
    we top them up from librosa rather than shipping a half-empty result.
    """
    analyzer = resolve(backend)
    result = analyzer.analyze(inp)

    if not result.chords:
        helper = LibrosaAnalyzer()
        if helper.available()[0]:
            try:
                aux = helper.analyze(inp)
                result.chords = aux.chords
                result.key = result.key or aux.key
                result.meta["chords_backend"] = helper.version
            except Exception as e:      # chords are a bonus, never fatal
                result.meta["chords_error"] = str(e)
    return result
