import type { Analysis } from "../lib/api";
import { fmtTime } from "../lib/api";

// Stable colour per functional label, so the same part reads the same
// across every song in a set.
const COLORS: Record<string, string> = {
  intro: "#7f9cc0", verse: "#8fc08f", prechorus: "#c9bd72",
  chorus: "#f2b134", bridge: "#c08fb8", instrumental: "#8fbfc0",
  solo: "#e08f6a", breakdown: "#9a9a9a", outro: "#6f7f95",
  silence: "#3a3f47", unknown: "#555b66",
};

export function SectionTimeline({ analysis }: { analysis: Analysis }) {
  const total = analysis.duration || 1;
  const barsOf = (secs: number) =>
    analysis.tempo
      ? secs * analysis.tempo / 60 / (analysis.time_signature || 4)
      : 0;

  return (
    <div>
      <div className="timeline">
        {analysis.sections.map((s, i) => {
          const pct = ((s.end - s.start) / total) * 100;
          return (
            <div
              key={i}
              className="seg"
              style={{ width: `${pct}%`, background: COLORS[s.label] ?? COLORS.unknown }}
              title={`${s.label}  ${fmtTime(s.start)}–${fmtTime(s.end)}  ${barsOf(s.end - s.start).toFixed(1)} bars`}
            >
              {pct > 7 ? s.label : ""}
            </div>
          );
        })}
      </div>
      <table>
        <thead>
          <tr><th>section</th><th>start</th><th>end</th><th>bars</th><th>conf</th></tr>
        </thead>
        <tbody>
          {analysis.sections.map((s, i) => (
            <tr key={i}>
              <td>{s.label}</td>
              <td className="mono">{fmtTime(s.start)}</td>
              <td className="mono">{fmtTime(s.end)}</td>
              <td className="mono">{barsOf(s.end - s.start).toFixed(1)}</td>
              <td className="mono">{s.confidence.toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
