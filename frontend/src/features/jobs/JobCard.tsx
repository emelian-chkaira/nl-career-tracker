import type { Job } from "@/shared/api/types";
import { ago, label, money } from "@/shared/lib/format";

export function Logo({ c, big = false }: { c: Job["company"]; big?: boolean }) {
  const cls = "logo" + (big ? " lg" : "");
  return c.logo ? <img className={cls} src={c.logo.startsWith("http") || c.logo.startsWith("/") ? c.logo : `/logos/${c.logo}`} alt="" loading="lazy" /> : <div className={cls}>{c.name[0]}</div>;
}
export const sponsorChip = (s: string) => (s === "recognised" ? <span className="chip ok">IND sponsor</span> : s === "possible" ? <span className="chip warn">Possible sponsor</span> : null);
const isNew = (d?: string | null) => !!d && Date.now() - new Date(d).getTime() < 3 * 86400000;

export function JobCard({ job, selected, onOpen }: { job: Job; selected?: boolean; onOpen(id: number): void }) {
  const when = job.posted_at ?? job.first_seen;
  return (
    <div className={"job" + (selected ? " sel" : "")} onClick={() => onOpen(job.id)} role="button" tabIndex={0} onKeyDown={(e) => e.key === "Enter" && onOpen(job.id)}>
      <Logo c={job.company} />
      <div className="grow" style={{ minWidth: 0 }}>
        <div className="t">{job.title}</div>
        <div className="meta">{job.company.name} · {job.city ?? job.location ?? "Netherlands"}{job.remote ? " · Remote" : ""}</div>
        {job.snippet && <div className="small muted" style={{ margin: "4px 0", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }} dangerouslySetInnerHTML={{ __html: sanitize(job.snippet) }} />}
        <div style={{ marginTop: 6 }}>
          {isNew(when) && <span className="chip ok">New</span>}
          <span className="chip">{label(job.job_type)}</span>
          {sponsorChip(job.company.sponsor_status)}
          {job.fit != null && <span className="chip ok" title={job.fit_reason ?? ""}>{job.fit}% fit</span>}
          {job.stage && <span className="chip warn">{label(job.stage)}</span>}
          {job.salary?.min != null && <span className="chip plain">{money(job.salary.min)}{job.salary.max ? `–${money(job.salary.max)}` : ""}/{job.salary.period ?? "mo"}</span>}
          {job.skills.slice(0, 3).map((s) => <span key={s} className="chip plain">{s}</span>)}
        </div>
      </div>
      <div className="small muted" style={{ whiteSpace: "nowrap" }}>{ago(when)}</div>
    </div>
  );
}
/** Snippets come from ts_headline and may only contain <mark>; strip everything else. */
function sanitize(html: string) { return html.replace(/<(?!\/?mark>)[^>]*>/gi, ""); }
