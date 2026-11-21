import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/shared/api/client";
import { ActionButton, ago, num, useNotify } from "./ui";

type Task = { id: number; kind: string; status: string; progress?: Record<string, unknown>; error?: string | null; created_at: string; finished_at?: string | null };
export const TASKS: { kind: string; title: string; what: string }[] = [
  { kind: "scan_unscanned", title: "Scan new companies", what: "Scan only companies that were never scanned." },
  { kind: "scan_all", title: "Re-scan everything", what: "Re-read every company's careers page. Slow: the worker also does this continuously." },
  { kind: "discover", title: "Discover companies", what: "Find new employers from free public sources." },
  { kind: "census", title: "Find ATS boards", what: "Look for companies on public job-board providers." },
  { kind: "internships", title: "Find internships", what: "Look for internship and graduate programmes." },
  { kind: "sponsors_refresh", title: "Refresh sponsor list", what: "Download the IND recognised-sponsor register and re-check companies." },
  { kind: "logos", title: "Fetch logos", what: "Download company logos for the job cards." },
  { kind: "embed", title: "Build search embeddings", what: "Add semantic-search vectors for new jobs." },
];

function progressText(t: Task) {
  const p = t.progress ?? {}; const done = Number(p.done ?? 0), total = Number(p.total ?? 0);
  if (t.error) return t.error;
  if (total) return `${num(done)} / ${num(total)}${p.new_jobs ? ` · ${num(Number(p.new_jobs))} new jobs` : ""}`;
  const e = Object.entries(p).filter(([, v]) => typeof v === "number" || typeof v === "string").slice(0, 3).map(([k, v]) => `${k.replace(/_/g, " ")}: ${v}`); return e.join(" · ");
}

export function TasksPanel({ compact = false }: { compact?: boolean }) {
  const qc = useQueryClient(); const notify = useNotify();
  const tasks = useQuery({ queryKey: ["admin-tasks"], refetchInterval: 4000, queryFn: () => api.get<Task[]>("/admin/tasks") });
  const run = async (t: (typeof TASKS)[number]) => { const r = await api.post<{ id: number }>("/admin/tasks", { kind: t.kind }); notify(`Queued “${t.title}” (#${r.id}). The worker starts it within seconds.`, "ok"); qc.invalidateQueries({ queryKey: ["admin-tasks"] }); };
  const items = tasks.data ?? [];
  const active = items.filter((t) => t.status === "queued" || t.status === "running").length;
  return (
    <div className="stack">
      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(250px,1fr))" }}>
        {TASKS.slice(0, compact ? 4 : 8).map((t) => <div key={t.kind} className="opt" style={{ flexDirection: "column" }}><div><b>{t.title}</b><div className="small muted">{t.what}</div></div><ActionButton className="btn ghost small" run={() => run(t)}>Run</ActionButton></div>)}
      </div>
      {!compact && <><div className="row" style={{ justifyContent: "space-between" }}><h3 style={{ margin: 0 }}>Task history {active > 0 && <span className="badge ok">{active} active</span>}</h3>
        <ActionButton className="btn ghost small" run={async () => { const r = await api.del<{ removed: number }>("/admin/tasks"); notify(`Removed ${r.removed} finished task(s).`, "ok"); qc.invalidateQueries({ queryKey: ["admin-tasks"] }); }}>Clear finished</ActionButton></div>
      <div className="tablewrap"><table className="dtable"><thead><tr><th>#</th><th>Task</th><th>Status</th><th>Progress</th><th>Started</th><th /></tr></thead>
        <tbody>{items.map((t) => <tr key={t.id}><td>{t.id}</td><td>{t.kind.replace(/_/g, " ")}</td>
          <td><span className={`badge ${t.status === "done" ? "ok" : t.status === "failed" ? "bad" : t.status === "running" ? "warn" : ""}`}>{t.status}</span></td>
          <td className="clip small muted" title={progressText(t)}>{progressText(t)}</td><td className="small muted">{ago(t.created_at)}</td>
          <td><div className="actions">{(t.status === "queued" || t.status === "running") && <ActionButton className="iconbtn" run={async () => { await api.post(`/admin/tasks/${t.id}/cancel`); notify(`Task #${t.id} stopped.`, "ok"); qc.invalidateQueries({ queryKey: ["admin-tasks"] }); }}>Stop</ActionButton>}</div></td></tr>)}
          {!items.length && <tr><td colSpan={6} className="empty">No tasks yet. Run one above.</td></tr>}</tbody></table></div></>}
    </div>
  );
}
