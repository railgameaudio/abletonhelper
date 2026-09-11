# Music analysis: what exists, what we use, what it costs

## The short answer

There is no service running anywhere for this. Nothing was set up before
now. What exists is a set of open-source models you run yourself, and
they are not equally good at the three things you asked for.

| Need | Best option | Quality | Notes |
|---|---|---|---|
| Tempo + beat grid | `allin1`, or librosa | very good | librosa measured at 0.002% error on a synthetic 120 BPM test |
| Key | librosa (Krumhansl-Kessler) | good | correct on the test signal |
| Chords | librosa chroma + triad templates | good for triads | no 7ths, no inversions, no slash chords |
| **Sections** | **`allin1`** | **the only real option** | librosa cannot name a chorus — see below |

## Why sections are the hard one

This is the part you said matters most for the setlist, and it is the
part where the gap between backends is widest.

librosa can do **structure** but not **semantics**. Its Laplacian
segmentation (McFee & Ellis 2014, implemented in
`analysis/librosa_backend.py`) finds where the music repeats and groups
those spans into clusters — it will correctly tell you "span 3 is the
same music as span 5". It has no idea that the repeated loud one is
called a chorus. Our label mapping is an explicit heuristic (most
repeated + highest energy = chorus, first = intro, last = outro) and it
ships with `confidence = 0.25` as an honest signal, not as decoration.

Measured on a synthetic 6-section song with known boundaries, it found
5 sections with boundaries off by up to 14 seconds. Chords and tempo on
the same file were essentially perfect. That asymmetry is the whole
argument for a second backend.

**All-In-One Music Structure Analyzer** (Kim & Nam, ISMIR 2023) is a
single model trained to predict beats, downbeats, tempo *and* functional
segment labels — `intro`, `verse`, `chorus`, `bridge`, `inst`, `solo`,
`outro`. That vocabulary is exactly what a setlist needs, which is why
it is the preferred backend in `analysis/registry.py`.

```bash
pip install allin1
```

Costs to know before you commit:
- Pulls PyTorch, NATTEN and Demucs. Expect ~2.5 GB.
- Downloads model weights on first run.
- Runs Demucs source separation internally. On CPU that is slow — minutes
  per song. With a CUDA GPU it is seconds. Your Mac will use CPU unless
  you get MPS working, which NATTEN historically does not.
- It does **not** predict chords. `registry.analyze()` therefore fills
  chords in from librosa automatically, so you get both.

## Other things considered

- **madmom** — excellent beat/downbeat DBN trackers and a chord
  recogniser. Pinned at 0.16.1 and does not build cleanly on Python 3.11
  without patching; skipped for now, worth revisiting if beat tracking
  ever proves to be the weak link.
- **Essentia** — no wheel available on this platform. Would need building
  from source.
- **MSAF** — unsupervised segmentation only, same semantic gap as
  librosa, one more dependency. No advantage.
- **BTC / Chordino** — better chord models than our template matcher. Only
  worth adding if triads turn out to be insufficient.

## Using your stems

You already have stems, which is an advantage the model list above does
not assume. `AnalysisInput` carries them, and the librosa backend
already uses them when present:

- beat tracking runs on the **drums** stem when there is one — transient
  audio tracks far more reliably than a full mix
- chroma/chords run on **other** or **bass** rather than the mix

If you eventually feed allin1 your stems directly you can skip its
internal Demucs pass entirely. That is the single largest speedup
available and is the main open optimisation here.

## Calibrating against your own music

The numbers above come from a synthetic test signal, which is
deliberately easy in some ways (dead-steady tempo) and unusually hard in
others (sine triads give segmentation very little timbral contrast to
work with). They are a sanity check, not a benchmark.

Before trusting any of this on stage, run it on a few real songs where
you already know the answer and compare. `abletonhelper analyze <folder>`
prints sections in bars, which is the unit you will actually check in
Live.
