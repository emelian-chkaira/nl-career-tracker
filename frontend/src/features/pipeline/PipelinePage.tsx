import { useQuery } from "@tanstack/react-query";
import { api } from "@/shared/api/client";
import type { Job } from "@/shared/api/types";
import { label, ago } from "@/shared/lib/format";
import { useSetStage } from "@/features/jobs/api";
import { useState } from "react";
import { JobDrawer } from "@/features/jobs/JobDrawer";

export function PipelinePage() {
  const { data } = useQuery({ queryKey: ["pipeline"], queryFn: () => api.get<{ stages: string[]; items: Job[] }>("/me/pipeline") });
  const set = useSetStage(); const [open, setOpen] = useState<number | null>(null);
  if (!data) return <p className="muted">Loading…</p>;
  const stages = data.stages.filter((s) => s !== "skipped");
  return (<div className="stack"><div><h1>Pipeline</h1><div className="muted">Track every application from shortlist to offer.</div></div>
    {!data.items.length && <div className="card empty">Open a job and choose a pipeline stage to start tracking.</div>}
    <div className="board">{stages.map((s) => { const items = data.items.filter((j) => j.stage === s); return (
      <div key={s} className="card stack" style={{ background: "var(--bg)" }}><h3>{label(s)} <span className="muted">{items.length}</span></h3>
        {items.map((j) => <div key={j.id} className="card" style={{ padding: 10 }}>
          <a href="#" onClick={(e) => { e.preventDefault(); setOpen(j.id); }}><strong>{j.title}</strong></a><div className="small muted">{j.company.name} · {ago((j as { updated_at?: string }).updated_at)}</div>
          <select style={{ marginTop: 6, width: "100%" }} value={j.stage ?? ""} onChange={(e) => set.mutate({ id: j.id, stage: e.target.value })}>{data.stages.map((x) => <option key={x} value={x}>{label(x)}</option>)}</select></div>)}</div>); })}</div>
    {open != null && <JobDrawer id={open} onClose={() => setOpen(null)} />}
  </div>);
}
