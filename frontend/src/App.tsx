import { useEffect, useState } from "react";
import { api, waitForJob, fmtTime } from "./lib/api";
import type { Health, Job, Song } from "./lib/api";
import { SectionTimeline } from "./components/SectionTimeline";

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [songs, setSongs] = useState<Song[]>([]);
  const [selected, setSelected] = useState<Song | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [err, setErr] = useState<string>("");

  const refresh = () =>
    api.songs().then(setSongs).catch((e) => setErr(String(e)));

  useEffect(() => {
    api.health().then(setHealth).catch((e) => setErr(String(e)));
    refresh();
  }, []);

  const open = async (id: string) => {
    setErr("");
    try {
      setSelected(await api.song(id));
    } catch (e) {
      setErr(String(e));
    }
  };

  const analyze = async (song: Song) => {
    setErr("");
    try {
      const { job_id } = await api.analyze(song.id);
      const done = await waitForJob(job_id, setJob);
      setJob(null);
      if (done.state === "error") setErr(done.message);
      await refresh();
      await open(song.id);
    } catch (e) {
      setJob(null);
      setErr(String(e));
    }
  };

  const allin1 = health?.backends?.allin1;

  return (
    <div className="app">
      <h1>abletonhelper</h1>
      <div className="sub">
        Analyse stems, name the sections, build the Live set.
      </div>

      {allin1 && !allin1.available && (
        <div className="warn">
          <strong>Sections are running on the fallback backend.</strong> librosa
          finds boundaries by repetition, so labels like “chorus” are guesses at
          low confidence. Install <code>allin1</code> for real functional
          labels — see docs/analysis.md.
        </div>
      )}
      {health && !health.template.present && (
        <div className="warn">
          No Live template at <code>{health.template.path}</code>. Set building
          is disabled until one is there.
        </div>
      )}
      {err && <div className="panel err">{err}</div>}

      <div className="panel">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <strong>Songs</strong>
          <div className="row">
            <button className="ghost" onClick={() => api.scan().then(refresh)}>
              Scan songs/
            </button>
            <button className="ghost" onClick={refresh}>Refresh</button>
          </div>
        </div>
        <table>
          <thead>
            <tr>
              <th>name</th><th>stems</th><th>tempo</th><th>key</th>
              <th>length</th><th></th>
            </tr>
          </thead>
          <tbody>
            {songs.map((s) => (
              <tr key={s.id}>
                <td>
                  <a href="#" onClick={(e) => { e.preventDefault(); open(s.id); }}>
                    {s.name}
                  </a>
                </td>
                <td>{Object.keys(s.stems).length}</td>
                <td className="mono">{s.tempo ? s.tempo.toFixed(1) : "—"}</td>
                <td>{s.key ?? "—"}</td>
                <td className="mono">{s.duration ? fmtTime(s.duration) : "—"}</td>
                <td>
                  <button onClick={() => analyze(s)} disabled={!!job}>
                    {s.analyzed ? "Re-analyse" : "Analyse"}
                  </button>
                </td>
              </tr>
            ))}
            {songs.length === 0 && (
              <tr><td colSpan={6} style={{ color: "var(--muted)" }}>
                Nothing yet. Drop stem folders into <code>songs/</code> and hit Scan.
              </td></tr>
            )}
          </tbody>
        </table>
      </div>

      {job && (
        <div className="panel">
          Analysing… <span className="mono">{Math.round(job.progress * 100)}%</span>{" "}
          <span className="chip">{job.message || job.state}</span>
        </div>
      )}

      {selected && (
        <div className="panel">
          <div className="row" style={{ justifyContent: "space-between" }}>
            <strong>{selected.name}</strong>
            <span className="chip">
              {selected.analysis?.backend ?? "not analysed"}
            </span>
          </div>
          {selected.analysis ? (
            <>
              <div className="row" style={{ margin: "10px 0" }}>
                <span className="chip">{selected.analysis.tempo.toFixed(2)} BPM</span>
                <span className="chip">{selected.analysis.key}</span>
                <span className="chip">{selected.analysis.time_signature}/4</span>
                <span className="chip">{selected.analysis.sections.length} sections</span>
                <span className="chip">{selected.analysis.chords.length} chord spans</span>
              </div>
              <SectionTimeline analysis={selected.analysis} />
            </>
          ) : (
            <div className="sub" style={{ marginTop: 10 }}>
              Not analysed yet.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
