# Chords

Two sources, one representation.

| Source | Confidence | Notes |
|---|---|---|
| Audio analysis (librosa) | ~0.9 per span | triads only, no extensions, no inversions |
| **Authored MIDI** (Logic export) | **0.99** | whatever you actually played |

Both produce a `ChordSpan` list, so nothing downstream cares where the
chords came from. When a song folder contains a chord MIDI it **wins** —
`library.analyze_song` overwrites the detected chords with the authored
ones and sets `meta.chords_authored = True`.

## Getting chords out of Logic

Export the chord/pad region as MIDI into the song's folder:

```
songs/my-song/
├── Kick.wav
├── Bass DI.wav
├── LeadVox.wav
└── Chords.mid        <- picked up automatically
```

Naming it with `chord`, `harmony` or `prog` is what makes it get found. A
folder with exactly one `.mid` also works. Two unnamed MIDI files is
ambiguous and the scanner takes neither, rather than guessing wrong.

## Track filtering matters

Logic exports **every** track into one MIDI file. Reading all of them at
once is actively wrong — a sustained bass note rewrites the harmony:

```
all tracks:          C6    Fmaj7/C   C   G7/C
filtered to chords:  Am7   Fmaj7     C   G7
```

Same file. The first reading is garbage. That is why extraction defaults
to `track_filter="chord"` and only falls back to reading everything when
no track name matches. There is a regression test pinning this exact
behaviour.

Check what is in a file before trusting it:

```bash
python -m abletonhelper.cli chords songs/my-song/Chords.mid --tracks
python -m abletonhelper.cli chords songs/my-song/Chords.mid --track "Piano"
```

## What the namer handles

Triads (maj, min, dim, aug), sus2/sus4, 6/m6, 7/maj7/m7/mMaj7/m7b5/dim7,
7sus4, add9/madd9, 9/maj9/m9, power chords, and inversions as slash
chords (`C/E`, `C/G`). `--flats` spells `Db` instead of `C#`.

Scoring balances matched tones against missing and extra ones, with a
small bonus for root position and a preference for simpler spellings on
ties. It names a chord for whatever is sounding on a 1/8-second grid,
merges equal neighbours, and absorbs anything under 0.4 s so passing
notes do not become chords.

## Rendering a chord lane into Live

Not built yet — it needs `templates/Template.als` like the rest of the
builder. The options, which differ in how they behave on stage:

1. **MIDI clips with the actual notes.** Playable, audible if you assign
   an instrument, visible in the piano roll. Not readable at a glance
   from across a stage.
2. **Named empty clips.** One clip per chord on a dedicated track, each
   named `Am7`, `Fmaj7`. Live shows clip names in the arrangement, so
   this reads as a chord lane at a glance. Silent.
3. **Both.** Named clips that also contain the notes — readable *and*
   usable as a cue. Mute the track and it is purely visual.
4. **Locators.** Live's own timeline markers. Global, not a lane, and
   they compete with section markers for the same strip. Probably wrong
   for chords.

Option 3 is the default worth building unless there is a reason not to.
