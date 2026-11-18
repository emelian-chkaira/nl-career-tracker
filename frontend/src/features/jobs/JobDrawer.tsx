import { Link } from "react-router-dom";
import { useAuth } from "@/features/auth/AuthContext";
import { label, ago } from "@/shared/lib/format";
import { useJob, useSetStage } from "./api";
import { Logo, sponsorChip } from "./JobCard";

const STAGES = ["shortlisted", "applied", "screening", "interview", "offer", "accepted", "rejected", "withdrawn", "skipped"];

/** Plain-text description -> paragraphs, bullet lists and sub-headings (no HTML injection: everything is rendered as React text). */
function Description({ text }: { text: string }) {
  const blocks: JSX.Element[] = []; let list: string[] = [];
  const flush = () => { if (list.length) { blocks.push(<ul key={"u" + blocks.length}>{list.map((x, i) => <li key={i}>{x}</li>)}</ul>); list = []; } };
  text.split(/\n+/).map((l) => l.trim()).filter(Boolean).forEach((l) => {
    if (/^[-*•·]\s+/.test(l)) list.push(l.replace(/^[-*•·]\s+/, ""));
    else { flush(); blocks.push(/^[^.!?]{3,60}:$/.test(l) && l.split(" ").length <= 7 ? <h4 key={blocks.length}>{l.replace(/:$/, "")}</h4> : <p key={blocks.length}>{l}</p>); }
  });
  flush();
  return <div className="desc">{blocks}</div>;
}

export function JobDetail({ id, onClose }: { id: number; onClose?: () => void }) {
  const { data: j, isLoading, error } = useJob(id);
  const { user } = useAuth(); const setStage = useSetStage();
  if (isLoading) return <div className="bd stack"><div className="skel" style={{ height: 64 }} /><div className="skel" style={{ height: 14 }} /><div className="skel" style={{ height: 240 }} /></div>;
  if (error || !j) return <div className="bd err">{(error as Error)?.message ?? "Not found"}</div>;
  return (<>
    <div className="hd">
      <div className="row" style={{ alignItems: "flex-start", flexWrap: "nowrap" }}>
        <Logo c={j.company} big />
        <div className="grow" style={{ minWidth: 0 }}>
          <h1 style={{ fontSize: 22 }}>{j.title}</h1>
          <div className="muted">{j.company.name} · {j.location ?? "Netherlands"} · {ago(j.posted_at ?? j.first_seen)}</div>
        </div>
        {onClose && <button className="btn ghost small" onClick={onClose}>✕</button>}
      </div>
      <div style={{ margin: "12px 0 4px" }}>{sponsorChip(j.company.sponsor_status)}<span className="chip">{label(j.job_type)}</span>{j.language !== "unknown" && <span className="chip">{label(j.language)}</span>}{j.remote && <span className="chip">Remote friendly</span>}</div>
      <div className="row">
        <a className="btn" href={j.url} target="_blank" rel="noreferrer noopener">Apply on company site ↗</a>
        <Link className="btn ghost" to={`/cv?job=${j.id}`}>Tailor CV & letter</Link>
        {user && <select value={j.stage ?? ""} onChange={(e) => setStage.mutate({ id: j.id, stage: e.target.value })} title="Pipeline stage">
          <option value="" disabled>Track…</option>{STAGES.map((s) => <option key={s} value={s}>{label(s)}</option>)}</select>}
        {!user && <span className="small muted"><Link to="/login">Sign in</Link> to track</span>}
      </div>
    </div>
    <div className="bd stack">
      {j.skills.length > 0 && <div><h3>Skills mentioned</h3>{j.skills.map((s) => <span className="chip" key={s}>{s}</span>)}</div>}
      <div><h3>About the role</h3>{j.description ? <Description text={j.description} /> : <p className="muted">No description captured — open the posting on the company site.</p>}</div>
      {j.company.sponsor_match && <div className="small muted">IND register match: {j.company.sponsor_match}. A flag only; confirm with the employer.</div>}
    </div>
  </>);
}

export function JobDrawer({ id, onClose }: { id: number; onClose(): void }) {
  return (<><div className="scrim" onClick={onClose} /><aside className="drawer" aria-label="Job details"><JobDetail id={id} onClose={onClose} /></aside></>);
}
