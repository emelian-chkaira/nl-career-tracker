import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/shared/api/client";
import { ActionButton, Modal, Pager, download, ago, num, useDebounced, useNotify } from "./ui";

type Company = { id: number; name: string; website?: string | null; careers_url?: string | null; ats?: string | null; city?: string | null; source?: string | null;
  last_scan?: string | null; next_scan?: string | null; scan_note?: string | null; fail_count: number; notes?: string | null; open_jobs: number };
type Page = { items: Company[]; total: number };

const FILTERS: [string, string][] = [["all", "All"], ["has_jobs", "Has open jobs"], ["no_jobs", "Scanned, no jobs"], ["failing", "Failing"], ["never", "Never scanned"], ["due", "Due for scan"], ["no_site", "No website"]];
const SORTS: [string, string][] = [["name", "Name"], ["jobs", "Most jobs"], ["last_scan", "Recently scanned"], ["failing", "Most failures"], ["newest", "Newest added"]];

function health(c: Company) {
  if (!c.last_scan) return <span className="badge">not scanned</span>;
  if (c.open_jobs) return <span className="badge ok">{c.open_jobs} {c.open_jobs === 1 ? "job" : "jobs"}</span>;
  if (c.fail_count) return <span className="badge bad">failing ×{c.fail_count}</span>;
  return <span className="badge warn">no jobs</span>;
}

export function CompaniesTab({ isAdmin }: { isAdmin: boolean }) {
  const qc = useQueryClient(); const notify = useNotify();
  const [q, setQ] = useState(""); const [status, setStatus] = useState("all"); const [sort, setSort] = useState("name"); const [page, setPage] = useState(1);
  const dq = useDebounced(q);
  const list = useQuery({ queryKey: ["co", dq, status, sort, page], queryFn: () => api.get<Page>("/admin/companies", { q: dq, status, sort, page, limit: 25 }), placeholderData: (p) => p });
  const [edit, setEdit] = useState<Company | null>(null); const [add, setAdd] = useState(false); const [del, setDel] = useState<Company | null>(null);
  const refresh = () => { qc.invalidateQueries({ queryKey: ["co"] }); qc.invalidateQueries({ queryKey: ["admin-policy"] }); qc.invalidateQueries({ queryKey: ["admin-worker"] }); };
  const rescan = async (c: Company) => { await api.post(`/admin/companies/${c.id}/scan`); notify(`Queued a re-scan of ${c.name}. The worker picks it up in a few seconds.`, "ok"); };
  const items = list.data?.items ?? [];
  return (
    <div className="stack">
      <div className="toolbar">
        <input type="search" placeholder="Search name or website" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
        <select value={sort} onChange={(e) => { setSort(e.target.value); setPage(1); }} aria-label="Sort">{SORTS.map(([v, l]) => <option key={v} value={v}>Sort: {l}</option>)}</select>
        <button className="btn small" onClick={() => setAdd(true)}>＋ Add companies</button>
        <ActionButton className="btn ghost small" run={async () => { await download("/admin/export/companies.csv", "companies.csv"); notify("Downloaded companies.csv", "ok"); }}>⬇ CSV</ActionButton>
      </div>
      <div className="row" style={{ gap: 6 }}>{FILTERS.map(([v, l]) => <button key={v} className={`chip ${status === v ? "ok" : "plain"}`} style={{ cursor: "pointer", border: 0, margin: 0 }} onClick={() => { setStatus(v); setPage(1); }}>{l}</button>)}</div>
      <div className="tablewrap"><table className="dtable">
        <thead><tr><th>Company</th><th>Status</th><th>Careers page</th><th>Via</th><th>Last scan</th><th>Result</th><th /></tr></thead>
        <tbody>{items.map((c) => <tr key={c.id}>
          <td><b>{c.name}</b>{c.city && <div className="muted small">{c.city}</div>}</td>
          <td>{health(c)}</td>
          <td className="clip">{c.careers_url ? <a href={c.careers_url} target="_blank" rel="noreferrer">{c.careers_url.replace(/^https?:\/\//, "")}</a> : c.website ? <span className="muted">{c.website.replace(/^https?:\/\//, "")}</span> : <span className="muted">—</span>}</td>
          <td><span className="badge">{c.ats ?? "—"}</span></td>
          <td className="small muted">{ago(c.last_scan)}</td>
          <td className="clip small muted" style={{ maxWidth: 150 }} title={c.scan_note ?? ""}>{c.scan_note ?? ""}</td>
          <td><div className="actions"><ActionButton className="iconbtn" run={() => rescan(c)} title="Scan this company now">↻ Scan</ActionButton><button className="iconbtn" onClick={() => setEdit(c)}>Edit</button>{isAdmin && <button className="iconbtn bad" onClick={() => setDel(c)}>Delete</button>}</div></td>
        </tr>)}
          {!items.length && <tr><td colSpan={7} className="empty">{list.isLoading ? "Loading…" : "No companies match. Add some with “＋ Add companies”."}</td></tr>}</tbody>
      </table></div>
      <Pager page={page} limit={25} total={list.data?.total ?? 0} onPage={setPage} />
      {edit && <EditCompany c={edit} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); refresh(); notify("Company saved.", "ok"); }} />}
      {add && <AddCompanies onClose={() => setAdd(false)} onDone={(m) => { setAdd(false); refresh(); notify(m, "ok"); }} />}
      {del && <Modal title={`Delete ${del.name}?`} onClose={() => setDel(null)}>
        <p>This removes the company and its <b>{num(del.open_jobs)}</b> open job(s) (and any pipeline entries pointing to them). It cannot be undone.</p>
        <div className="row" style={{ justifyContent: "flex-end" }}><button className="btn ghost" onClick={() => setDel(null)}>Cancel</button>
          <ActionButton className="btn danger" run={async () => { await api.del(`/admin/companies/${del.id}`); setDel(null); refresh(); notify(`Deleted ${del.name}.`, "ok"); }}>Delete</ActionButton></div></Modal>}
    </div>
  );
}

function EditCompany({ c, onClose, onSaved }: { c: Company; onClose(): void; onSaved(): void }) {
  const notify = useNotify();
  const [f, setF] = useState({ name: c.name, website: c.website ?? "", careers_url: c.careers_url ?? "", notes: c.notes ?? "" });
  return <Modal title={`Edit ${c.name}`} onClose={onClose}>
    <div className="field"><label>Name</label><input type="text" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></div>
    <div className="field"><label>Website</label><input type="text" value={f.website} onChange={(e) => setF({ ...f, website: e.target.value })} placeholder="https://company.com" /></div>
    <div className="field"><label>Careers page <span className="muted small">(changing it makes the next scan start from this URL)</span></label><input type="text" value={f.careers_url} onChange={(e) => setF({ ...f, careers_url: e.target.value })} placeholder="https://company.com/careers" /></div>
    <div className="field"><label>Notes</label><textarea rows={3} value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} style={{ fontFamily: "inherit" }} /></div>
    <div className="row" style={{ justifyContent: "flex-end" }}><button className="btn ghost" onClick={onClose}>Cancel</button>
      <ActionButton className="btn" run={async () => { try { await api.patch(`/admin/companies/${c.id}`, f); onSaved(); } catch (e) { notify((e as Error).message, "bad"); } }}>Save</ActionButton></div>
  </Modal>;
}

function AddCompanies({ onClose, onDone }: { onClose(): void; onDone(msg: string): void }) {
  const notify = useNotify(); const [text, setText] = useState(""); const [scan, setScan] = useState(true);
  const lines = text.split("\n").filter((l) => l.trim() && !l.startsWith("#")).length;
  return <Modal title="Add companies" onClose={onClose} wide>
    <div className="small muted">One per line: <code>Name</code>, <code>Name | https://site.com</code> or just a website. The crawler finds the careers page itself.</div>
    <textarea rows={8} value={text} onChange={(e) => setText(e.target.value)} placeholder={"Adyen | https://www.adyen.com\nMollie\nhttps://www.bunq.com"} autoFocus />
    <label className="small"><input type="checkbox" checked={scan} onChange={(e) => setScan(e.target.checked)} /> Scan the new companies right away</label>
    <div className="row" style={{ justifyContent: "flex-end" }}><button className="btn ghost" onClick={onClose}>Cancel</button>
      <ActionButton className="btn" disabled={!lines} run={async () => {
        try { const r = await api.post<{ added: number; already_known: number; ignored: string[] }>("/admin/companies/bulk", { text, scan }); onDone(`${r.added} added, ${r.already_known} already known${r.ignored.length ? `, ${r.ignored.length} ignored` : ""}.${scan && r.added ? " Scanning started." : ""}`); }
        catch (e) { notify((e as Error).message, "bad"); } }}>Add {lines || ""} {lines === 1 ? "company" : "companies"}</ActionButton></div>
  </Modal>;
}
