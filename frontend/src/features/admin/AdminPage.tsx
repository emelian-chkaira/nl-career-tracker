import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/shared/api/client";

const KINDS = ["scan_all", "discover", "logos", "sponsors", "embed"];
export function AdminPage() {
  const qc = useQueryClient();
  const stats = useQuery({ queryKey: ["admin-stats"], refetchInterval: 15000, queryFn: () => api.get<Record<string, unknown> & { scan_outcomes: { note: string; n: number }[] }>("/admin/stats") });
  const tasks = useQuery({ queryKey: ["admin-tasks"], refetchInterval: 5000, queryFn: () => api.get<{ id: number; kind: string; status: string; progress: unknown; error?: string; created_at: string }[]>("/admin/tasks") });
  const users = useQuery({ queryKey: ["admin-users"], queryFn: () => api.get<{ id: string; email: string; role: string; active: boolean; created_at: string }[]>("/admin/users") });
  const enqueue = async (kind: string) => { await api.post("/admin/tasks", { kind }); qc.invalidateQueries({ queryKey: ["admin-tasks"] }); };
  const setUser = async (id: string, body: object) => { await api.patch(`/admin/users/${id}`, body); qc.invalidateQueries({ queryKey: ["admin-users"] }); };
  return (<div className="stack"><h1>Admin</h1>
    <div className="grid kpis">{stats.data && Object.entries(stats.data).filter(([, v]) => typeof v === "number").map(([k, v]) => <div className="card kpi" key={k}><div className="muted small">{k.replace(/_/g, " ")}</div><div className="v">{(v as number).toLocaleString()}</div></div>)}</div>
    <div className="card stack"><h2>Run a background task</h2><div className="row">{KINDS.map((k) => <button key={k} className="btn ghost small" onClick={() => enqueue(k)}>{k}</button>)}</div>
      <table className="table"><thead><tr><th>#</th><th>Kind</th><th>Status</th><th>Progress</th></tr></thead><tbody>{tasks.data?.map((t) => <tr key={t.id}><td>{t.id}</td><td>{t.kind}</td><td className={t.status === "failed" ? "err" : ""}>{t.status}</td><td className="small muted">{t.error ?? JSON.stringify(t.progress)}</td></tr>)}</tbody></table></div>
    <div className="card"><h2>Users</h2><table className="table"><thead><tr><th>Email</th><th>Role</th><th>Active</th><th /></tr></thead><tbody>{users.data?.map((u) => <tr key={u.id}><td>{u.email}</td><td>{u.role}</td><td>{u.active ? "yes" : "no"}</td>
      <td><button className="btn ghost small" onClick={() => setUser(u.id, { active: !u.active })}>{u.active ? "Disable" : "Enable"}</button></td></tr>)}</tbody></table></div>
  </div>);
}
