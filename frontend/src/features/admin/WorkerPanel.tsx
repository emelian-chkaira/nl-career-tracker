import { useQuery } from "@tanstack/react-query";
import { api } from "@/shared/api/client";

type Worker = {
  running: boolean; idle_seconds: number | null; total: number; due: number; rate_per_min: number; eta_minutes: number | null;
  open_jobs: number; new_jobs_hour: number; saved_careers_pages: number;
  per_min: { t: string; n: number }[]; recent: { name: string; ats: string | null; note: string | null; at: string }[];
};

const ago = (iso: string) => { const s = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000)); return s < 60 ? `${s}s ago` : `${Math.round(s / 60)}m ago`; };
const eta = (m: number | null) => (m == null ? "–" : m < 60 ? `${m} min` : `${(m / 60).toFixed(1)} h`);

/** Live view of the crawler worker: status, throughput chart, backlog progress and the latest scans. Refreshes every 5 s. */
export function WorkerPanel() {
  const q = useQuery({ queryKey: ["admin-worker"], refetchInterval: 5000, queryFn: () => api.get<Worker>("/admin/worker") });
  const w = q.data;
  if (q.isError || (w && !Array.isArray(w.per_min))) return <div className="card muted">Worker status is unavailable. Restart the API (<code>./run.sh api</code>) so it picks up the new <code>/admin/worker</code> endpoint.</div>;
  if (!w) return <div className="card muted">Loading worker…</div>;
  const done = w.total - w.due, pct = w.total ? Math.round((done / w.total) * 100) : 0;
  // fill missing minutes so the chart is a continuous 30-minute strip
  const now = Math.floor(Date.now() / 60000), by = new Map(w.per_min.map((p) => [Math.floor(new Date(p.t).getTime() / 60000), p.n]));
  const series = Array.from({ length: 30 }, (_, i) => by.get(now - 29 + i) ?? 0), max = Math.max(1, ...series);
  return (
    <div className="card stack">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h2 style={{ margin: 0 }}>The crawler, right now</h2>
        <span className={`chip ${w.running ? "ok" : "warn"}`}>{w.running ? "Running" : `Idle${w.idle_seconds != null ? ` (${Math.round(w.idle_seconds / 60)} min since last scan)` : ""}`}</span>
      </div>
      <div className="statrow">
        <div><b>{w.rate_per_min}</b><span>companies read per minute</span></div>
        <div><b>{w.due.toLocaleString()}</b><span>still waiting for a visit</span></div>
        <div><b>{eta(w.eta_minutes)}</b><span>until it catches up</span></div>
        <div><b>{w.new_jobs_hour}</b><span>new jobs in the last hour</span></div>
        <div><b>{w.saved_careers_pages.toLocaleString()}</b><span>careers pages remembered</span></div>
      </div>
      <div>
        <div className="row small muted" style={{ justifyContent: "space-between" }}><span>Checked recently: {done.toLocaleString()} / {w.total.toLocaleString()} companies</span><span>{pct}%</span></div>
        <div style={{ height: 10, borderRadius: 999, background: "var(--panel2)", border: "1px solid var(--line)", overflow: "hidden" }}>
          <div style={{ width: `${pct}%`, height: "100%", background: "var(--hero)", transition: "width .6s" }} />
        </div>
      </div>
      <div>
        <div className="small muted">Companies visited per minute, last half hour</div>
        <div style={{ display: "flex", alignItems: "flex-end", gap: 3, height: 70 }} role="img" aria-label="scans per minute">
          {series.map((n, i) => <div key={i} title={`${n} scans`} style={{ flex: 1, height: `${Math.max(3, (n / max) * 100)}%`, background: n ? "var(--brand)" : "var(--line)", borderRadius: 3 }} />)}
        </div>
      </div>
      <table className="table"><thead><tr><th>Just visited</th><th>Method</th><th>Result</th><th /></tr></thead>
        <tbody>{w.recent.map((r, i) => <tr key={i}><td>{r.name}</td><td className="small muted">{r.ats ?? "–"}</td><td className="small muted">{r.note ?? ""}</td><td className="small muted">{ago(r.at)}</td></tr>)}</tbody></table>
    </div>
  );
}
