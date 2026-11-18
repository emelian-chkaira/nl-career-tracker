import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useAuth } from "@/features/auth/AuthContext";
import { ApiError } from "@/shared/api/client";
import type { SearchParams } from "@/shared/api/types";
import { parseQs, qs } from "@/shared/lib/format";
import { SaveSearchButton } from "@/features/alerts/SaveSearchButton";
import { liveSearch, taskStatus, useJobSearch, useSuggest } from "./api";
import { Filters } from "./Filters";
import { JobCard } from "./JobCard";
import { JobDetail, JobDrawer } from "./JobDrawer";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/shared/api/client";
import { useQueryClient } from "@tanstack/react-query";

const ARR = ["job_type", "language", "city", "skills"] as const;
function fromUrl(search: string, internships: boolean): SearchParams {
  const raw = parseQs(search); const p: Record<string, unknown> = { ...raw };
  for (const k of ARR) p[k] = raw[k] === undefined ? [] : ([] as string[]).concat(raw[k]);
  for (const k of ["remote", "sponsor"]) if (raw[k] !== undefined) p[k] = raw[k] === "true";
  for (const k of ["min_salary", "days", "page"]) if (raw[k] !== undefined) p[k] = Number(raw[k]);
  if (internships) p.kind = "internship";
  return { limit: 20, ...p } as SearchParams;
}

function useWide() {
  const [w, setW] = useState(() => window.matchMedia("(min-width:1101px)").matches);
  useEffect(() => { const m = window.matchMedia("(min-width:1101px)"); const f = () => setW(m.matches); m.addEventListener("change", f); return () => m.removeEventListener("change", f); }, []);
  return w;
}
const QUICK = ["python", "react", "flutter", "data engineer", "devops", "machine learning", "backend", "intern"];

export function JobsPage({ internships = false }: { internships?: boolean }) {
  const [sp, setSp] = useSearchParams();
  const params = useMemo(() => fromUrl(sp.toString(), internships), [sp, internships]);
  const [q, setQ] = useState(params.q ?? ""); const [open, setOpen] = useState<number | null>(null);
  const { user } = useAuth(); const qc = useQueryClient();
  const { data, isFetching, error } = useJobSearch(params);
  const sug = useSuggest(q.split(/\s+/).pop() ?? "");
  useEffect(() => setQ(params.q ?? ""), [params.q]);

  const update = (patch: Partial<SearchParams>, keepPage = false) => {
    const next = { ...params, ...patch, ...(keepPage ? {} : { page: 1 }) } as Record<string, unknown>; delete next.limit; delete next.kind;
    setSp(qs(next), { replace: true });
  };
  const [live, setLive] = useState("");
  async function runLive() {
    if (!q.trim()) return;
    try {
      setLive("Re-reading career pages…"); const { task_id } = await liveSearch(q);
      for (let i = 0; i < 40; i++) {
        await new Promise((r) => setTimeout(r, 3000)); const t = await taskStatus(task_id);
        if (t.status === "done" || t.status === "failed") { setLive(t.status === "done" ? "Live search finished — results refreshed." : "Live search failed."); qc.invalidateQueries({ queryKey: ["jobs"] }); return; }
        setLive(`Re-reading career pages… ${JSON.stringify(t.progress ?? {})}`);
      }
      setLive("Still running in the background; refresh in a minute.");
    } catch (e) { setLive(e instanceof ApiError ? e.message : "Live search unavailable"); }
  }
  const wide = useWide();
  const stats = useQuery({ queryKey: ["hero-stats"], staleTime: 300_000, queryFn: () => api.get<{ kpi: { open_jobs: number; hiring_companies: number; internships: number; new_7d: number } }>("/analytics/overview", { days: 30 }) });
  const k = stats.data?.kpi;
  useEffect(() => { if (wide && data?.items.length && (open == null || !data.items.some((j) => j.id === open))) setOpen(data.items[0].id); }, [wide, data]);   // eslint-disable-line react-hooks/exhaustive-deps
  const pages = data ? Math.max(1, Math.ceil(data.total / data.limit)) : 1;
  return (<div>
    <section className="hero">
      <h1>{internships ? "Find your internship in the Netherlands" : "Tech jobs in the Netherlands, straight from the source"}</h1>
      <p>Every posting is read from the employer's own career page — no aggregators, no duplicates. IND sponsor status is shown as a flag.</p>
      <form className="searchbar" onSubmit={(e) => { e.preventDefault(); update({ q }); }}>
        <input type="search" list="sug" placeholder={'Job title, skill or company — try  flutter -senior  or  "data engineer"'} value={q} onChange={(e) => setQ(e.target.value)} />
        <datalist id="sug">{[...(sug.data?.skills ?? []), ...(sug.data?.titles ?? [])].slice(0, 8).map((s) => <option key={s} value={q.replace(/\S*$/, "") + s} />)}</datalist>
        <select value={params.mode ?? "hybrid"} onChange={(e) => update({ mode: e.target.value as SearchParams["mode"] })} title="Search mode"><option value="hybrid">Smart</option><option value="keyword">Exact words</option><option value="semantic">By meaning</option></select>
        <select value={params.sort ?? ""} onChange={(e) => update({ sort: e.target.value || undefined })}><option value="">Best match</option><option value="newest">Newest</option><option value="oldest">Oldest</option><option value="salary">Salary</option>{user && <option value="fit">My fit</option>}</select>
        <button className="btn lg">Search</button>
      </form>
      <div className="quick">{QUICK.map((t) => <button key={t} onClick={() => { setQ(t); update({ q: t }); }}>{t}</button>)}</div>
      {k && <div className="stats"><div><b>{k.open_jobs.toLocaleString()}</b><span>open roles</span></div><div><b>{k.hiring_companies.toLocaleString()}</b><span>hiring companies</span></div><div><b>{k.internships.toLocaleString()}</b><span>internships</span></div><div><b>{k.new_7d.toLocaleString()}</b><span>new this week</span></div></div>}
    </section>
    <div className="row small muted" style={{ marginTop: 14 }}><strong style={{ color: "var(--text)" }}>{data ? `${data.total.toLocaleString()} results` : ""}</strong>{isFetching && <span>updating…</span>}
      <button className="btn ghost small" onClick={runLive} disabled={!q.trim()}>⟳ Re-read employers live</button><span>{live}</span>{user && <span className="right"><SaveSearchButton params={params} /></span>}</div>
    <div className={"layout" + (wide ? "" : " noDetail")}>
      <Filters params={params} facets={data?.facets} onChange={(p) => update(p)} />
      <div className="card list">
        {!data && !error && Array.from({ length: 6 }, (_, i) => <div key={i} className="job"><div className="skel logo" /><div className="grow stack" style={{ gap: 8 }}><div className="skel" style={{ height: 16, width: "70%" }} /><div className="skel" style={{ height: 12, width: "45%" }} /></div></div>)}
        {error && <div className="empty err">{(error as Error).message}</div>}
        {data && !data.items.length && <div className="empty">No jobs match. Loosen the filters or re-read employers live.</div>}
        {data?.items.map((j) => <JobCard key={j.id} job={j} selected={wide && open === j.id} onOpen={setOpen} />)}
        {data && pages > 1 && <div className="pager">
          <button className="btn ghost small" disabled={(params.page ?? 1) <= 1} onClick={() => update({ page: (params.page ?? 1) - 1 }, true)}>← Prev</button>
          <span className="muted small">Page {params.page ?? 1} of {pages}</span>
          <button className="btn ghost small" disabled={(params.page ?? 1) >= pages} onClick={() => update({ page: (params.page ?? 1) + 1 }, true)}>Next →</button></div>}
      </div>
      {wide && <div className="card detail inline">{open != null ? <JobDetail id={open} /> : <div className="empty">Select a job to read it here.</div>}</div>}
    </div>
    {!wide && open != null && <JobDrawer id={open} onClose={() => setOpen(null)} />}
  </div>);
}
