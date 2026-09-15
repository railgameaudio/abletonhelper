# What goes in a song folder

Everything is optional except the audio. Each authored file replaces a
detected guess with ground truth.

```
songs/my-song/
├── Kick.wav            audio stems -- the only required part
├── Bass DI.wav
├── LeadVox.wav
├── Chords.mid          authored chords      -> replaces detection
├── sections.txt        authored arrangement -> replaces detection
└── lyrics.lrc          timed lyrics         -> nothing else provides these
```

## Authored beats detected, always

| Signal | Detected | Authored | Why it matters |
|---|---|---|---|
| Tempo / key | reliable | — | detection is fine, 0.002% error |
| Chords | triads only | exact, with 7ths and inversions | `Chords.mid` |
| **Sections** | **weak** | **exact** | `sections.txt` or MIDI markers |
| Lyrics | impossible | exact | `lyrics.lrc` |

Detected sections were the worst signal in the project: 5 found where
there were 6, boundaries off by up to 14 seconds, and the labels changed
between librosa versions on identical input. Marking the arrangement by
hand removes that problem completely — and removes the reason to install
`allin1` at all.

Authored results carry `confidence = 1.0`; detected sections carry 0.25.

## sections.txt

```
# comments are fine
0:00   Intro
0:08   Verse 1
0:24   Chorus
1:12   Gtr Solo
2:04   Outro
```

Times may be `mm:ss`, `mm:ss.cc`, or plain seconds. Separator is
whitespace, comma, tab or `=`. Order does not matter; marks are sorted.
Each section runs until the next one starts, and the last runs to the end
of the audio.

Names are mapped onto canonical labels (`Verse 1` → `verse`, `Middle 8` →
`bridge`, `Pre-Chorus` → `prechorus`) so colour-coding and setlist logic
can rely on them — while your original wording is kept for display, so
Live shows `Verse 1`, not `verse`.

**Alternative: MIDI markers.** If Logic writes its arrangement markers
into the MIDI export, they are read straight out of `Chords.mid` and no
sections file is needed. An explicit `sections.txt` wins if both exist.
Check with:

```bash
python -c "from abletonhelper.analysis.sections import sections_from_midi_markers as f; print(f('songs/my-song/Chords.mid', 200))"
```

Empty result means Logic did not export them — use the text file.

## lyrics.lrc

Standard LRC, the karaoke format:

```
[ar:The Band]
[ti:Song Name]
[offset:+500]
[00:12.50]First line
[00:15.30]Second line
[00:18.00][01:02.40]A line that comes back twice
```

Supported: `mm:ss`, `mm:ss.cc`, `mm:ss.mmm`; multiple timestamps on one
line for repeated lyrics; `[offset:]` in milliseconds; enhanced-LRC
per-word tags (stripped, not yet used). A line runs until the next one
begins.

This was chosen over transcription or forced alignment deliberately: it
is the only option that cannot be subtly wrong. Whisper mis-hears sung
vowels, and aligners drift on held notes — both produce output you would
have to proof-read anyway.
