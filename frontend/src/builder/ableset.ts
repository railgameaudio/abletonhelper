/**
 * SongMeta -> the strings AbleSet reads.
 *
 * Every name AbleSet parses is produced here and nowhere else, so the
 * notation lives in one file and can be tested without building a set.
 * Notation reference: ableset.com/docs/locator-notation and /docs/flags.
 */

import type { SectionSpec, SongMeta } from "./songmeta";
import { barsToLiveTime } from "./timebase";

export interface Placed<T> {
  /** Position in Live time units (quarter notes) from the set's start. */
  time: number;
  value: T;
}

/**
 * The song's own locator: title, description, colour, tags.
 *
 * The description carries key and tempo. AbleSet's Cues feature spells
 * out chord symbols found in a description, and its docs say to wrap the
 * chord in square brackets when the description contains more than just
 * the chord — hence `{[F#m] · 113 BPM}`.
 *
 * Caveat worth keeping in view: square brackets are also AbleSet's
 * attribute syntax at the top level of a locator name. Inside `{}` they
 * should be description text, but that is inference from the docs, not
 * something observed. If cues mispronounce or the colour stops
 * applying, `describeKey` is the one place to change.
 */
export function songLocatorName(meta: SongMeta): string {
  const parts = [meta.title];
  const description = describeKey(meta);
  if (description) parts.push(`{${description}}`);
  if (meta.color) parts.push(`[${meta.color}]`);
  if (meta.countIn !== undefined) parts.push(`[c:${meta.countIn}]`);
  parts.push(...meta.tags);
  return parts.join(" ");
}

function describeKey(meta: SongMeta): string {
  const bits: string[] = [];
  if (meta.key) bits.push(`[${meta.key}]`);
  bits.push(`${formatBpm(meta.bpm)} BPM`);
  if (meta.meter[0] !== 4 || meta.meter[1] !== 4) {
    bits.push(`${meta.meter[0]}/${meta.meter[1]}`);
  }
  return bits.join(" · ");
}

function formatBpm(bpm: number): string {
  return Number.isInteger(bpm) ? String(bpm) : bpm.toFixed(2).replace(/0+$/, "");
}

/**
 * The section's *clip* name on the Sections track — the authored wording
 * and nothing else. Colour comes from the clip's own colour because the
 * track carries `+CC`, and flags go on the locator, which is the thing
 * AbleSet can act on mid-song.
 */
export function sectionClipName(section: SectionSpec): string {
  return section.name;
}

/**
 * The section's locator. Bare `>` by default: the clip already carries
 * the name, and a locator is only needed because AbleSet cannot jump to
 * a section clip while Live is playing.
 *
 * Flags and count-in attributes have to live on the locator, so as soon
 * as a section has any, the locator takes the full name too — otherwise
 * `> +LOOP` would read as a section literally called "+LOOP".
 */
export function sectionLocatorName(section: SectionSpec): string {
  const extras = [...section.flags, ...section.attrs];
  if (extras.length === 0) return ">";
  return [`> ${section.name}`, ...extras].join(" ");
}

export const SONG_END_LOCATOR = "SONG END";

export interface SongLayout {
  /** Locators, in time order, including the closing SONG END. */
  locators: Placed<string>[];
  /** One entry per section, for clips on the Sections track. */
  sections: (Placed<string> & { length: number; color?: string })[];
  /** One entry per bar, for clips on the Measures track. */
  measures: Placed<string>[];
  /** Whole-song span for the silent Lead clip on the Tempo track. */
  tempoClip: { time: number; length: number; bpm: number };
  /** Total length in Live time units. */
  length: number;
}

/**
 * Everything the builder needs to place, in Live time units, at a bar
 * offset. The offset is what makes a multi-song master set the same code
 * path as a single-song file — see docs/template-spec.md §7.
 */
export function layoutSong(meta: SongMeta, offsetBars = 0): SongLayout {
  const t = (bars: number) => barsToLiveTime(offsetBars + bars, meta.meter);
  const start = t(0);
  const end = t(meta.totalBars);

  const locators: Placed<string>[] = [
    { time: start, value: songLocatorName(meta) },
  ];
  const sections: SongLayout["sections"] = [];

  for (const s of meta.sections) {
    const at = t(s.startBar - 1);
    // The song locator already sits at bar 1; a second locator in the
    // same place would show up as an empty section in the setlist.
    if (s.startBar > 1) {
      locators.push({ time: at, value: sectionLocatorName(s) });
    }
    sections.push({
      time: at,
      length: barsToLiveTime(s.bars, meta.meter),
      value: sectionClipName(s),
      color: s.color,
    });
  }

  locators.push({ time: end, value: SONG_END_LOCATOR });

  const measures: Placed<string>[] = [];
  for (let bar = 0; bar < meta.totalBars; bar++) {
    measures.push({ time: t(bar), value: String(bar + 1) });
  }

  return {
    locators,
    sections,
    measures,
    tempoClip: { time: start, length: end - start, bpm: meta.bpm },
    length: end - start,
  };
}
