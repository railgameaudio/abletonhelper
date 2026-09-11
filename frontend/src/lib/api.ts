export interface Section {
  start: number; end: number; label: string; confidence: number;
}
export interface ChordSpan {
  start: number; end: number; chord: string; confidence: number;
}
export interface Analysis {
  duration: number; tempo: number; time_signature: number;
  key: string | null; backend: string; backend_version: string;
  beats: number[]; downbeats: number[];
  sections: Section[]; chords: ChordSpan[];
  meta: Record<string, unknown>;
}
export interface Song {
  id: string; name: string; folder: string;
  stems: Record<string, string>;
  tempo: number | null; key: string | null; duration: number | null;
  analyzed: boolean; analysis?: Analysis | null;
}
export interface Job {
  id: string; kind: string; state: "queued" | "running" | "done" | "error";
  progress: number; message: string; result: unknown;
}
export interface Health {
  ok: boolean;
  backends: Record<string, { available: boolean; reason: string; version: string }>;
  template: { path: string; present: boolean };
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!r.ok) throw new Error((await r.text()) || r.statusText);
  return r.json() as Promise<T>;
}

export const api = {
  health: () => req<Health>("/health"),
  songs: () => req<Song[]>("/songs"),
  song: (id: string) => req<Song>(`/songs/${id}`),
  scan: () => req<{ added: Song[]; count: number }>("/songs/scan", { method: "POST" }),
  analyze: (id: string, backend?: string) =>
    req<{ job_id: string }>(`/songs/${id}/analyze`, {
      method: "POST",
      body: JSON.stringify({ backend: backend ?? null }),
    }),
  job: (id: string) => req<Job>(`/jobs/${id}`),
};

/** Poll a job to completion. Resolves with the finished job. */
export async function waitForJob(
  id: string,
  onTick?: (j: Job) => void,
  intervalMs = 1200,
): Promise<Job> {
  for (;;) {
    const j = await api.job(id);
    onTick?.(j);
    if (j.state === "done" || j.state === "error") return j;
    await new Promise((r) => setTimeout(r, intervalMs));
  }
}

export const fmtTime = (s: number) =>
  `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
