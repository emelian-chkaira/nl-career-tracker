import { useState } from "react";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "@/shared/api/client";
import type { Company } from "@/shared/api/types";
import { sponsorChip } from "@/features/jobs/JobCard";

export function CompaniesPage() {
  const [q, setQ] = useState(""); const [hiring, setHiring] = useState(true); const [page, setPage] = useState(1);
  const { data } = useQuery({ queryKey: ["companies", q, hiring, page], placeholderData: keepPreviousData, queryFn: () => api.get<{ items: Company[]; total: number; limit: number }>("/companies", { q, hiring, page }) });
  return (<div className="stack"><div><h1>Companies</h1><div className="muted">{data?.total.toLocaleString() ?? "…"} tech companies tracked</div></div>
    <div className="row"><input type="search" className="grow" placeholder="Filter by name or description" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
      <label className="row small"><input type="checkbox" checked={hiring} onChange={(e) => { setHiring(e.target.checked); setPage(1); }} />Only hiring now</label></div>
    <div className="grid two">{data?.items.map((c) => <div key={c.id} className="card row">
      {c.logo ? <img className="logo" src={c.logo.startsWith("/") || c.logo.startsWith("http") ? c.logo : `/logos/${c.logo}`} alt="" /> : <div className="logo">{c.name[0]}</div>}
      <div className="grow" style={{ minWidth: 0 }}><strong>{c.name}</strong> {sponsorChip(c.sponsor_status)}<div className="small muted">{c.city ?? ""} · {c.open_jobs ?? 0} open roles</div>
        <div className="small"><Link to={`/?company_id=${c.id}`}>View jobs</Link>{c.careers_url && <> · <a href={c.careers_url} target="_blank" rel="noreferrer noopener">Careers page ↗</a></>}</div></div></div>)}</div>
    {data && data.total > data.limit && <div className="row"><button className="btn ghost small" disabled={page <= 1} onClick={() => setPage(page - 1)}>← Prev</button><span className="muted small">Page {page}</span>
      <button className="btn ghost small" disabled={page * data.limit >= data.total} onClick={() => setPage(page + 1)}>Next →</button></div>}
  </div>);
}
