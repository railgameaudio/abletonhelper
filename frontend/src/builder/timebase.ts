/**
 * Musical time, and the two Live encodings we have evidence for.
 *
 * Live's arrangement time unit is the quarter note, not the bar and not
 * the beat-as-the-meter-defines-it. A bar of 6/8 is three units long,
 * not six. This is read off AbleSet's own Measure Track Generator, which
 * computes a bar as `numerator * {1:4, 2:2, 4:1, 8:.5, 16:.25}[denom]`
 * — i.e. `numerator * 4 / denominator`.
 *
 * Nothing here converts to seconds except `barsToSeconds`, and nothing
 * outside this module should. Same rule as the Python side: seconds are
 * for analysis, quarter notes are for Live, and the boundary is one file.
 */

export type Meter = readonly [numerator: number, denominator: number];

/** Denominators Live's time-signature enum is known to cover. */
const DENOMINATOR_UNITS: Readonly<Record<number, number>> = {
  1: 4,
  2: 2,
  4: 1,
  8: 0.5,
  16: 0.25,
};

/**
 * Base offsets of Live's `EnumEvent` time-signature encoding, read off
 * AbleSet's Measure Track Generator bundle. The value for n/d is
 * `BASE[d] + (n - 1)`, so 4/4 is 201 and 6/8 is 302.
 *
 * Unverified against a real template — see docs/template-spec.md §3.
 * `liveTimeSignature` is the only caller, so when the template arrives
 * there is exactly one place to correct.
 */
const ENUM_BASE: Readonly<Record<number, number>> = {
  1: 0,
  2: 99,
  4: 198,
  8: 297,
  16: 396,
};

export class TimebaseError extends Error {}

function unit(meter: Meter): number {
  const u = DENOMINATOR_UNITS[meter[1]];
  if (u === undefined) {
    throw new TimebaseError(
      `unsupported time signature denominator ${meter[1]}; ` +
        `known: ${Object.keys(DENOMINATOR_UNITS).join(", ")}`,
    );
  }
  if (!Number.isInteger(meter[0]) || meter[0] < 1 || meter[0] > 99) {
    throw new TimebaseError(`time signature numerator out of range: ${meter[0]}`);
  }
  return u;
}

/** Length of one bar in Live time units (quarter notes). */
export function barLength(meter: Meter): number {
  return meter[0] * unit(meter);
}

/** Position of a bar count in Live time units. Bar 1 is time 0. */
export function barsToLiveTime(bars: number, meter: Meter): number {
  return bars * barLength(meter);
}

/**
 * Seconds for a number of bars. Live's tempo is quarter notes per
 * minute regardless of meter, which is why this goes through
 * `barLength` rather than multiplying by the numerator.
 */
export function barsToSeconds(bars: number, meter: Meter, bpm: number): number {
  if (!(bpm > 0)) throw new TimebaseError(`bpm must be positive, got ${bpm}`);
  return (barsToLiveTime(bars, meter) * 60) / bpm;
}

/** Live's `EnumEvent` value for a time signature. */
export function liveTimeSignature(meter: Meter): number {
  unit(meter); // range-checks both halves
  return ENUM_BASE[meter[1]] + (meter[0] - 1);
}
