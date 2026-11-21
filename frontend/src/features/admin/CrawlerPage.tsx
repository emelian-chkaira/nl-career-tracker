import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/shared/api/client";
import { useAuth } from "@/features/auth/AuthContext";
import { WorkerPanel } from "./WorkerPanel";
import { CompaniesTab } from "./CompaniesTab";
import { JobsTab } from "./JobsTab";
import { StorageTab } from "./StorageTab";
import { TasksPanel } from "./TasksTab";
import { UsersTab } from "./UsersTab";
import { NotifyProvider, num } from "./ui";

type Stats = { companies: number; companies_scanned: number; companies_with_jobs: number; open_jobs: number; users: number; sponsors: number; scan_outcomes: { note: string; n: number }[] };
type Tab = "overview" | "companies" | "jobs" | "storage" | "tasks" | "users";

export function CrawlerPage() {
  const isAdmin = useAuth().user?.role === "admin";
  const [tab, setTab] = useState<Tab>("overview");
  const stats = useQuery({ queryKey: ["admin-stats"], refetchInterval: 15000, queryFn: () => api.get<Stats>("/admin/stats") });
  const s = stats.data;
  const tabs: [Tab, string, string?][] = [["overview", "Overview"], ["companies", "Companies", s ? num(s.companies) : undefined], ["jobs", "Jobs", s ? num(s.open_jobs) : undefined], ["storage", "Storage & cleanup"], ["tasks", "Tasks"], ...(isAdmin ? [["users", "Users", s ? num(s.users) : undefined] as [Tab, string, string?]] : [])];
  return (
    <NotifyProvider>
      <div className="stack">
        <div><h1 style={{ marginBottom: 4 }}>Crawler</h1><div className="muted">See what the crawler is up to, tidy the companies and jobs it has saved, and decide what is worth keeping.</div></div>
        <div className="tabs" role="tablist">{tabs.map(([k, l, c]) => <button key={k} role="tab" aria-selected={tab === k} className={`tab ${tab === k ? "on" : ""}`} onClick={() => setTab(k)}>{l}{c && <span className="count">{c}</span>}</button>)}</div>
        {tab === "overview" && <Overview s={s} go={setTab} />}
        {tab === "companies" && <CompaniesTab isAdmin={isAdmin} />}
        {tab === "jobs" && <JobsTab isAdmin={isAdmin} />}
        {tab === "storage" && <StorageTab isAdmin={isAdmin} />}
        {tab === "tasks" && <TasksPanel />}
        {tab === "users" && isAdmin && <UsersTab />}
      </div>
    </NotifyProvider>
  );
}

function Overview({ s, go }: { s?: Stats; go(t: Tab): void }) {
  const kpi: [string, number | undefined, Tab][] = [["Companies", s?.companies, "companies"], ["Scanned", s?.companies_scanned, "companies"], ["With open jobs", s?.companies_with_jobs, "companies"], ["Open jobs", s?.open_jobs, "jobs"], ["IND sponsors", s?.sponsors, "companies"]];
  return (
    <div className="stack">
      <WorkerPanel />
      <div className="statrow">{kpi.map(([l, v, t]) => <div key={l} style={{ cursor: "pointer" }} onClick={() => go(t)}><b>{num(v)}</b><span>{l}</span></div>)}</div>
      {!!s?.scan_outcomes?.length && <div className="card stack"><h2 style={{ margin: 0 }}>How the last scans ended</h2>
        {s.scan_outcomes.map((o) => <div key={o.note} className="row" style={{ gap: 8 }}><span style={{ flex: 1 }} className="small">{o.note}</span><span className="small muted">{num(o.n)}</span></div>)}</div>}
      <div className="card stack"><div className="row" style={{ justifyContent: "space-between" }}><h2 style={{ margin: 0 }}>Run something now</h2><button className="btn ghost small" onClick={() => go("tasks")}>All tasks →</button></div><TasksPanel compact /></div>
    </div>
  );
}
