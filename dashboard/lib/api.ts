export const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const ASPECTS = ["guidance", "margins", "demand", "litigation", "management_tone", "liquidity"] as const;
export type Aspect = (typeof ASPECTS)[number];

export const aspectLabel = (a: string) => a.replace("_", " ").replace(/^\w/, (c) => c.toUpperCase());

export async function get<T = any>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} — ${path}`);
  return res.json();
}

export async function post<T = any>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} — ${path}`);
  return res.json();
}

export interface TrajPoint {
  document_id: number;
  date: string;
  doc_type: string;
  title: string;
  mean: number;
  n: number;
  prepared: number | null;
  qa: number | null;
}

export interface ScoredPoint {
  chunk_id: number;
  text: string;
  section: string;
  speaker: string;
  date: string;
  document: string;
  document_id: number;
  score: number;
  polarity: string;
  confidence: number;
  model: string;
}

/** diverging colour for a signed score in [-1, 1] */
export function scoreColor(s: number | null | undefined): string {
  if (s === null || s === undefined) return "var(--muted)";
  if (s > 0.15) return "var(--pos)";
  if (s < -0.15) return "var(--neg)";
  return "var(--neu)";
}

export const fmt = (s: number | null | undefined) => (s === null || s === undefined ? "–" : (s > 0 ? "+" : "") + s.toFixed(2));
