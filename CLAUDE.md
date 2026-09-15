# abletonhelper

Turn a folder of song stems into a performance-ready Ableton Live set:
analyse each song (tempo, key, chords, **sections**), order songs into a
setlist, and write a Live set built from a real user template.

Runs locally as a web app today; built so it can become a hosted service
without a rewrite.

## Layout

    backend/abletonhelper/
      analysis/    swappable analyzers -> AnalysisResult   (see docs/analysis.md)
      als/         inspect + build Live sets
      library.py   stem discovery + analysis orchestration
      jobs.py      background work (thread pool today)
      db.py        SQLAlchemy / SQLite
      main.py      FastAPI
      cli.py       `python -m abletonhelper.cli`
    frontend/      React + Vite
    templates/     Template.als  <- REQUIRED INPUT, must be committed
    songs/         one folder of stems per song
    out/           generated sets

## Hard constraints

1. **Never guess Live's XML.** The builder clones structure out of the
   user's real template. Hand-written Live XML breaks on Live updates and
   fails in ways that look fine until playback.

2. **Never assume the clip timebase.** Whether an unwarped clip's
   `Loop/LoopStart`, `LoopEnd`, `StartRelative` are beats or seconds is
   *measured*, not remembered — `als/inspect.py::timebase_evidence`
   compares loop length against the sample's true duration from
   `SampleRef` (`DefaultDuration / SampleRate`). `TimeBase.loop_value()`
   raises rather than guess when the units are unknown. This is verified
   to discriminate correctly in both directions against synthetic sets;
   it has **not** yet been run against a real Live 12 template.

3. **Seconds everywhere in analysis.** `AnalysisResult` is always
   seconds. Conversion to Ableton units happens only in `als/timebase.py`.

4. **Never ignore `*.als`.** It is input. See docs/assets.md — the
   failure mode is a silent push that omits the template.

5. **Report confidence honestly.** Heuristic section labels ship at
   `confidence = 0.25` and the UI says so. A wrong chorus marker on stage
   is worse than no marker.

## State

Working and tested:
- librosa backend — tempo 0.002% error, key correct, chords correct on
  the synthetic test; **sections weak** (5 found vs 6 true, boundaries
  off by up to 14 s)
- verified on librosa 0.11.0 (py3.11) and 1.0.0 (py3.12). Tempo, key and
  chords agree across both; 1.0.0 gets the beat count exactly right
  (160/40 vs 161/41). Section *labels* differ between versions on
  identical input — further evidence the librosa section path is not
  trustworthy for performance use.
- `als/inspect.py` — verified to distinguish BEATS from SECONDS encoding
- FastAPI: import -> analyze job -> poll -> persisted result, exercised
  end to end
- React UI: song library, analysis run, section timeline. Builds clean
  under strict TS.
- Authored inputs override detection (`analysis/sections.py`,
  `analysis/lyrics.py`): `sections.txt` or MIDI markers for arrangement,
  `.lrc` for timed lyrics. Authored data ships at confidence 1.0.
  Verified end to end: authored sections hit 6/6 exact where detection
  managed 5/6 with 14 s errors. See docs/song-folder.md.
- MIDI chord import (`analysis/midi_chords.py`) — reads an authored chord
  track and overrides detected chords. Track selection is automatic: a
  lone chord track is used whatever it is named. Segmentation is at note
  boundaries, so block-chord spans are exact. Selection is load-bearing,
  not cosmetic: reading every track at once turns Am7 into C6. See
  docs/chords.md.

Written but NOT verified:
- `analysis/allin1_backend.py` — follows the documented allin1 API; the
  package is not installed here (~2.5 GB, needs torch). `available()`
  reports this honestly.

Deliberately unfinished:
- `als/builder.py` — raises `NotImplementedError` in the placement pass.
  It needs a real `templates/Template.als` to clone track/clip layout
  from. It refuses rather than emitting a plausible-but-wrong set.

## Next

1. Add `templates/Template.als`, run `abletonhelper inspect` on it, and
   finish the builder placement pass against the measured layout.
2. allin1 is now optional, not needed: hand-marked sections beat what it
   would detect. Only worth installing for songs nobody will mark up.
3. Setlist -> arrangement: section markers become Live locators, and
   chord spans become a chord lane. Rendering choice is open — see
   docs/chords.md.
4. Project-folder export with relative sample paths — required before
   this can ever be hosted. See docs/architecture.md.

## Commands

    make dev            # API on :8000 and UI on :5173
    make serve          # API on 0.0.0.0 so phones on the LAN can reach it
    make api            # API only
    make check          # import checks, TS build, smoke test

    python -m abletonhelper.cli backends
    python -m abletonhelper.cli analyze songs/<song>/
    python -m abletonhelper.cli inspect templates/Template.als
    python -m abletonhelper.cli chords songs/<song>/Chords.mid
    python -m abletonhelper.cli chords songs/<song>/Chords.mid --tracks
