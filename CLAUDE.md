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

## Decided (2026-09-17)

Four decisions that change the shape of the project. Full reasoning in
docs/template-spec.md.

- **Target is AbleSet**, not a bare Live set. The template carries a
  fixed track layout — Sections, Measures, four `+LYRICS` views, Cue,
  Click, Lights, stems, Tempo — and the generator writes into it. See
  docs/template-spec.md §2.
- **Tempo comes from Lead clips, not Main-track automation.** One warped
  silent audio clip per song on a `Tempo` track, switched to Lead, at the
  song's BPM (Live 12 manual §9.1.4). The Tempo track must be the
  bottom-most track — when several clips lead, the lowest track wins.
- **The builder runs in the browser.** A `.als` is gzipped XML, so it
  needs no server; AbleSet's own generators do exactly this, cloning a
  prototype clip out of a bundled template. `frontend/src/builder/` is
  the product; `backend/abletonhelper/analysis/` is an optional local
  tool for songs nobody has marked up. Deploying to DigitalOcean.
- **The rig is a Mac; development is on Windows.** So the project-folder
  export with relative sample paths is required now, not "before this
  could be hosted". A generated `.als` with absolute Windows paths is
  unopenable on the rig.

Division of labour with the sibling repo `railchordchartapp`: that app
owns charts (`Song`, transposition, gig view, PDF); this one owns DAW
files (`.als`, `.mid`, tempo maps, locators). Chart JSON is the contract
between them.

## Next

1. Add `templates/Template.als` (built on the Mac — docs/template-spec.md
   §4), run `abletonhelper inspect` on it, and finish the builder
   placement pass against the measured layout. **Everything is blocked on
   this.**
2. Extend `als/inspect.py` to read MIDI note events and clip names, so an
   existing `.als` yields sections + chords + lyrics. The builder needs
   the same parsing, so this is not a detour.
3. Project-folder export: emit an Ableton Project folder as a zip, with
   relative sample paths. See docs/architecture.md.
4. `song.txt` from a Logic MIDI export — tempo, meter, key, markers and
   chords are all in the file; the missing link is seconds→bars, and the
   tempo map needed for it is already parsed in `analysis/midi_chords.py`.
5. allin1 is optional, not needed: hand-marked sections beat what it
   would detect. Only worth installing for songs nobody will mark up.

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
