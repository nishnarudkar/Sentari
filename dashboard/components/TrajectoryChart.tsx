"use client";
import { TrajPoint, fmt, scoreColor } from "@/lib/api";

const W = 340, H = 150, PAD = { l: 34, r: 12, t: 12, b: 26 };

/** Dependency-free SVG line chart: mean score per document, plus prepared vs Q&A. Clicking a point drills down. */
export default function TrajectoryChart({
  points, onSelect, selectedId,
}: { points: TrajPoint[]; onSelect: (p: TrajPoint) => void; selectedId?: number }) {
  if (!points.length) return <div className="muted small" style={{ padding: "40px 0" }}>No scored sentences for this aspect yet.</div>;
  const x = (i: number) => PAD.l + (points.length === 1 ? (W - PAD.l - PAD.r) / 2 : (i * (W - PAD.l - PAD.r)) / (points.length - 1));
  const y = (v: number) => PAD.t + ((1 - v) / 2) * (H - PAD.t - PAD.b);
  const line = (key: "mean" | "prepared" | "qa") => {
    const pts = points.map((p, i) => [x(i), p[key], i] as const).filter(([, v]) => v !== null) as [number, number, number][];
    return pts.map(([px, v], k) => `${k ? "L" : "M"}${px},${y(v)}`).join(" ");
  };
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="aspect sentiment trajectory">
      {[1, 0, -1].map((t) => (
        <g key={t}>
          <line x1={PAD.l} x2={W - PAD.r} y1={y(t)} y2={y(t)} stroke="var(--border)" strokeDasharray={t === 0 ? "" : "3 3"} />
          <text x={PAD.l - 6} y={y(t) + 4} fontSize="10" textAnchor="end" fill="var(--muted)">{t > 0 ? "+1" : t}</text>
        </g>
      ))}
      <path d={line("prepared")} fill="none" stroke="var(--pos)" strokeWidth="1.3" strokeDasharray="4 3" opacity=".7" />
      <path d={line("qa")} fill="none" stroke="var(--neg)" strokeWidth="1.3" strokeDasharray="4 3" opacity=".7" />
      <path d={line("mean")} fill="none" stroke="var(--accent)" strokeWidth="2" />
      {points.map((p, i) => (
        <g key={p.document_id} style={{ cursor: "pointer" }} onClick={() => onSelect(p)}>
          <circle cx={x(i)} cy={y(p.mean)} r={selectedId === p.document_id ? 7 : 5} fill={scoreColor(p.mean)} stroke="var(--card)" strokeWidth="2" />
          <title>{`${p.date} · ${p.doc_type} · mean ${fmt(p.mean)} (n=${p.n})`}</title>
          <text x={x(i)} y={H - 8} fontSize="9.5" textAnchor="middle" fill="var(--muted)">{p.date.slice(2, 7)}</text>
        </g>
      ))}
    </svg>
  );
}
