import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "@/shared/api/client";
import { label, money } from "@/shared/lib/format";

interface Overview {
  kpi: { open_jobs: number; hiring_companies: number; internships: number; new_7d: number; prev_7d: number; remote_jobs: number; english_ok: number; with_salary: number; sponsor_jobs: number };
  daily: { day: string; new_jobs: number }[]; cities: { name: string; jobs: number }[]; types: { name: string; jobs: number }[]; languages: { name: string; jobs: number }[];
  companies: { name: string; jobs: number }[]; skills: { name: string; jobs: number; last_30d: number; prev_30d: number; trend: number | null }[];
  salary: { name: string; n: number; avg: number; median: number }[];
}
const COLORS = ["#2f5bea", "#12a27a", "#e08a1e", "#c2410c", "#7c3aed", "#0891b2", "#be185d"];
const Kpi = ({ v, t, s }: { v: string | number; t: string; s?: string }) => <div className="card kpi"><div className="muted small">{t}</div><div className="v">{typeof v === "number" ? v.toLocaleString() : v}</div>{s && <div className="small muted">{s}</div>}</div>;

export function DashboardPage() {
  const [days, setDays] = useState(90); const [kind, setKind] = useState("");
  const { data: d, isLoading, error } = useQuery({ queryKey: ["analytics", days, kind], queryFn: () => api.get<Overview>("/analytics/overview", { days, kind }) });
  if (isLoading) return <p className="muted">Loading market data…</p>;
  if (error || !d) return <p className="err">{(error as Error)?.message ?? "No data"}</p>;
  const k = d.kpi; const wow = k.prev_7d ? Math.round(((k.new_7d - k.prev_7d) / k.prev_7d) * 100) : null;
  const salaryMedian = d.salary.find((x) => x.name === "job")?.median ?? d.salary[0]?.median;
  const tick = { fill: "var(--muted)", fontSize: 12 };
  return (<div className="stack">
    <div className="row"><div><h1>Market dashboard</h1><div className="muted">Open tech roles in the Netherlands, from employers' own career pages.</div></div>
      <select className="right" value={kind} onChange={(e) => setKind(e.target.value)}><option value="">Jobs + internships</option><option value="job">Jobs</option><option value="internship">Internships</option></select>
      <select value={days} onChange={(e) => setDays(+e.target.value)}><option value={30}>30 days</option><option value={90}>90 days</option><option value={180}>180 days</option></select></div>
    <div className="grid kpis">
      <Kpi v={k.open_jobs} t="Open roles" /><Kpi v={k.hiring_companies} t="Hiring companies" /><Kpi v={k.new_7d} t="New this week" s={wow == null ? undefined : `${wow >= 0 ? "▲" : "▼"} ${Math.abs(wow)}% vs previous week`} />
      <Kpi v={k.internships} t="Internships" /><Kpi v={k.remote_jobs} t="Remote friendly" /><Kpi v={k.english_ok} t="English-friendly" /><Kpi v={k.sponsor_jobs} t="At IND-listed sponsors" />
      <Kpi v={salaryMedian ? money(salaryMedian) : "–"} t="Median salary / mo" s={`${k.with_salary} postings state pay`} />
    </div>
    <div className="card"><h2>New postings per day</h2><ResponsiveContainer width="100%" height={220}><AreaChart data={d.daily}><CartesianGrid stroke="var(--line)" vertical={false} />
      <XAxis dataKey="day" tick={tick} tickFormatter={(v) => v.slice(5)} minTickGap={30} /><YAxis tick={tick} width={34} /><Tooltip contentStyle={{ background: "var(--panel)", border: "1px solid var(--line)" }} />
      <Area dataKey="new_jobs" name="New jobs" stroke="#2f5bea" fill="#2f5bea33" /></AreaChart></ResponsiveContainer></div>
    <div className="grid two">
      <Bars title="Top cities" data={d.cities} /><Bars title="Top hiring companies" data={d.companies} />
      <div className="card"><h2>Contract type</h2><ResponsiveContainer width="100%" height={220}><PieChart><Pie data={d.types.map((t) => ({ ...t, name: label(t.name) }))} dataKey="jobs" nameKey="name" outerRadius={80} label>
        {d.types.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}</Pie><Tooltip /></PieChart></ResponsiveContainer></div>
      <div className="card"><h2>In-demand skills (30d vs previous 30d)</h2>
        <table className="table"><thead><tr><th>Skill</th><th>Jobs (30d)</th><th>Trend</th></tr></thead><tbody>
          {d.skills.slice(0, 14).map((s) => <tr key={s.name}><td>{s.name}</td><td>{s.last_30d}</td><td className={s.trend == null ? "muted" : s.trend >= 0 ? "ok" : "err"}>{s.trend == null ? "new" : `${s.trend >= 0 ? "▲" : "▼"} ${Math.abs(Math.round(s.trend))}%`}</td></tr>)}</tbody></table></div>
    </div>
  </div>);
}
function Bars({ title, data }: { title: string; data: { name: string; jobs: number }[] }) {
  return <div className="card"><h2>{title}</h2><ResponsiveContainer width="100%" height={Math.max(180, data.slice(0, 10).length * 26)}>
    <BarChart data={data.slice(0, 10)} layout="vertical" margin={{ left: 20 }}><XAxis type="number" hide /><YAxis type="category" dataKey="name" width={120} tick={{ fill: "var(--muted)", fontSize: 12 }} />
      <Tooltip contentStyle={{ background: "var(--panel)", border: "1px solid var(--line)" }} cursor={{ fill: "var(--chip)" }} /><Bar dataKey="jobs" fill="#2f5bea" radius={[0, 4, 4, 0]} /></BarChart></ResponsiveContainer></div>;
}
