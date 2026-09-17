import { describe, expect, it } from "vitest";
import { barLength, barsToSeconds, liveTimeSignature, TimebaseError } from "./timebase";
import { parseSongMeta, SongMetaError } from "./songmeta";
import { layoutSong, songLocatorName, sectionLocatorName } from "./ableset";
import { silentWav, silenceFrames, SAMPLE_RATE } from "./silence";

const SONG = `
# a comment line
title:    Follow Night
artist:   Rail
key:      F#m
bpm:      113
meter:    4/4
color:    blue
tags:     #rock #set1
stems:    include
count-in: 2

[sections]
Intro       4
Verse 1     16
Chorus      8    [red]   +LOOP
Middle 8    8            +PAUSE
Outro       8    [gray]  +END
`;

describe("timebase", () => {
  it("measures a bar in quarter notes, not in beats", () => {
    expect(barLength([4, 4])).toBe(4);
    expect(barLength([6, 8])).toBe(3); // six eighths = three quarters
    expect(barLength([3, 4])).toBe(3);
    expect(barLength([5, 4])).toBe(5);
  });

  it("converts bars to seconds through the quarter note", () => {
    // 8 bars of 4/4 at 120 BPM: 32 quarter notes at 0.5 s = 16 s
    expect(barsToSeconds(8, [4, 4], 120)).toBeCloseTo(16, 10);
    // 8 bars of 6/8 at 120: 24 quarter notes = 12 s
    expect(barsToSeconds(8, [6, 8], 120)).toBeCloseTo(12, 10);
  });

  it("encodes Live's time signature enum", () => {
    expect(liveTimeSignature([4, 4])).toBe(201);
    expect(liveTimeSignature([3, 4])).toBe(200);
    expect(liveTimeSignature([6, 8])).toBe(302);
    expect(liveTimeSignature([1, 1])).toBe(0);
  });

  it("refuses a denominator it has no evidence for", () => {
    expect(() => barLength([4, 3])).toThrow(TimebaseError);
    expect(() => barLength([4, 32])).toThrow(TimebaseError);
  });

  it("refuses a nonsense tempo rather than producing Infinity", () => {
    expect(() => barsToSeconds(4, [4, 4], 0)).toThrow(TimebaseError);
  });
});

describe("song.txt", () => {
  it("parses the documented example", () => {
    const m = parseSongMeta(SONG);
    expect(m.title).toBe("Follow Night");
    expect(m.bpm).toBe(113);
    expect(m.meter).toEqual([4, 4]);
    expect(m.color).toBe("blue");
    expect(m.tags).toEqual(["#rock", "#set1"]);
    expect(m.stems).toBe("include");
    expect(m.countIn).toBe(2);
    expect(m.totalBars).toBe(44);
  });

  it("keeps a digit in a section name out of the bar count", () => {
    const m = parseSongMeta(SONG);
    const middle = m.sections.find((s) => s.name === "Middle 8");
    expect(middle).toBeDefined();
    expect(middle!.bars).toBe(8);
    expect(middle!.flags).toEqual(["+PAUSE"]);
  });

  it("assigns start bars cumulatively", () => {
    const m = parseSongMeta(SONG);
    expect(m.sections.map((s) => [s.name, s.startBar])).toEqual([
      ["Intro", 1],
      ["Verse 1", 5],
      ["Chorus", 21],
      ["Middle 8", 29],
      ["Outro", 37],
    ]);
  });

  it("separates colour from flags", () => {
    const chorus = parseSongMeta(SONG).sections[2];
    expect(chorus.color).toBe("red");
    expect(chorus.flags).toEqual(["+LOOP"]);
  });

  it("reports every problem at once, with line numbers", () => {
    let err: SongMetaError | undefined;
    try {
      parseSongMeta("title: X\nbpm: 900\ncolor: beige\n[sections]\nIntro four\n");
    } catch (e) {
      err = e as SongMetaError;
    }
    expect(err).toBeInstanceOf(SongMetaError);
    expect(err!.problems).toHaveLength(3);
    expect(err!.problems.join("\n")).toMatch(/line 2: bpm out of range/);
    expect(err!.problems.join("\n")).toMatch(/line 3: unknown colour/);
    expect(err!.problems.join("\n")).toMatch(/line 5: bar count/);
  });

  it("refuses a song with no tempo rather than assuming 120", () => {
    expect(() => parseSongMeta("title: X\n[sections]\nIntro 4\n")).toThrow(
      /missing required field: bpm/,
    );
  });

  it("rejects a flag AbleSet does not know", () => {
    expect(() => parseSongMeta("title: X\nbpm: 100\n[sections]\nIntro 4 +REWIND\n"))
      .toThrow(/unknown flag/);
  });
});

describe("locator notation", () => {
  const meta = parseSongMeta(SONG);

  it("writes the song locator", () => {
    expect(songLocatorName(meta)).toBe(
      "Follow Night {[F#m] · 113 BPM} [blue] [c:2] #rock #set1",
    );
  });

  it("leaves a plain section locator bare so the clip names it", () => {
    expect(sectionLocatorName(meta.sections[1])).toBe(">");
  });

  it("names the locator when it has to carry a flag", () => {
    // "> +LOOP" would read as a section called "+LOOP".
    expect(sectionLocatorName(meta.sections[2])).toBe("> Chorus +LOOP");
  });
});

describe("layout", () => {
  const meta = parseSongMeta(SONG);

  it("places one measure clip per bar", () => {
    const l = layoutSong(meta);
    expect(l.measures).toHaveLength(44);
    expect(l.measures[0]).toEqual({ time: 0, value: "1" });
    expect(l.measures[43]).toEqual({ time: 172, value: "44" });
  });

  it("does not stack a section locator on top of the song locator", () => {
    const l = layoutSong(meta);
    const atZero = l.locators.filter((x) => x.time === 0);
    expect(atZero).toHaveLength(1);
    expect(atZero[0].value).toMatch(/^Follow Night/);
  });

  it("closes the song with SONG END at the last bar", () => {
    const l = layoutSong(meta);
    const last = l.locators[l.locators.length - 1];
    expect(last.value).toBe("SONG END");
    expect(last.time).toBe(176); // 44 bars * 4
  });

  it("spans the tempo clip across the whole song", () => {
    const l = layoutSong(meta);
    expect(l.tempoClip).toEqual({ time: 0, length: 176, bpm: 113 });
  });

  it("shifts everything by a bar offset, which is what a master set is", () => {
    const l = layoutSong(meta, 44);
    expect(l.locators[0].time).toBe(176);
    expect(l.measures[0]).toEqual({ time: 176, value: "1" }); // bars restart per song
    expect(l.tempoClip.time).toBe(176);
  });
});

describe("silent wav", () => {
  it("is exactly as long as the song", () => {
    // 44 bars of 4/4 at 113 BPM
    const seconds = barsToSeconds(44, [4, 4], 113);
    const frames = silenceFrames({ bars: 44, meter: [4, 4], bpm: 113 });
    expect(frames).toBe(Math.round(seconds * SAMPLE_RATE));
  });

  it("writes a canonical 44-byte RIFF header", () => {
    const wav = silentWav({ bars: 1, meter: [4, 4], bpm: 120 });
    const text = (o: number, n: number) =>
      String.fromCharCode(...wav.slice(o, o + n));
    const u32 = (o: number) => new DataView(wav.buffer).getUint32(o, true);
    const u16 = (o: number) => new DataView(wav.buffer).getUint16(o, true);

    expect(text(0, 4)).toBe("RIFF");
    expect(text(8, 4)).toBe("WAVE");
    expect(text(12, 4)).toBe("fmt ");
    expect(text(36, 4)).toBe("data");
    expect(u16(20)).toBe(1); // PCM
    expect(u16(22)).toBe(1); // mono
    expect(u32(24)).toBe(SAMPLE_RATE);
    expect(u16(34)).toBe(16); // bit depth
    expect(u32(4)).toBe(wav.length - 8);
    expect(u32(40)).toBe(wav.length - 44);
  });

  it("is actually silent", () => {
    const wav = silentWav({ bars: 1, meter: [4, 4], bpm: 120 });
    expect(wav.slice(44).every((b) => b === 0)).toBe(true);
  });
});
