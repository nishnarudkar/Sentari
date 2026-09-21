"use client";
import { useEffect, useState } from "react";
import { fmt, get, scoreColor } from "@/lib/api";

/** Shows a source sentence in context, the scoring models and their per-aspect verdicts — the grounding trail. */
export default function SourceDrawer({ chunkId, onClose }: { chunkId: number | null; onClose: () => void }) {
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    if (chunkId === null) return;
    setData(null); setErr("");
    get(`/chunks/${chunkId}?context=3`).then(setData).catch((e) => setErr(String(e)));
  }, [chunkId]);

  if (chunkId === null) return null;
  return (
    <aside className="drawer" aria-label="source sentence">
      <div className="row between">
        <h3>Source sentence</h3>
        <button onClick={onClose}>Close</button>
      </div>
      {err && <div className="err">{err}</div>}
      {!data && !err && <div className="muted">Loading…</div>}
      {data && (
        <>
          <div className="muted small">
            {data.document.title} · {data.document.date} · {data.chunk.section}
            {data.chunk.speaker ? ` · ${data.chunk.speaker}` : ""}
          </div>
          <div style={{ marginTop: 10 }}>
            {data.context.map((c: any) => (
              <div key={c.id} className={"quote" + (c.is_target ? " target" : "")}>
                {c.speaker && <div className="muted small">{c.speaker}</div>}
                {c.text}
              </div>
            ))}
          </div>
          <h3 style={{ marginTop: 18 }}>Model verdicts</h3>
          <table>
            <thead><tr><th>Aspect</th><th>Polarity</th><th>Score</th><th>Conf.</th><th>Model</th></tr></thead>
            <tbody>
              {data.scores.map((s: any, i: number) => (
                <tr key={i}>
                  <td>{s.aspect.replace("_", " ")}</td>
                  <td style={{ color: scoreColor(s.score) }}>{s.polarity}</td>
                  <td>{fmt(s.score)}</td>
                  <td>{(s.confidence * 100).toFixed(0)}%</td>
                  <td className="muted">{s.model}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {data.document.url && <p className="small muted">Source: {data.document.source} — {data.document.url}</p>}
        </>
      )}
    </aside>
  );
}
