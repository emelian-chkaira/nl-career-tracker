const SPECIAL: Record<string, string> = { devops: "DevOps", qa: "QA", ai_ml: "AI / ML", data: "Data", ml: "ML", ui_ux: "UI / UX" };
export const label = (s: string) => SPECIAL[s] ?? s.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
export function ago(d?: string | null): string {
  if (!d) return "";
  const days = Math.floor((Date.now() - new Date(d).getTime()) / 86400000);
  if (days <= 0) return "today"; if (days === 1) return "yesterday"; if (days < 31) return `${days}d ago`; if (days < 365) return `${Math.floor(days / 30)}mo ago`; return `${Math.floor(days / 365)}y ago`;
}
export const money = (v?: number) => (v == null ? "" : `€${Math.round(v).toLocaleString("nl-NL")}`);
export function qs(params: Record<string, unknown>): string {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) { if (v == null || v === "" || (Array.isArray(v) && !v.length)) continue; (Array.isArray(v) ? v : [v]).forEach((x) => u.append(k, String(x))); }
  return u.toString();
}
export function parseQs(search: string): Record<string, string | string[]> {
  const u = new URLSearchParams(search); const out: Record<string, string | string[]> = {};
  for (const k of new Set(u.keys())) { const all = u.getAll(k); out[k] = all.length > 1 ? all : all[0]; }
  return out;
}
