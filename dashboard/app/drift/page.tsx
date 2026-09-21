"use client";
import { useEffect, useState } from "react";
import { ASPECTS, aspectLabel, get } from "@/lib/api";

function MixBars({ cur, base }: { cur?: Record<string, number>; base?: Record<string, number> }) {
  if (!cur || !base) return null;
  return (
    <div style={{ minWidth: 240 }}>
      {ASPECTS.map((a) => (
        <div key={a} className="row" style={{ gap: 6, fontSize: 11.5 }}>
          <span style={{ width: 96 }} className="muted">{aspectLabel(a)}</span>
          <div className="bar" style={{ flex: 1 }}><i style={{ width: `${(base[a] || 0) * 100}%`, background: "var(--neu)" }} /></div>
          <div className="bar" style={{ flex: 1 }}><i style={{ width: `${(cur[a] || 0) * 100}%` }} /></div>
        </div>
      ))}
      <div className="muted small">grey = baseline mix · blue = current week</div>
    </div>
  );
}

export default function Drift() {
  const [rows, setRows] = useState<any[]>([]);
  const [err, setErr] = useState("");
  useEffect(() => { get("/drift").then(setRows).catch((e) => setErr(String(e))); }, []);
  return (
    <>
      <h1 style={{ marginTop: 22 }}>Drift monitor</h1>
      <div className="muted">
        Week-over-week shift in the aspect-mention mix (PSI) and model confidence (Cohen’s d) per ticker — a proxy for the ABSA
        model degrading or the input data changing character. Alerts: PSI &gt; 0.25 or |d| &gt; 0.8.
      </div>
      {err && <div className="err">{err}</div>}
      <div className="card" style={{ marginTop: 14 }}>
        <table>
          <thead><tr><th>Ticker</th><th>Window</th><th>PSI</th><th>Conf. shift (d)</th><th>Status</th><th>Aspect mix</th></tr></thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan={6} className="muted">No drift reports yet — run the daily pipeline.</td></tr>}
            {rows.map((r, i) => (
              <tr key={i}>
                <td><b>{r.ticker}</b></td>
                <td>{r.week_start}</td>
                <td>{r.psi_aspect_mix.toFixed(3)}</td>
                <td>{r.confidence_shift.toFixed(2)}</td>
                <td><span className={"badge " + (r.alert ? "neg" : r.detail?.status === "insufficient_data" ? "neu" : "pos")}>
                  {r.alert ? "alert" : r.detail?.status === "insufficient_data" ? "insufficient data" : "ok"}</span></td>
                <td><MixBars cur={r.detail?.mix_current} base={r.detail?.mix_baseline} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
