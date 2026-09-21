"use client";
import { useEffect, useState } from "react";
import { get } from "@/lib/api";

export default function Models() {
  const [rows, setRows] = useState<any[]>([]);
  const [err, setErr] = useState("");
  useEffect(() => { get("/models").then(setRows).catch((e) => setErr(String(e))); }, []);
  const f = (v: any) => (typeof v === "number" ? v.toFixed(3) : "–");
  return (
    <>
      <h1 style={{ marginTop: 22 }}>Model registry</h1>
      <div className="muted">Every rung of the ladder, scored on the same held-out gold set. Full runs are tracked in MLflow.</div>
      {err && <div className="err">{err}</div>}
      <div className="card" style={{ marginTop: 14, overflowX: "auto" }}>
        <table>
          <thead><tr><th>Model</th><th>Version</th><th>Macro-F1</th><th>Accuracy</th><th>Trap acc.</th><th>ms/item</th><th>Serving</th></tr></thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan={7} className="muted">No model runs yet — run <code>python -m absa_service.train</code>.</td></tr>}
            {rows.map((r) => (
              <tr key={r.name + r.version}>
                <td><b>{r.name}</b></td><td className="muted">{r.version}</td>
                <td>{f(r.metrics.gold_macro_f1)}</td><td>{f(r.metrics.gold_accuracy)}</td>
                <td>{f(r.metrics.gold_trap_accuracy)}</td><td>{f(r.metrics.latency_ms)}</td>
                <td>{r.serving && <span className="badge pos">serving</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
