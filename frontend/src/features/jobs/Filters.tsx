import type { Facet, SearchParams } from "@/shared/api/types";
import { label } from "@/shared/lib/format";

function Group({ title, facets, selected, onToggle, fmt = (v: string) => v }: { title: string; facets?: Facet[]; selected: string[]; onToggle(v: string): void; fmt?: (v: string) => string }) {
  if (!facets?.length) return null;
  return (<div className="facet" style={{ marginBottom: 12 }}><h3>{title}</h3>
    {facets.slice(0, 8).map((f) => <label key={f.value}><input type="checkbox" checked={selected.includes(f.value)} onChange={() => onToggle(f.value)} />{fmt(f.value)}<span className="n">{f.count}</span></label>)}</div>);
}
const toggle = (arr: string[] | undefined, v: string) => { const a = arr ?? []; return a.includes(v) ? a.filter((x) => x !== v) : [...a, v]; };

export function Filters({ params, facets, onChange }: { params: SearchParams; facets?: Record<string, Facet[]>; onChange(p: Partial<SearchParams>): void }) {
  return (<div className="card">
    <Group title="Type" facets={facets?.job_type} selected={params.job_type ?? []} onToggle={(v) => onChange({ job_type: toggle(params.job_type, v) })} fmt={label} />
    <Group title="Domain" facets={facets?.domain} selected={params.domain ?? []} onToggle={(v) => onChange({ domain: toggle(params.domain, v) })} fmt={label} />
    <Group title="City" facets={facets?.city} selected={params.city ?? []} onToggle={(v) => onChange({ city: toggle(params.city, v) })} />
    <Group title="Language" facets={facets?.language} selected={params.language ?? []} onToggle={(v) => onChange({ language: toggle(params.language, v) })} fmt={label} />
    <Group title="Skills" facets={facets?.skills} selected={params.skills ?? []} onToggle={(v) => onChange({ skills: toggle(params.skills, v) })} />
    <div className="facet">
      <label><input type="checkbox" checked={!!params.remote} onChange={(e) => onChange({ remote: e.target.checked || undefined })} />Remote friendly</label>
      <label><input type="checkbox" checked={!!params.sponsor} onChange={(e) => onChange({ sponsor: e.target.checked || undefined })} />Recognised sponsor only</label>
    </div>
    <div className="row" style={{ marginTop: 10 }}>
      <select value={params.days ?? ""} onChange={(e) => onChange({ days: e.target.value ? +e.target.value : undefined })}>
        <option value="">Any date</option><option value="1">Last 24h</option><option value="7">Last 7 days</option><option value="30">Last 30 days</option></select>
      <select value={params.skills_mode ?? "any"} onChange={(e) => onChange({ skills_mode: e.target.value as "any" | "all" })}><option value="any">any skill</option><option value="all">all skills</option></select>
    </div>
    <div className="row" style={{ marginTop: 10 }}><input type="number" placeholder="Min € / month" style={{ width: 130 }} value={params.min_salary ?? ""} onChange={(e) => onChange({ min_salary: e.target.value ? +e.target.value : undefined })} /></div>
  </div>);
}
