import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

SR = 22050


@pytest.fixture(scope="session")
def click_track(tmp_path_factory):
    """12 s of 4/4 at exactly 120 BPM, with a C major triad under it."""
    import soundfile as sf

    bpm, dur = 120.0, 12.0
    spb = 60.0 / bpm
    t = np.linspace(0, dur, int(SR * dur), endpoint=False)
    tone = sum(np.sin(2 * np.pi * f * t) for f in (261.63, 329.63, 392.00)) / 3
    y = tone * 0.3
    rng = np.random.RandomState(0)
    for i in range(int(dur / spb)):
        o = int(i * spb * SR)
        k = int(SR * 0.04)
        burst = rng.randn(k) * np.exp(-np.linspace(0, 40, k))
        burst *= 1.6 if i % 4 == 0 else 1.0
        y[o:o + k] += burst[:max(0, len(y) - o)][:k] * 0.6
    y = y / np.max(np.abs(y)) * 0.9

    p = tmp_path_factory.mktemp("audio") / "click.wav"
    sf.write(p, y, SR)
    return p
