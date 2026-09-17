# Handoff: what was built, and why it is the way it is

A record of the work and the reasoning, so the decisions are auditable
rather than folklore. Chronological by commit.

## 1. Scaffold (`13cd90d`)

Local-first web app: FastAPI + SQLAlchemy/SQLite backend, React + Vite
frontend, background jobs in a thread pool.

Established `AnalysisResult` as the single contract crossing from
analysis into set building and the UI. Everything downstream consumes it
and nothing else, which is what makes analyzer backends swappable. All
times in it are seconds; Ableton-unit conversion is isolated in
`als/timebase.py`.

Built `als/inspect.py`, which reports a template's real structure and
**measures** whether unwarped clip loop fields are beats or seconds
rather than assuming. Method: compare the clip's loop length against the
sample's true duration from `SampleRef` (`DefaultDuration / SampleRate`).
Tested to discriminate both encodings correctly, plus the 60 BPM case
(where a beat is a second, so the test genuinely cannot decide) and
trimmed clips (reported INCONCLUSIVE, not guessed).

Measured the librosa backend against a synthetic reference song with
known ground truth:

| | result | truth |
|---|---|---|
| tempo | 120.003 BPM | 120.000 |
| key | C major | C major |
| chords | C / Am F C G / F G C C | exact match |
| sections | 5 found, boundaries off by ≤14 s | 6 |

Two real bugs found and fixed during that measurement:

- **Tempo estimator.** Onset frames are quantised to the hop size, so
  inter-beat gaps alternate between neighbouring frame counts
  (0.488 / 0.511 s). The median snaps to one of them — 117.4 BPM instead
  of 120. Fixed by fitting the whole grid by least squares. A regression
  test pins it.
- **Section over-segmentation.** Raw spectral clustering emitted 29
  "sections" including half-second fragments. Fixed by snapping
  boundaries to bar lines and absorbing anything under a musical minimum.

## 2. librosa pin (`a9262da`)

`librosa>=0.10` let 1.0.0 in — a major bump never tested against.
Reproduced it under Python 3.12 and re-ran everything:

| version | tempo | beats/downbeats | key | chords |
|---|---|---|---|---|
| 0.11.0 | 120.0029 | 161 / 41 | C major | identical |
| 1.0.0 | 120.0013 | **160 / 40** | C major | identical |
| truth | 120.0000 | 160 / 40 | C major | |

1.0.0 is marginally better. Constraint narrowed to `>=0.11,<2`.

Section *labels* differed between the two versions on byte-identical
input. That instability is recorded because it is independent evidence
that the librosa section path should not be relied on for performance
use.

## 3. Chords from MIDI (`e0cdf7d`, `73d51e7`)

Detected chords are a guess; a chord track someone played is ground
truth. A `.mid` in a song folder overrides the audio path, as the same
`ChordSpan` list at higher confidence.

**Track selection is load-bearing, not cosmetic.** Logic exports every
track into one file, and reading them together is not merely noisier — it
is wrong. A sustained bass note rewrites the harmony:

```
all tracks         C6    Fmaj7/C   C   G7/C
chord track only   Am7   Fmaj7     C   G7
```

Same file. A regression test pins that `C6` so the failure cannot return
silently.

The second commit corrected two choices made for the harder case that got
in the way of the real one (a generated chord track with block chords,
exported alone):

- **Grid sampling → note-boundary segmentation.** Sampling every 125 ms
  added quantisation error at exactly the points that matter. Spans are
  now cut at note starts and ends, so a 2-bar chord at 120 BPM reports
  `0.0 → 4.0` exactly.
- **`track_filter="chord"` default → automatic selection.** A generated
  track is often named `Track 1`, or nothing at all, and a name-match
  default would have read it as no chords. Rule order is now: forced
  all-tracks, explicit filter, the only track with notes whatever it is
  called, a chord-looking name, else everything with the reason stated.
  `explain()` reports which rule fired.

Namer covers triads, sus, 6ths, 7ths, 9ths, power chords and inversions
as slash chords. Scored rather than table-matched, so an unrecognised
voicing degrades to the nearest sane name instead of failing.

## 4. Authored sections and lyrics (`c7fc569`)

Sections were the weakest signal in the project. Rather than tune the
heuristic, authored input now wins outright — from `sections.txt` or from
marker meta events inside the chord MIDI (free when Logic exports them).

Canonical labels (`Verse 1` → `verse`, `Middle 8` → `bridge`) keep
colour-coding and setlist logic reliable, while the authored wording is
preserved separately for display — Live should show `Verse 1`, not
`verse`.

Lyrics come from `.lrc`, chosen over transcription and forced alignment
because it is the only option that cannot be subtly wrong. Whisper
mis-hears sung vowels; aligners drift on held notes. Both produce output
needing proof-reading anyway.

Verified end to end on a folder with stems + chord MIDI + sections +
lyrics: **6/6 sections exact** where detection managed 5/6 with 14 s
errors, chords exact, 6 lyric lines placed, tempo and key still detected.

Consequence: **allin1 is no longer needed**, saving 2.5 GB and slow CPU
runs.

Also added `make serve` (binds `0.0.0.0`) so band members' phones on the
same network can open the UI. Localhost stays the default.

---

## Things deliberately not done

- **`als/builder.py` placement pass.** Needs a real template. Refuses
  rather than emitting a plausible-but-wrong set.
- **allin1 verification.** The adapter follows the documented API but the
  package was never installed (2.5 GB, no GPU available). `available()`
  reports this honestly instead of failing at call time.
- **Lyrics/chord rendering into Live.** Open decision — named clips, real
  MIDI notes, or both on a muted track.

## Known limitations

- Audio chord detection is triads only.
- Section detection without authored input is unreliable; treat the 0.25
  confidence as real.
- A generated `.als` will reference audio by absolute path. Fine locally,
  fatal for any hosted version — see `docs/architecture.md`.
