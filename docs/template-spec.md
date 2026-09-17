# Template.als — what to build by hand, and why

`als/builder.py` clones structure out of a real template rather than
synthesising Live XML (CLAUDE.md, constraint 1). This document is the
spec for that template: every track the generator writes into, every
prototype clip it needs to copy, and the reasoning behind each.

Build it once in Live, save it to `templates/Template.als`, and run
`python -m abletonhelper.cli inspect templates/Template.als`. Everything
below is chosen so that report can be turned into a builder without a
single guessed field.

Sources: AbleSet docs (locator-notation, sections-track, lyrics,
guide-tracks, cues, mixer, measure-track, multi-file-projects, flags) and
the Live 12 manual §9.1.4 Clip Tempo Followers and Leaders.

---

## 1. The tempo strategy

No tempo automation drawn by hand on the Main track. Instead: an audio
track at the **bottom** of the set holding one warped, silent audio clip
per song, each clip switched to **Lead** in Clip View's Audio Utilities
panel.

The Live 12 manual, §9.1.4:

> When a clip is set to Lead, the Set plays back at the tempo determined
> by the clip's Warp Markers. [...] Any number of clips can be set as
> tempo leaders, but only one clip at a time can actually determine the
> tempo. When multiple clips on different tracks are leaders, the tempo
> of the currently playing clip on the **bottom-most track** will take
> precedence.

Three consequences that shape the template:

1. **The Tempo track must be the last track in the set.** If an imported
   stem ever ends up as a leader, the bottom-most track wins — so the
   tempo track has to be below every stem, not above them.
2. **Lead only works on Arrangement clips**, and only on audio clips. It
   is an audio track, not MIDI.
3. Live writes the tempo automation into the Main track itself, read
   only. That is fine — nothing downstream edits it. Note that
   `Unfollow Tempo Automation` in the tempo field's context menu is a
   one-way door: it converts every leader clip back to a follower and
   makes the automation editable. Do not use it on a generated set.

The clip is silence, so a song whose original recording drifts still gets
a rock-steady grid (goal 3).

---

## 2. Track list

Order matters in four places, all noted below. Everything else is
cosmetic.

| # | Track name | Type | Purpose |
|---|---|---|---|
| 1 | `Sections +CC` | MIDI | AbleSet sections track — one empty clip per section |
| 2 | `Measures` | MIDI | per-song bar numbers — one clip per bar |
| 3 | `Lyrics +LYRICS [top+2]` | MIDI | plain timed lyrics |
| 4 | `Chord Chart +LYRICS [mono] [left] [nofade] [nozoom]` | MIDI | bar-grid chart |
| 5 | `Chords & Lyrics +LYRICS` | MIDI | ChordPro — chords above words |
| 6 | `Sheet Music +LYRICS [full]` | MIDI | one `[img:...]` clip per page |
| 7 | `Lights` | MIDI | reserved, empty for now |
| 8 | `Cue +NM` | MIDI | hosts the AbleSet Cues VST3 |
| 9 | `Click +NM` | audio | click; AbleSet auto-groups anything named Click |
| 10+ | `Drums +G:DRUMS`, `Bass +G:BASS`, … | audio | stem prototypes |
| last | `Tempo +NM` | audio | tempo leader clips — **must be bottom-most** |

**Order-sensitive points**

- `Tempo` bottom-most — §1 above.
- Only one sections track is honoured; if several are marked, AbleSet
  uses the first. Keep `Sections` at the top so it can never lose.
- AbleSet **Intro displays only the first lyrics track**. Standard and
  Pro support all of them. Track 3 is first because plain lyrics is the
  safest fallback view.
- Tracks inside collapsed Live group tracks do not report meter levels to
  AbleSet. If stems get grouped, leave the group expanded.

**Flags used, and why**

- `+CC` on `Sections` makes AbleSet take section colours from the clip
  colour, so the generator sets colour in one place instead of writing
  `[blue]` into every clip name.
- `+NM` (`+NEVERMUTE`) on `Cue`, `Click` and `Tempo` keeps them audible
  when a mixer group is soloed from the web app. On `Tempo` it is
  belt-and-braces: track mute should not affect tempo leading, but that
  is worth confirming rather than assuming.
- `+G:NAME` puts stems into mixer groups. Group names must be uppercase,
  letters/digits/dashes/underscores only; `_` renders as a space.
- `Lights` carries no flag yet. When the lighting rig is decided it
  becomes either a plain MIDI track or `Lights +OSC [ip:port]` for an
  OSC-driven desk — the track exists now so the layout does not shift.

---

## 3. Prototype clips the builder needs

The builder copies clip nodes out of the template, so the template must
contain **at least two** of every clip kind it will emit. Two, not one:
one clip shows the structure, the difference between two shows which
fields carry the varying data.

| Track | Put in the template | What it pins down |
|---|---|---|
| `Tempo` | 2 audio clips from the **same** silent WAV, both Warp on, both **Lead**, at two clearly different tempos (e.g. 100 and 137 BPM) and two different lengths | which fields encode clip tempo, loop length, and the Lead flag |
| `Sections` | 2 empty MIDI clips, differently named, **different colours**, different lengths | clip name, colour index, start/length |
| `Measures` | 2 empty MIDI clips named `1` and `2`, one bar each, back to back | the cheapest possible repeated node |
| each `+LYRICS` track | 2 clips with real text — include one with a `\` line break and one with `**bold**` | that clip names survive punctuation |
| `Sheet Music` | 2 clips named `[img:test/page-1.png]`, `[img:test/page-2.png]` | nothing special, but keeps the shape uniform |
| `Click` | 1 warped audio clip | audio clip prototype in the **follower** state, to contrast with `Tempo` |
| each stem track | 1 warped audio clip, any file | stem placement prototype |
| `Cue` | the AbleSet Cues plugin loaded, no clips | device chain node to clone |

Two tempos at two lengths is the important one. It is the difference
between reading the tempo encoding off the file and guessing it.

**This is also how AbleSet's own generators work.** Reading the bundle
behind the Measure Track Generator: it parses a bundled template with
`DOMParser`, walks `MidiTrack → ClipTimeable` to the first clip,
`cloneNode(true)`s it once per measure, sets only `Id`, `Time`, `Name`,
`CurrentStart` and `CurrentEnd`, removes the prototype, serialises with
`XMLSerializer` and gzips the result to `.als`. If the template is
missing any of those nodes it throws `Missing elements in the template`
rather than emitting a file. Same method, same refusal — independent
confirmation that cloning a prototype is the correct approach, not a
cautious one.

Their time-signature encoding, also read off that bundle, is worth
recording since we will need it for `meter`:

    EnumEvent Value = {1:0, 2:99, 4:198, 8:297, 16:396}[denominator]
                      + (numerator - 1)

so 4/4 is 201 and 6/8 is 302. Verify against the template before relying
on it.

### Also place, in the template

- A song locator at bar 1: `Test Song {F#m · 113} [blue] #test`
- Two section locators, `>` and `>> Chorus`, on downbeats
- A `SONG END` locator

That covers each locator form the generator emits, so `inspect` reports
how Live stores locator names and positions.

---

## 4. Build steps in Live

1. New set. Delete the default tracks.
2. Create the tracks in §2, **in that order**, with the names exactly as
   written including flags and spaces.
3. Make a silent WAV — any length, 48 kHz, mono is fine — and keep it in
   the project's `Samples/Imported/` folder. Drop two copies onto the
   `Tempo` track in **Arrangement** view.
4. For each: Clip View → Audio Utilities → Warp **on**, then set the
   Lead/Follow toggle to **Lead**. Set one to 100 BPM and the other to
   137 BPM, and give them different bar lengths.
5. Add the clips from §3 to every other track.
6. Load **AbleSet Cues** onto the `Cue` track. On macOS this needs
   Live → Preferences → Plug-Ins → *Use VST3 Plug-In System Folders*
   enabled, then Rescan. (On Windows it would instead be *Use VST3
   Plug-In Custom Folder* pointed at
   `%LOCALAPPDATA%\Programs\Common\VST3` — noted only because the
   generator runs on Windows even though the rig does not.)
7. Add the three locators from §3.
8. Create a `Lyrics/` folder inside the Live project folder — that is
   where AbleSet reads sheet-music images from, by relative path.
9. Save as `templates/Template.als`, then:

```bash
git check-ignore -v templates/Template.als   # must print NOTHING
python -m abletonhelper.cli inspect templates/Template.als
```

`*.als` is input and must never be ignored — see docs/assets.md.

---

## 5. Song metadata format

One folder per song. Only `song.txt` and the stems are read; everything
else is optional and each optional file replaces a guess with ground
truth.

```
songs/follow-night/
├── song.txt          required
├── Kick.wav          stems (skippable — see `stems:`)
├── Bass DI.wav
├── LeadVox.wav
├── lyrics.lrc        timed lyrics        → Lyrics track
├── chords.pro        ChordPro            → Chords & Lyrics track
├── chart.txt         bar grid            → Chord Chart track
└── sheet/            page images         → Sheet Music track
```

`song.txt`:

```
title:    Follow Night
artist:   Rail
key:      F#m
bpm:      113
meter:    4/4
color:    blue
tags:     #rock #set1
stems:    include        # include | skip
count-in: 2              # optional, becomes [c:2] on the song locator

[sections]
Intro       4
Verse 1     16
Pre         8    [amber]
Chorus      8    [red]   +LOOP
Verse 2     16
Chorus      8    [red]
Middle 8    8            +PAUSE
Chorus      16   [red]
Outro       8    [gray]  +END
```

**Bar counts, not timestamps.** Bars are what gets written on a chart,
they survive a tempo change, and they make the `Measures` track fall out
for free. Seconds are derived from `bpm` and `meter`, never entered.

Per-section trailing tokens are passed through to AbleSet: `[colour]`
and any of the locator flags (`+LOOP`, `+LOOPFULL`, `+PAUSE`, `+SKIP`,
`+END`), plus count-in attributes like `[c:1]` or `[c:2.3:nl]`.

`stems: skip` produces goal 3: a clean cue project with tempo, sections,
measures, cues and the lyrics views, and no audio. This is the right
default for anything recorded without a click.

---

## 6. What the generator writes, per song

Given the above, for one song it emits:

- a song locator at bar 1 — `Follow Night {F#m · 113} [blue] #rock`
- one empty MIDI clip per section on `Sections`, coloured, named with the
  authored wording (`Verse 1`, not `verse`)
- a bare `>` locator at each section start, because **section clips
  cannot be jumped to while Live is playing** — the clip carries the
  name and colour, the locator makes it reachable mid-song
- one clip per bar on `Measures`, numbered from 1 within the song
- one silent, warped, **Lead** clip on `Tempo` spanning the whole song at
  `bpm`
- lyrics / chart / chords / sheet clips where the source files exist
- stems on their tracks, unless `stems: skip`
- a `SONG END` locator at the last bar

---

## 7. One song per file, and the master set

AbleSet's multi-file mode takes a folder of `.als` files, one song each,
and builds the setlist from them. Its caveat is explicit: *one project
file can currently only contain one song*. Song order, notes, colour and
duration can live in the filename:
`03 Follow Night {capo 1} [blue] [3.42].als`.

So there are two outputs from the same data, and goal 7 is satisfied by
generating rather than merging — Live offers no way to splice projects
together, but nothing needs splicing if both come out of the same
description:

- `build <song>/` → one `.als` per song, for multi-file mode
- `build-set <setlist>` → every song laid end to end on one timeline at
  increasing bar offsets, for a single master set

The second is the first with a bar offset and no reset, which is why the
generator should carry an offset from the start even while only ever
being called with zero.

---

## 8. The rig is a Mac; the generator runs on Windows

This is decided, and it changes the order of work. A generated `.als`
that references audio by absolute Windows path is unopenable on the Mac —
so the project-folder export that `docs/architecture.md` files under
"required before this could ever be hosted" is required *now*, for the
ordinary case.

What that means concretely:

- Every build emits a real **Ableton Project folder**, not a bare `.als`:
  the set, a `Samples/Imported/` folder holding the silent tempo WAV and
  any copied stems, and a `Lyrics/` folder for sheet images.
- Sample references are written with the relative path and the matching
  relative-path type, so Live resolves them inside the project folder
  regardless of which machine opens it.
- Path separators and drive letters never reach the file. The one
  absolute path Live also stores is a hint; it must not be the only
  reference.

The template itself is built on the Mac and copied back to
`templates/Template.als`. `inspect` then reports the Mac-written
encoding, which is the one the builder has to reproduce — so no
Windows-authored reference file should ever be used to derive the format.

---

## 9. Where the builder runs

Decided: the builder is **TypeScript running in the browser**, deployed
as a static site to DigitalOcean. The Python analysis stays, local-only.

A `.als` is a gzipped XML document, so nothing about writing one needs a
server. AbleSet's own generators prove the shape — the Measure Track
Generator parses a bundled template, clones a prototype clip per
measure, serialises and gzips it, entirely client-side (§3).

What follows from that:

- **The template ships inside the app.** `templates/Template.als` becomes
  a bundled asset, the way AbleSet bundles theirs.
- **Stems are never uploaded.** The browser reads the dropped folder and
  writes a zip of a complete Ableton Project folder. No server storage,
  no upload wait, and the stems never leave the machine.
- **The silent tempo WAV is generated in JS** — see `silence.ts`. It is
  zeroes, and it deflates to nothing inside the zip.
- **The analysis path cannot follow.** librosa needs Python. But a
  `song.txt` supplies tempo, key and section bar counts directly, so the
  browser app needs no analysis at all. Detection is the fallback for
  songs nobody has marked up, not the main path.

The split is therefore: `frontend/src/builder/` is the product,
`backend/abletonhelper/analysis/` is an optional local tool. They share a
vocabulary, not code.

---

## Open questions

Recorded here so they are not silently decided:

1. **Live version on the Mac.** 12.3 is installed on the Windows machine,
   but the rig's version is what the template will be written by, and the
   `inspect` timebase check has never been run against a real Live 12
   file. `inspect` reports it — confirm before writing the builder.
2. **Does track mute affect a Lead clip?** `+NM` sidesteps it, but it
   should be tested.
3. **Cue track type.** The Cues plugin is a VST3; whether it loads as an
   instrument (MIDI track) or an effect (audio track) decides track 8's
   type. §2 assumes MIDI.

Settled:

- **AbleSet tier** — Standard or Pro, so all four lyrics tracks are live
  and each device can pick its view.
- **Outputs** — per-song `.als` for multi-file mode first, single
  concatenated master set second, both from the same description (§7).
- **Rig** — Mac (§8).
