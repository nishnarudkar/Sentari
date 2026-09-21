"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { ASPECTS, aspectLabel, fmt, get, post, scoreColor } from "@/lib/api";

export default function Watchlist() {
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState("");
  const [digest, setDigest] = useState<any>(null);
  const [running, setRunning] = useState(false);

  const load = () => {
    get("/watchlist").then(setData).catch((e) => setErr(String(e)));
    get("/digest").then(setDigest).catch(() => {});
  };
  useEffect(load, []);

  const runDaily = async () => {
    setRunning(true);
    try { await post("/run/daily"); load(); } catch (e) { setErr(String(e)); }
    setRunning(false);
  };

  return (
    <>
      <div className="row between" style={{ marginTop: 22 }}>
        <div>
          <h1>Watchlist</h1>
          <div className="muted">Aspect-level sentiment from the latest earnings call, with the prepared-vs-Q&A gap.</div>
        </div>
        <button className="primary" onClick={runDaily} disabled={running}>{running ? "Running…" : "Run daily pipeline"}</button>
      </div>
      {err && <div className="err">Could not reach the API: {err}. Is the backend running on {process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}?</div>}
      {data && data.tickers.length === 0 && (
        <p className="muted">No data yet — press “Run daily pipeline” to ingest and score the sample corpus.</p>
      )}

      {digest?.moves?.length > 0 && (
        <>
          <h2>Top aspect moves</h2>
          <div className="grid">
            {digest.moves.map((m: any, i: number) => (
              <Link key={i} href={`/ticker/${m.ticker}`} className="card" style={{ color: "inherit" }}>
                <div className="row between">
                  <b>{m.ticker}</b>
                  <span className={"badge " + (m.change > 0 ? "pos" : "neg")}>{m.change > 0 ? "▲" : "▼"} {fmt(m.change)}</span>
                </div>
                <div className="muted small">{aspectLabel(m.aspect)} · {fmt(m.from)} → {fmt(m.to)} · {m.date}</div>
              </Link>
            ))}
          </div>
        </>
      )}

      <h2>Tickers</h2>
      <div className="grid">
        {data?.tickers.map((t: any) => (
          <Link key={t.ticker} href={`/ticker/${t.ticker}`} className="card" style={{ color: "inherit" }}>
            <div className="row between">
              <h1 style={{ fontSize: 20 }}>{t.ticker}</h1>
              {t.brief && (
                <span className={"badge " + (t.brief.stance?.includes("positive") ? "pos" : t.brief.stance?.includes("negative") ? "neg" : "neu")}>
                  {t.brief.stance} · {(t.brief.confidence * 100).toFixed(0)}%
                </span>
              )}
            </div>
            <div className="muted small">{t.latest_document?.title} · {t.latest_document?.date}</div>
            <div className="row" style={{ marginTop: 10 }}>
              {ASPECTS.map((a) => {
                const v = t.aspects[a];
                return (
                  <span key={a} className="chip" title={v?.delta != null ? `Q&A − prepared: ${fmt(v.delta)}` : ""}>
                    {aspectLabel(a)} <b style={{ color: scoreColor(v?.mean) }}>{fmt(v?.mean)}</b>
                    {v?.delta != null && v.delta < -0.5 && <span title="Q&A markedly weaker than prepared remarks" style={{ color: "var(--warn)" }}>⚠</span>}
                  </span>
                );
              })}
            </div>
          </Link>
        ))}
      </div>
    </>
  );
}
