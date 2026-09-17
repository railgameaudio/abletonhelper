# abletonhelper

Turn a folder of song stems into a performance-ready Ableton Live set.

Point it at a song's stems, add whatever you've already authored in Logic
(chord MIDI, section markers, lyrics), and it works out tempo, key,
chords, arrangement sections and timed lyrics — then builds a Live set
from your own template.

It runs locally as a web app. The architecture is deliberately shaped so
the same codebase can become a hosted service later without a rewrite.

---

## Honest status

This matters more than a feature list, so it's first.

| | State |
|---|---|
| Read stems from a folder | **works**, tested |
| Tempo / key / beat grid | **works** — 0.002% tempo error on a reference signal |
| Chords from authored MIDI | **works** — exact spans, exact boundaries |
| Chords from audio | **works**, triads only (no 7ths, no inversions) |
| Sections from `sections.txt` / MIDI markers | **works** — 6/6 exact |
| Sections from audio | works but **weak** — 5/6, boundaries off by up to 14 s |
| Timed lyrics from `.lrc` | **works** |
| Web UI + background jobs | **works**, exercised end to end |
| **Writing the `.als`** | **not built** — blocked on your template |

**Today, giving it stems produces an analysis JSON, not a Live set.** The
set builder stops at `NotImplementedError` on purpose. See
[Why the builder is unfinished](#why-the-builder-is-unfinished).

90 tests pass on librosa 0.11.0 / Python 3.11 and librosa 1.0.0 /
Python 3.12.

---

## Requirements

- **Python 3.12+** (3.10 minimum, but librosa 1.0 needs 3.12). macOS's
  built-in `/usr/bin/python3` is 3.9 and will not work.
- Node 18+ for the frontend.

```bash
brew install python@3.12      # or python.org installer
```

## Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .

cd frontend && npm install && cd ..
```

`pip install -e .` pulls librosa, numba and scipy — expect a few minutes.

## Run

```bash
make dev      # API on :8000, UI on :5173
make serve    # API on 0.0.0.0 so phones on your network can reach it
make check    # imports, backends, TS build, full test suite
```

---

## How a song is described

Everything except the audio is optional. Each authored file replaces a
detected guess with ground truth.

```
songs/my-song/
├── Kick.wav            stems — the only required part
├── Bass DI.wav
├── LeadVox.wav
├── Chords.mid          authored chords      → replaces detection
├── sections.txt        authored arrangement → replaces detection
└── lyrics.lrc          timed lyrics         → nothing else provides these
```

Stem roles are inferred from filenames (`kick`/`snare`/`perc` → drums,
`vox` → vocals, `gtr` → guitar, and so on), which lets the analyzer track
beats on the drums stem and chords on the harmonic ones rather than on a
mixdown.

`sections.txt`:

```
0:00   Intro
0:08   Verse 1
0:24   Chorus
2:04   Outro
```

`lyrics.lrc` is standard LRC (the karaoke format) — timestamps, optional
`[offset:]`, multiple timestamps per repeated line.

Full details: [`docs/song-folder.md`](docs/song-folder.md).

---

## Why authored input wins

Section detection is the weakest signal this project produces. On a
reference song with known boundaries it found 5 sections where there were
6, with boundaries off by up to 14 seconds — and the labels *changed
between librosa versions on byte-identical input*.

That instability is why marking sections by hand is the recommended path,
and why **`allin1` is not needed**. It's a good model (it's the one thing
that predicts real `intro`/`verse`/`chorus` labels rather than repetition
clusters), but it costs ~2.5 GB of PyTorch and runs slowly without a GPU.
Hand-marked sections beat it. The adapter is written and wired if you ever
want it for songs nobody will mark up.

Same logic for chords: the audio path gets triads right, but a chord track
you actually played gets 7ths, inversions and slash chords right too.

Authored data carries `confidence = 1.0`. Detected sections carry `0.25`,
and the UI says so — a wrong chorus marker on stage is worse than no
marker.

---

## Architecture

```
frontend/   React + Vite (TypeScript)
               │  /api
backend/    FastAPI
            ├── analysis/   pluggable analyzers → AnalysisResult
            ├── als/        read + write Live sets
            ├── library.py  stem discovery, analysis orchestration
            ├── jobs.py     background work
            └── db.py       SQLAlchemy over SQLite
```

**One contract matters:** `analysis/base.py::AnalysisResult`. It is the
only thing crossing from analysis into set building and the UI, so
backends are swappable because nothing downstream knows which one ran.
Times in it are **always seconds**; conversion to Ableton units happens
once, in `als/timebase.py`.

Choices that make the eventual hosted version cheap: SQLite behind
SQLAlchemy (one env var to point at Postgres), jobs behind `jobs.submit`
(swap the thread pool for a real queue, the API contract is unchanged),
and a `single_user` flag.

More: [`docs/architecture.md`](docs/architecture.md).

---

## Why the builder is unfinished

`als/builder.py` raises `NotImplementedError` in its placement pass. This
is deliberate, and there are two hard rules behind it.

**1. Never guess Live's XML.** The builder clones structure out of *your*
template rather than synthesising Live XML from scratch. Hand-written Live
XML breaks on Live updates and fails in ways that look fine until
playback. So it needs `templates/Template.als` — containing at least one
audio clip, which serves as the prototype it copies.

**2. Never assume the clip timebase.** Whether an unwarped clip's
`Loop/LoopStart`, `LoopEnd` and `StartRelative` are in beats or seconds is
*measured*, not remembered. `als/inspect.py::timebase_evidence` compares
the clip's loop length against the sample's true duration derived from
`SampleRef` (`DefaultDuration / SampleRate`), and reports BEATS, SECONDS,
AMBIGUOUS (at 60 BPM a beat *is* a second) or INCONCLUSIVE (trimmed clip).
It's verified to discriminate correctly in both directions against
synthetic sets. `TimeBase.loop_value()` raises rather than guess.

To unblock it:

```bash
cp "/path/to/your/Template.als" templates/Template.als
git check-ignore -v templates/Template.als    # must print NOTHING
python -m abletonhelper.cli inspect templates/Template.als
```

That report gives the real track layout, clip node structure and the
measured timebase — enough to finish the placement pass against what's
actually in your file.

> `*.als` must never be added to `.gitignore`. It is **input**. Ableton's
> own project folders ship with ignore rules that exclude it, and the
> failure is silent: the push succeeds, the template just isn't in it.

---

## CLI

```bash
python -m abletonhelper.cli backends                     # what's usable
python -m abletonhelper.cli analyze songs/my-song/       # full analysis
python -m abletonhelper.cli chords songs/my-song/Chords.mid
python -m abletonhelper.cli chords songs/my-song/Chords.mid --tracks
python -m abletonhelper.cli inspect templates/Template.als
```

---

## What's next

1. Add `templates/Template.als`, run `inspect`, finish the builder.
2. Setlist → arrangement: sections become Live locators; chords and
   lyrics become lanes. **Open decision** — named clips (readable across
   a stage), real MIDI notes (playable), or both on a muted track. See
   [`docs/chords.md`](docs/chords.md).
3. Project-folder export with relative sample paths. Required before this
   could ever be hosted: a generated `.als` references audio by absolute
   path, and a server can't know where someone else's Mac keeps its
   files. The fix is emitting a proper Ableton Project folder as a zip,
   which also makes local sets portable between machines.

---

## Docs

| | |
|---|---|
| [`docs/song-folder.md`](docs/song-folder.md) | what goes in a song folder |
| [`docs/chords.md`](docs/chords.md) | chord sources, track selection, Live rendering options |
| [`docs/analysis.md`](docs/analysis.md) | analyzer backends and what each costs |
| [`docs/architecture.md`](docs/architecture.md) | structure, local → hosted |
| [`docs/assets.md`](docs/assets.md) | templates and audio in git |
| [`CLAUDE.md`](CLAUDE.md) | working constraints and state |
