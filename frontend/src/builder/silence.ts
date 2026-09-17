/**
 * The silent WAV behind the tempo track.
 *
 * The Tempo track holds one warped audio clip per song, switched to
 * Lead, and Live takes the set's tempo from that clip's warp markers
 * (Live 12 manual §9.1.4). So the clip needs a real audio file, and the
 * simplest file that can carry a tempo is silence cut to exactly the
 * song's length.
 *
 * Cutting it to length matters: if the file is exactly `bars` long at
 * `bpm`, then warp markers at the first and last sample describe that
 * tempo and nothing has to be interpolated. A generic 60-second blob
 * would need markers placed at computed offsets, which is arithmetic
 * that can be wrong. This cannot.
 *
 * Silence deflates to almost nothing, so a four-minute 48 kHz file
 * costs ~23 MB raw and a few KB inside the project zip.
 */

import { barsToSeconds, type Meter } from "./timebase";

export const SAMPLE_RATE = 48000;
const CHANNELS = 1;
const BITS_PER_SAMPLE = 16;

export interface SilenceSpec {
  bars: number;
  meter: Meter;
  bpm: number;
}

/** Sample count for a song's tempo clip, rounded to a whole sample. */
export function silenceFrames({ bars, meter, bpm }: SilenceSpec): number {
  const seconds = barsToSeconds(bars, meter, bpm);
  return Math.round(seconds * SAMPLE_RATE);
}

/**
 * A mono 16-bit PCM WAV of pure silence, exactly `bars` long at `bpm`.
 *
 * Canonical 44-byte RIFF header, no extension chunks — Live reads it and
 * so does everything else.
 */
export function silentWav(spec: SilenceSpec): Uint8Array {
  const frames = silenceFrames(spec);
  const blockAlign = (CHANNELS * BITS_PER_SAMPLE) / 8;
  const dataBytes = frames * blockAlign;
  const buffer = new ArrayBuffer(44 + dataBytes);
  const view = new DataView(buffer);

  const ascii = (offset: number, s: string) => {
    for (let i = 0; i < s.length; i++) view.setUint8(offset + i, s.charCodeAt(i));
  };

  ascii(0, "RIFF");
  view.setUint32(4, 36 + dataBytes, true);
  ascii(8, "WAVE");

  ascii(12, "fmt ");
  view.setUint32(16, 16, true); // PCM fmt chunk size
  view.setUint16(20, 1, true); // format: PCM
  view.setUint16(22, CHANNELS, true);
  view.setUint32(24, SAMPLE_RATE, true);
  view.setUint32(28, SAMPLE_RATE * blockAlign, true); // byte rate
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, BITS_PER_SAMPLE, true);

  ascii(36, "data");
  view.setUint32(40, dataBytes, true);
  // The sample data is already zeroes — an ArrayBuffer starts zeroed,
  // and zero is silence in signed PCM.

  return new Uint8Array(buffer);
}
