"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import SourceDrawer from "@/components/SourceDrawer";
import { aspectLabel, get } from "@/lib/api";

export default function BriefPage() {
  const { id } = useParams<{ id: string }>();
  const [b, setB] = useState<any>(null);
  const [err, setErr] = useState("");
  const [chunk, setChunk] = useState<number | null>(null);
  const [showTrace, setShowTrace] = useState(false);

  useEffect(() => { get(`/briefs/${id}`).then(setB).catch((e) => setErr(String(e))); }, [id]);

  if (err) return <div className="err">{err}</div>;
  if (!b) return <div className="muted" style={{ marginTop: 22 }}>Loading…</div>;
  const body = b.body;
  const detail = body.confidence_detail;

  const Cites = ({ ids }: { ids: number[] }) => (
    <>{ids.map((c) => (
      <button key={c} className="cite" title={b.sources?.[c]?.text} onClick={() => setChunk(c)}>src {c}</button>
    ))}</>
  );

  return (
    <>
      <div style={{ marginTop: 22 }}>
        <Link href={`/ticker/${b.ticker}`} className="muted small">← {b.ticker}</Link>
        <h1>{b.ticker} brief</h1>
        <div className="muted">{b.period[0]} → {b.period[1]} · {body.llm} · {b.latency_s}s{b.tokens_in ? ` · ${b.tokens_in + b.tokens_out} tokens` : ""}</div>
      </div>

      <div className="card" style={{ marginTop: 14 }}>
        <div className="row between">
          <b>Stance: {body.stance} (net {body.net_sentiment >= 0 ? "+" : ""}{body.net_sentiment})</b>
          <span className="badge neu">confidence {(b.confidence * 100).toFixed(0)}%</span>
        </div>
        <div className="bar" style={{ margin: "8px 0" }}><i style={{ width: `${b.confidence * 100}%` }} /></div>
        <div className="muted small">
          claims surviving the skeptic: {detail.supported} supported, {detail.unverified} unverified, {detail.rejected} rejected ·
          evidence confidence {(detail.mean_evidence_confidence * 100).toFixed(0)}% · aspect coverage {(detail.aspect_coverage * 100).toFixed(0)}%
        </div>
        <div className="muted small">Confidence is a transparent heuristic, not a calibrated probability.</div>
      </div>

      <h2>Summary</h2>
      <div className="card">
        {body.summary.map((s: any, i: number) => (
          <p key={i} style={{ margin: "6px 0" }}>{s.text}<Cites ids={s.citations} /></p>
        ))}
      </div>

      <h2>Bull vs bear, by aspect (verified claims only)</h2>
      <div className="grid">
        {Object.entries(body.sections).map(([aspect, sides]: any) => (
          <div key={aspect} className="card">
            <h3>{aspectLabel(aspect)}</h3>
            {["bull", "bear"].map((side) => sides[side].map((c: any) => (
              <div key={c.claim_id} style={{ margin: "8px 0" }}>
                <span className={"badge " + (side === "bull" ? "pos" : "neg")}>{side}</span>{" "}
                {c.text}<Cites ids={c.citations} />
              </div>
            )))}
          </div>
        ))}
      </div>

      {body.unverified.length > 0 && (
        <>
          <h2>Flagged as unverified</h2>
          <div className="card">
            {body.unverified.map((c: any) => (
              <div key={c.claim_id} style={{ margin: "6px 0" }}>
                <span className="badge warn">unverified</span> {c.text}<Cites ids={c.citations} />
              </div>
            ))}
          </div>
        </>
      )}
      <p className="muted small">{body.dropped_claims} claim(s) were rejected by the skeptic and removed from this brief.</p>

      <div className="row" style={{ marginTop: 14 }}>
        <button onClick={() => setShowTrace(!showTrace)}>{showTrace ? "Hide" : "Show"} agent audit trail</button>
      </div>
      {showTrace && (
        <div className="card" style={{ marginTop: 10 }}>
          {b.traces.map((t: any) => (
            <details key={t.step} style={{ margin: "6px 0" }}>
              <summary><b>{t.step}. {t.agent}</b></summary>
              <pre style={{ whiteSpace: "pre-wrap", fontSize: 12 }}>{JSON.stringify(t.payload, null, 2)}</pre>
            </details>
          ))}
        </div>
      )}
      <SourceDrawer chunkId={chunk} onClose={() => setChunk(null)} />
    </>
  );
}
