import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/shared/api/client";
import { label } from "@/shared/lib/format";
import { ActionButton, Modal, Pager, download, num, useDebounced, useNotify } from "./ui";

type Job = { id: number; title: string; url: string; location?: string | null; status: string; domain?: string | null; job_type: string; posted_at?: string | null; first_seen: string; company: string; company_id: number; saved_by: number };
type Page = { items: Job[]; total: number };
const DOMAINS = ["mobile", "frontend", "backend", "fullstack", "software", "data", "devops", "security", "qa", "embedded", "design", "product", "other"];

export function JobsTab({ isAdmin }: { isAdmin: boolean }) {
  const qc = useQueryClient(); const notify = useNotify();
  const [q, setQ] = useState(""); const [status, setStatus] = useState("open"); const [domain, setDomain] = useState(""); const [older, setOlder] = useState(""); const [sort, setSort] = useState("newest"); const [page, setPage] = useState(1);
  const [sel, setSel] = useState<Set<number>>(new Set()); const [confirm, setConfirm] = useState<null | { action: string; all: boolean }>(null);
  const dq = useDebounced(q);
  const params = { q: dq, status, domain, older_than_days: older, sort, page, limit: 25 };
  const list = useQuery({ queryKey: ["jobs-admin", params], queryFn: () => api.get<Page>("/admin/jobs", params), placeholderData: (p) => p });
  const items = list.data?.items ?? []; const total = list.data?.total ?? 0;
  const refresh = () => { setSel(new Set()); qc.invalidateQueries({ queryKey: ["jobs-admin"] }); qc.invalidateQueries({ queryKey: ["admin-policy"] }); qc.invalidateQueries({ queryKey: ["admin-stats"] }); };
  const reset = (fn: () => void) => { fn(); setPage(1); setSel(new Set()); };
  const all = items.length > 0 && items.every((j) => sel.has(j.id));
  const run = async (action: string, allMatching: boolean) => {
    const body = allMatching ? { action, all_matching: true, confirm: true, q: dq || undefined, status: status === "all" ? undefined : status, domain: domain || undefined, older_than_days: older ? +older : undefined } : { action, ids: [...sel] };
    const r = await api.post<{ changed: number }>("/admin/jobs/bulk", body);
    notify(`${num(r.changed)} job(s) ${action === "delete" ? "deleted" : action === "expire" ? "marked expired" : "re-opened"}.`, r.changed ? "ok" : "info"); setConfirm(null); refresh();
  };
  const btn = (action: string, text: string, danger = false) => <button className={`btn small ${danger ? "danger" : "ghost"}`} disabled={!sel.size} onClick={() => (action === "delete" ? setConfirm({ action, all: false }) : run(action, false))}>{text} ({sel.size})</button>;
  return (
    <div className="stack">
      <div className="toolbar">
        <input type="search" placeholder="Search title or company" value={q} onChange={(e) => reset(() => setQ(e.target.value))} />
        <select value={status} onChange={(e) => reset(() => setStatus(e.target.value))}><option value="open">Open</option><option value="expired">Expired</option><option value="all">All</option></select>
        <select value={domain} onChange={(e) => reset(() => setDomain(e.target.value))}><option value="">Any domain</option>{DOMAINS.map((d) => <option key={d} value={d}>{label(d)}</option>)}</select>
        <select value={older} onChange={(e) => reset(() => setOlder(e.target.value))}><option value="">Any age</option><option value="7">Older than 7 days</option><option value="30">Older than 30 days</option><option value="60">Older than 60 days</option><option value="90">Older than 90 days</option><option value="180">Older than 180 days</option></select>
        <select value={sort} onChange={(e) => setSort(e.target.value)}><option value="newest">Newest first</option><option value="oldest">Oldest first</option><option value="company">Company</option><option value="title">Title</option></select>
        <ActionButton className="btn ghost small" run={async () => { await download("/admin/export/jobs.csv", "jobs.csv"); notify("Downloaded jobs.csv", "ok"); }}>⬇ CSV</ActionButton>
      </div>
      <div className="toolbar">
        {btn("expire", "Mark expired")}{btn("reopen", "Re-open")}{isAdmin && btn("delete", "Delete", true)}
        {isAdmin && total > 0 && <button className="btn ghost small" onClick={() => setConfirm({ action: "delete", all: true })}>Delete all {num(total)} matching…</button>}
        <span className="muted small right">{sel.size ? `${sel.size} selected` : "Tick rows to act on them"}</span>
      </div>
      <div className="tablewrap"><table className="dtable">
        <thead><tr><th style={{ width: 30 }}><input type="checkbox" checked={all} onChange={() => setSel(all ? new Set() : new Set(items.map((j) => j.id)))} aria-label="Select all on this page" /></th><th>Title</th><th>Company</th><th>Domain</th><th>Type</th><th>Posted</th><th>Seen</th><th>Status</th></tr></thead>
        <tbody>{items.map((j) => <tr key={j.id}>
          <td><input type="checkbox" checked={sel.has(j.id)} onChange={() => setSel((s) => { const n = new Set(s); n.has(j.id) ? n.delete(j.id) : n.add(j.id); return n; })} /></td>
          <td className="clip" title={j.title}><a href={j.url} target="_blank" rel="noreferrer">{j.title}</a>{j.saved_by > 0 && <span className="badge" title="Saved in someone's pipeline" style={{ marginLeft: 6 }}>saved ×{j.saved_by}</span>}</td>
          <td className="clip">{j.company}</td><td><span className="badge">{j.domain ?? "—"}</span></td><td className="small">{label(j.job_type)}</td>
          <td className="small muted">{j.posted_at ?? "—"}</td><td className="small muted">{new Date(j.first_seen).toLocaleDateString()}</td>
          <td><span className={`badge ${j.status === "open" ? "ok" : "warn"}`}>{j.status}</span></td></tr>)}
          {!items.length && <tr><td colSpan={8} className="empty">{list.isLoading ? "Loading…" : "No jobs match these filters."}</td></tr>}</tbody>
      </table></div>
      <Pager page={page} limit={25} total={total} onPage={(p) => { setPage(p); setSel(new Set()); }} />
      {confirm && <Modal title={confirm.all ? `Delete all ${num(total)} matching jobs?` : `Delete ${sel.size} job(s)?`} onClose={() => setConfirm(null)}>
        <p>{confirm.all ? <>Every job matching the current filters will be removed — not only the {items.length} on this page.</> : <>The selected jobs will be removed.</>} Jobs saved in a pipeline disappear from it too. This cannot be undone.</p>
        <div className="row" style={{ justifyContent: "flex-end" }}><button className="btn ghost" onClick={() => setConfirm(null)}>Cancel</button><ActionButton className="btn danger" run={() => run("delete", confirm.all)}>Delete</ActionButton></div></Modal>}
    </div>
  );
}
