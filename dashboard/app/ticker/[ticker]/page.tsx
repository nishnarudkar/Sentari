"use client";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import SourceDrawer from "@/components/SourceDrawer";
import TrajectoryChart from "@/components/TrajectoryChart";
import { ASPECTS, ScoredPoint, TrajPoint, aspectLabel, fmt, get, post, scoreColor } from "@/lib/api";

export default function TickerPage() {
  const { ticker } = useParams<{ ticker: string }>();
  const router = useRouter();
  const [traj, setTraj] = useState<Record<string, TrajPoint[]> | null>(null);
  const [briefs, setBriefs] = useState<any[]>([]);
  const [err, setErr] = useState("");
  const [sel, setSel] = useState<{ aspect: string; point: TrajPoint } | null>(null);
  const [points, setPoints] = useState<ScoredPoint[]>([]);
  const [chunk, setChunk] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);

  const load = () => {
    get(`/tickers/${ticker}/trajectory`).then((d) => setTraj(d.aspects)).catch((e) => setErr(String(e)));
    get(`/tickers/${ticker}/briefs`).then(setBriefs).catch(() => {});
  };
  useEffect(load, [ticker]);

  useEffect(() => {
    if (!sel) return;
    get(`/tickers/${ticker}/points?aspect=${sel.aspect}&document_id=${sel.point.document_id}`).then(setPoints).catch((e) => setErr(String(e)));
  }, [sel, ticker]);

  const generate = async (force: boolean) => {
    setBusy(true);
    try { const b = await post("/briefs/generate", { ticker, force }); router.push(`/briefs/${b.id}`); }
    catch (e) { setErr(String(e)); }
    setBusy(false);
  };

  return (
    <>
      <div className="row between" style={{ marginTop: 22 }}>
        <div><Link href="/" className="muted small">← Watchlist</Link><h1>{ticker}</h1></div>
        <div className="row">
          <button onClick={() => generate(false)} disabled={busy}>{busy ? "Working…" : "Open latest brief"}</button>
          <button onClick={() => generate(true)} disabled={busy} title="Re-run the agents even if nothing changed">Regenerate</button>
        </div>
      </div>
      {err && <div className="err">{err}</div>}

      <h2>Aspect trajectories</h2>
      <div className="muted small">
        <span style={{ color: "var(--accent)" }}>━</span> document mean &nbsp;
        <span style={{ color: "var(--pos)" }}>┅</span> prepared remarks &nbsp;
        <span style={{ color: "var(--neg)" }}>┅</span> Q&amp;A &nbsp;· click a point to see the sentences behind it
      </div>
      <div className="grid" style={{ marginTop: 10 }}>
        {ASPECTS.map((a) => (
          <div key={a} className="card">
            <div className="row between"><h3>{aspectLabel(a)}</h3>
              <span className="muted small">latest {fmt(traj?.[a]?.at(-1)?.mean)}</span></div>
            <TrajectoryChart points={traj?.[a] || []} selectedId={sel?.aspect === a ? sel.point.document_id : undefined}
              onSelect={(p) => setSel({ aspect: a, point: p })} />
          </div>
        ))}
      </div>

      {sel && (
        <>
          <h2>{aspectLabel(sel.aspect)} · {sel.point.title || sel.point.doc_type} · {sel.point.date}</h2>
          <div className="card">
            <table>
              <thead><tr><th>Section</th><th>Sentence</th><th>Score</th><th>Conf.</th><th>Model</th></tr></thead>
              <tbody>
                {points.map((p) => (
                  <tr key={p.chunk_id + p.model} onClick={() => setChunk(p.chunk_id)} style={{ cursor: "pointer" }}>
                    <td className="muted">{p.section}</td>
                    <td>{p.text}</td>
                    <td style={{ color: scoreColor(p.score), whiteSpace: "nowrap" }}>{fmt(p.score)}</td>
                    <td>{(p.confidence * 100).toFixed(0)}%</td>
                    <td className="muted">{p.model}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <h2>Briefs</h2>
      <div className="card">
        {briefs.length === 0 && <span className="muted">No briefs yet.</span>}
        {briefs.map((b) => (
          <div key={b.id} className="row between" style={{ padding: "6px 0", borderBottom: "1px solid var(--border)" }}>
            <Link href={`/briefs/${b.id}`}>{b.period[0]} → {b.period[1]}</Link>
            <span className="muted small">{b.body.stance} · confidence {(b.confidence * 100).toFixed(0)}% · {b.body.llm}</span>
          </div>
        ))}
      </div>
      <SourceDrawer chunkId={chunk} onClose={() => setChunk(null)} />
    </>
  );
}
