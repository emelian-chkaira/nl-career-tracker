import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/shared/api/client";
import { label } from "@/shared/lib/format";
import { ActionButton, Modal, Spinner, num, useNotify } from "./ui";

type Policy = { keep_domains: string[]; max_job_age_days: number; delete_expired_after_days: number; by_domain: Record<string, number>; defaults: { keep_domains: string[]; max_job_age_days: number; delete_expired_after_days: number } };
const DOMAINS = ["mobile", "frontend", "backend", "fullstack", "software", "data", "devops", "security", "qa", "embedded", "design", "product", "other"];

const ACTIONS: { id: string; title: string; what: string; danger?: boolean }[] = [
  { id: "backfill_domains", title: "Classify jobs", what: "Give every job that has no domain one (mobile, backend, data …). Safe — nothing is deleted." },
  { id: "purge", title: "Purge old jobs", what: "Delete jobs that vanished from the employer's page long ago, and jobs older than the age limit. Jobs saved in a pipeline stay." },
  { id: "prune", title: "Apply storage policy", what: "Delete stored jobs whose domain you no longer keep (plus everything Purge removes). Jobs saved in a pipeline stay." },
  { id: "clear_jobs", title: "Clear all jobs", what: "Delete every job, including from users' pipelines. Companies stay, so the next scan refills the database.", danger: true },
  { id: "clear_all", title: "Clear jobs and companies", what: "Empty the whole catalogue. Accounts, alerts and saved searches stay.", danger: true },
];
const nice = (k: string) => k.replace(/_/g, " ");

export function StorageTab({ isAdmin }: { isAdmin: boolean }) {
  const qc = useQueryClient(); const notify = useNotify();
  const q = useQuery({ queryKey: ["admin-policy"], queryFn: () => api.get<Policy>("/admin/policy") });
  const p = q.data;
  const [keep, setKeep] = useState<string[]>([]); const [age, setAge] = useState(0); const [exp, setExp] = useState(0);
  useEffect(() => { if (p) { setKeep(p.keep_domains); setAge(p.max_job_age_days); setExp(p.delete_expired_after_days); } }, [p]);
  const dirty = !!p && (JSON.stringify([...keep].sort()) !== JSON.stringify(p.keep_domains) || age !== p.max_job_age_days || exp !== p.delete_expired_after_days);
  const [log, setLog] = useState<{ at: string; title: string; text: string; ok: boolean }[]>([]);
  const [ask, setAsk] = useState<(typeof ACTIONS)[number] | null>(null);
  if (!p) return <div className="card muted">Loading…</div>;
  const max = Math.max(1, ...Object.values(p.by_domain)); const total = Object.values(p.by_domain).reduce((a, b) => a + b, 0);
  const save = async () => { try { await api.put("/admin/policy", { keep_domains: keep, max_job_age_days: age, delete_expired_after_days: exp }); await qc.invalidateQueries({ queryKey: ["admin-policy"] }); notify("Storage policy saved. New scans use it right away; run “Apply storage policy” to clean what is already stored.", "ok"); } catch (e) { notify((e as Error).message, "bad"); } };
  return (
    <div className="stack">
      <div className="card stack">
        <div className="row" style={{ justifyContent: "space-between" }}><h2 style={{ margin: 0 }}>What should be stored?</h2>{!isAdmin && <span className="badge">view only — ask an admin to change</span>}</div>
        <div><div className="small" style={{ marginBottom: 6 }}><b>Job domains to keep</b> <span className="muted">— {keep.length ? `only ${keep.length} selected` : "none selected = keep every domain"}</span></div>
          <div className="domgrid">{DOMAINS.map((d) => <label key={d} className={keep.includes(d) ? "on" : ""}><input type="checkbox" disabled={!isAdmin} checked={keep.includes(d)} onChange={() => setKeep((k) => (k.includes(d) ? k.filter((x) => x !== d) : [...k, d]))} />{label(d)}{p.by_domain[d] ? <span className="muted small">{num(p.by_domain[d])}</span> : null}</label>)}</div></div>
        <div className="row" style={{ gap: 18, alignItems: "flex-end" }}>
          <div className="field"><label>Don't store jobs older than (days)</label><input type="number" min={0} disabled={!isAdmin} value={age} onChange={(e) => setAge(Math.max(0, +e.target.value))} style={{ width: 130 }} /><div className="small muted">0 = no limit</div></div>
          <div className="field"><label>Delete vanished jobs after (days)</label><input type="number" min={0} disabled={!isAdmin} value={exp} onChange={(e) => setExp(Math.max(0, +e.target.value))} style={{ width: 130 }} /><div className="small muted">0 = keep forever</div></div>
        </div>
        {isAdmin && <div className="row"><ActionButton className="btn" disabled={!dirty} run={save}>Save policy</ActionButton>
          <button className="btn ghost" disabled={!dirty} onClick={() => { setKeep(p.keep_domains); setAge(p.max_job_age_days); setExp(p.delete_expired_after_days); }}>Undo changes</button>
          <ActionButton className="btn ghost" run={async () => { await api.del("/admin/policy"); await qc.invalidateQueries({ queryKey: ["admin-policy"] }); notify("Back to the defaults from .env.", "ok"); }}>Reset to .env defaults</ActionButton>
          {dirty && <span className="small warn">unsaved changes</span>}</div>}
        <div className="small muted">Saved in the database and applied to every new scan within seconds. Defaults come from <code>.env</code> ({p.defaults.keep_domains.join(", ") || "all domains"}, {p.defaults.max_job_age_days || "no"} day limit).</div>
      </div>

      <div className="card stack">
        <h2 style={{ margin: 0 }}>Stored jobs by domain <span className="muted small">· {num(total)} open</span></h2>
        {Object.entries(p.by_domain).map(([d, n]) => <div key={d} className="row" style={{ gap: 8, margin: "2px 0" }}>
          <span style={{ width: 110 }} className="small">{label(d)}</span><div style={{ flex: 1, height: 8, borderRadius: 999, background: "var(--panel2)" }}><div style={{ width: `${(n / max) * 100}%`, height: "100%", borderRadius: 999, background: p.keep_domains.length && !p.keep_domains.includes(d) ? "var(--warn)" : "var(--brand)" }} /></div>
          <span className="small muted" style={{ width: 60, textAlign: "right" }}>{num(n)}</span></div>)}
        {p.keep_domains.length > 0 && <div className="small muted">Orange bars are outside the domains you keep — “Apply storage policy” removes them.</div>}
      </div>

      {isAdmin ? <div className="card stack">
        <h2 style={{ margin: 0 }}>Housekeeping</h2>
        {ACTIONS.map((a) => <ActionRow key={a.id} a={a} onAsk={() => setAsk(a)} />)}
        {!!log.length && <div className="stack" style={{ gap: 4 }}><div className="small muted">Results (this session)</div>{log.map((l, i) => <div key={i} className={`small ${l.ok ? "" : "err"}`}>{l.at} · <b>{l.title}</b> — {l.text}</div>)}</div>}
      </div> : <div className="card small muted">Housekeeping (purge, clear, apply policy) is available to admins.</div>}
      {ask && <RunModal a={ask} onClose={() => setAsk(null)} onResult={(r, ok) => { setLog((l) => [{ at: new Date().toLocaleTimeString(), title: ask.title, text: r, ok }, ...l].slice(0, 8)); notify(`${ask.title}: ${r}`, ok ? "ok" : "bad"); setAsk(null); ["admin-policy", "admin-stats", "admin-worker", "co", "jobs-admin"].forEach((k) => qc.invalidateQueries({ queryKey: [k] })); }} />}
    </div>
  );
}

function usePreview(id: string) { return useQuery({ queryKey: ["preview", id], queryFn: () => api.get<Record<string, number>>(`/admin/maintenance/${id}/preview`), refetchInterval: 20000 }); }
const sum = (o?: Record<string, number>) => Object.entries(o ?? {}).filter(([k]) => k !== "pipeline_entries_lost" && k !== "nothing_to_do").reduce((a, [, v]) => a + v, 0);

function ActionRow({ a, onAsk }: { a: (typeof ACTIONS)[number]; onAsk(): void }) {
  const pv = usePreview(a.id); const n = sum(pv.data);
  return <div className="opt"><div><b>{a.title}</b><div className="small muted">{a.what}</div>
    <div className="small" style={{ marginTop: 4 }}>{pv.isLoading ? <Spinner /> : n ? <span className={a.danger ? "err" : "warn"}>Right now this would affect <b>{num(n)}</b> row(s): {Object.entries(pv.data ?? {}).map(([k, v]) => `${num(v)} ${nice(k)}`).join(", ")}.</span> : <span className="ok">Nothing to do right now.</span>}</div></div>
    <button className={`btn small ${a.danger ? "danger" : ""}`} disabled={!n && !a.danger} onClick={onAsk}>{a.title}…</button></div>;
}

function RunModal({ a, onClose, onResult }: { a: (typeof ACTIONS)[number]; onClose(): void; onResult(text: string, ok: boolean): void }) {
  const pv = usePreview(a.id); const [sure, setSure] = useState(false);
  return <Modal title={a.title} onClose={onClose}>
    <p className="small">{a.what}</p>
    <div className="card" style={{ padding: 12 }}>{pv.isLoading ? <Spinner /> : Object.entries(pv.data ?? {}).map(([k, v]) => <div key={k} className="row" style={{ justifyContent: "space-between" }}><span>{nice(k)}</span><b>{num(v)}</b></div>)}</div>
    {a.danger && <label className="small"><input type="checkbox" checked={sure} onChange={(e) => setSure(e.target.checked)} /> I understand this cannot be undone.</label>}
    <div className="row" style={{ justifyContent: "flex-end" }}><button className="btn ghost" onClick={onClose}>Cancel</button>
      <ActionButton className={`btn ${a.danger ? "danger" : ""}`} disabled={a.danger && !sure} run={async () => {
        try { const r = await api.post<Record<string, number>>(`/admin/maintenance/${a.id}`, a.danger ? { confirm: true } : {}); const e = Object.entries(r); onResult(e.length ? e.map(([k, v]) => `${num(v)} ${nice(k)}`).join(", ") : "done", true); }
        catch (e) { onResult((e as Error).message, false); } }}>Run now</ActionButton></div></Modal>;
}
