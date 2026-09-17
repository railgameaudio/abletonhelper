/**
 * Parser for `song.txt` — the one file you write per song.
 *
 * Format is documented in docs/template-spec.md §5. The parse either
 * returns a complete SongMeta or throws with every problem it found,
 * each with a line number. It never fills in a default for something
 * musical: a missing bpm is an error, not 120.
 */

import type { Meter } from "./timebase";

/** AbleSet's colour vocabulary — locator, section and lyrics colours. */
export const ABLESET_COLORS = [
  "gray", "red", "orange", "amber", "yellow", "lime", "green", "emerald",
  "teal", "cyan", "sky", "blue", "indigo", "violet", "purple", "fuchsia",
  "pink", "rose",
] as const;

export type AblesetColor = (typeof ABLESET_COLORS)[number];

/** Locator flags AbleSet understands on a section. */
export const SECTION_FLAGS = [
  "+LOOP", "+LOOPFULL", "+PAUSE", "+SKIP", "+END",
] as const;

export interface SectionSpec {
  /** Authored wording, shown as-is in Live and AbleSet: "Verse 1". */
  name: string;
  bars: number;
  color?: AblesetColor;
  /** e.g. ["+LOOP"] — passed through to the locator verbatim. */
  flags: string[];
  /** Count-in and other bracketed attributes, e.g. ["[c:2.3:nl]"]. */
  attrs: string[];
  /** Bar number this section starts on, 1-based. Filled in by the parser. */
  startBar: number;
}

export interface SongMeta {
  title: string;
  artist?: string;
  key?: string;
  bpm: number;
  meter: Meter;
  color?: AblesetColor;
  tags: string[];
  stems: "include" | "skip";
  countIn?: number;
  sections: SectionSpec[];
  /** Total length in bars — the sum of the sections. */
  totalBars: number;
}

export class SongMetaError extends Error {
  constructor(readonly problems: string[]) {
    super(`song.txt has ${problems.length} problem(s):\n  ` + problems.join("\n  "));
    this.name = "SongMetaError";
  }
}

const KNOWN_KEYS = new Set([
  "title", "artist", "key", "bpm", "meter", "color", "colour", "tags",
  "stems", "count-in",
]);

const LOOKS_LIKE_ATTR = /^\[[^\]]+\]$/;
const LOOKS_LIKE_FLAG = /^\+[A-Z]+(:\d+)?$/;

function stripComment(line: string): string {
  // A '#' inside `tags:` is data, not a comment, so only treat '#' as a
  // comment when it is preceded by whitespace or starts the line.
  const m = line.match(/(^|\s)#(?!\w*\s*$)/);
  return m && !line.trimStart().startsWith("tags:") ? line.slice(0, m.index) : line;
}

export function parseSongMeta(text: string): SongMeta {
  const problems: string[] = [];
  const lines = text.split(/\r?\n/);

  const fields = new Map<string, { value: string; line: number }>();
  const sectionLines: { raw: string; line: number }[] = [];
  let inSections = false;
  let sawSectionsHeader = false;

  lines.forEach((raw, i) => {
    const lineNo = i + 1;
    let line = raw.trimStart().startsWith("#") ? "" : stripComment(raw);
    line = line.trim();
    if (!line) return;

    if (/^\[sections\]$/i.test(line)) {
      inSections = true;
      sawSectionsHeader = true;
      return;
    }

    if (inSections) {
      sectionLines.push({ raw: line, line: lineNo });
      return;
    }

    const colon = line.indexOf(":");
    if (colon < 0) {
      problems.push(`line ${lineNo}: expected "key: value", got ${JSON.stringify(line)}`);
      return;
    }
    const key = line.slice(0, colon).trim().toLowerCase();
    const value = line.slice(colon + 1).trim();
    if (!KNOWN_KEYS.has(key)) {
      problems.push(
        `line ${lineNo}: unknown field ${JSON.stringify(key)}; known: ` +
          [...KNOWN_KEYS].join(", "),
      );
      return;
    }
    if (fields.has(key)) {
      problems.push(`line ${lineNo}: ${key} given twice`);
      return;
    }
    fields.set(key === "colour" ? "color" : key, { value, line: lineNo });
  });

  const get = (k: string) => fields.get(k)?.value;

  const title = get("title");
  if (!title) problems.push("missing required field: title");

  let bpm = NaN;
  const bpmRaw = get("bpm");
  if (bpmRaw === undefined) {
    problems.push("missing required field: bpm");
  } else {
    bpm = Number(bpmRaw);
    if (!Number.isFinite(bpm) || bpm <= 0 || bpm > 400) {
      problems.push(`line ${fields.get("bpm")!.line}: bpm out of range: ${bpmRaw}`);
    }
  }

  let meter: Meter = [4, 4];
  const meterRaw = get("meter");
  if (meterRaw !== undefined) {
    const m = meterRaw.match(/^(\d+)\s*\/\s*(\d+)$/);
    if (!m) {
      problems.push(`line ${fields.get("meter")!.line}: meter must look like 4/4, got ${JSON.stringify(meterRaw)}`);
    } else {
      meter = [Number(m[1]), Number(m[2])];
    }
  }

  let color: AblesetColor | undefined;
  const colorRaw = get("color");
  if (colorRaw !== undefined) {
    const c = colorRaw.toLowerCase();
    if (!(ABLESET_COLORS as readonly string[]).includes(c)) {
      problems.push(
        `line ${fields.get("color")!.line}: unknown colour ${JSON.stringify(colorRaw)}; ` +
          `AbleSet knows: ${ABLESET_COLORS.join(", ")}`,
      );
    } else {
      color = c as AblesetColor;
    }
  }

  const tags: string[] = [];
  const tagsRaw = get("tags");
  if (tagsRaw) {
    for (const t of tagsRaw.split(/\s+/)) {
      if (!t.startsWith("#")) {
        problems.push(`line ${fields.get("tags")!.line}: tags must start with #, got ${JSON.stringify(t)}`);
      } else {
        tags.push(t);
      }
    }
  }

  let stems: "include" | "skip" = "include";
  const stemsRaw = get("stems");
  if (stemsRaw !== undefined) {
    const s = stemsRaw.toLowerCase();
    if (s !== "include" && s !== "skip") {
      problems.push(`line ${fields.get("stems")!.line}: stems must be "include" or "skip", got ${JSON.stringify(stemsRaw)}`);
    } else {
      stems = s;
    }
  }

  let countIn: number | undefined;
  const ciRaw = get("count-in");
  if (ciRaw !== undefined) {
    const n = Number(ciRaw);
    if (![0, 1, 2].includes(n)) {
      problems.push(`line ${fields.get("count-in")!.line}: count-in must be 0, 1 or 2, got ${JSON.stringify(ciRaw)}`);
    } else {
      countIn = n;
    }
  }

  if (!sawSectionsHeader) problems.push("missing [sections] block");

  const sections: SectionSpec[] = [];
  let bar = 1;
  for (const { raw, line } of sectionLines) {
    const parsed = parseSectionLine(raw, line, problems);
    if (!parsed) continue;
    parsed.startBar = bar;
    bar += parsed.bars;
    sections.push(parsed);
  }
  if (sawSectionsHeader && sections.length === 0 && sectionLines.length === 0) {
    problems.push("[sections] block is empty — a song needs at least one section");
  }

  if (problems.length) throw new SongMetaError(problems);

  return {
    title: title!,
    artist: get("artist"),
    key: get("key"),
    bpm,
    meter,
    color,
    tags,
    stems,
    countIn,
    sections,
    totalBars: bar - 1,
  };
}

function parseSectionLine(
  raw: string,
  line: number,
  problems: string[],
): SectionSpec | null {
  const tokens = raw.split(/\s+/);
  const flags: string[] = [];
  const attrs: string[] = [];
  let color: AblesetColor | undefined;

  // Peel trailing flags and bracketed attributes off the right. The name
  // may contain spaces and digits ("Middle 8"), so the bar count is
  // whatever integer is left at the end once these are gone.
  while (tokens.length) {
    const last = tokens[tokens.length - 1];
    if (LOOKS_LIKE_FLAG.test(last)) {
      const base = last.split(":")[0];
      if (!(SECTION_FLAGS as readonly string[]).includes(base)) {
        problems.push(
          `line ${line}: unknown flag ${JSON.stringify(last)}; AbleSet knows: ` +
            SECTION_FLAGS.join(", "),
        );
      }
      flags.unshift(last);
      tokens.pop();
    } else if (LOOKS_LIKE_ATTR.test(last)) {
      const inner = last.slice(1, -1).toLowerCase();
      if ((ABLESET_COLORS as readonly string[]).includes(inner)) {
        color = inner as AblesetColor;
      } else if (inner.startsWith("c:")) {
        attrs.unshift(last);
      } else {
        problems.push(
          `line ${line}: ${JSON.stringify(last)} is neither an AbleSet colour ` +
            `nor a count-in attribute like [c:2]`,
        );
      }
      tokens.pop();
    } else {
      break;
    }
  }

  const barsTok = tokens.pop();
  if (barsTok === undefined) {
    problems.push(`line ${line}: no bar count`);
    return null;
  }
  const bars = Number(barsTok);
  if (!Number.isInteger(bars) || bars < 1) {
    problems.push(
      `line ${line}: bar count must be a whole number of bars, got ${JSON.stringify(barsTok)}`,
    );
    return null;
  }

  const name = tokens.join(" ").trim();
  if (!name) {
    problems.push(`line ${line}: section has a bar count but no name`);
    return null;
  }

  return { name, bars, color, flags, attrs, startBar: 0 };
}
