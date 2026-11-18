import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "@/shared/api/client";
import type { SearchResult } from "@/shared/api/types";
import { ago } from "@/shared/lib/format";
import { qs } from "@/shared/lib/format";
import { useNotifications, useReadNotifications, useSavedSearches, useSearchMutations } from "./api";

export function AlertsPage() {
  const { data: searches } = useSavedSearches(); const { data: notes } = useNotifications();
  const { update, remove } = useSearchMutations(); const read = useReadNotifications();
  return (<div className="stack">
    <div><h1>Alerts</h1><div className="muted">Saved searches are checked every few minutes; new matches create a notification and (if SMTP is configured) an e-mail.</div></div>
    <div className="grid two">
      <div className="card stack"><h2>Saved searches</h2>
        {!searches?.length && <div className="muted">Nothing saved yet — use “Save & alert” on the Jobs page.</div>}
        {searches?.map((s) => <div key={s.id} className="row" style={{ borderBottom: "1px solid var(--line)", paddingBottom: 8 }}>
          <div className="grow"><Link to={`/?${qs(s.params as Record<string, unknown>)}`}><strong>{s.name}</strong></Link><div className="small muted">{s.params.q || "all jobs"} · last checked {ago(s.last_run_at) || "never"}</div><Preview id={s.id} /></div>
          <select value={s.alert_frequency} onChange={(e) => update.mutate({ id: s.id, alert_frequency: e.target.value })}>
            <option value="off">No alerts</option><option value="instant">Instant</option><option value="daily">Daily</option><option value="weekly">Weekly</option></select>
          <button className="btn ghost small" onClick={() => confirm("Delete this search?") && remove.mutate(s.id)}>Delete</button></div>)}
      </div>
      <div className="card stack"><div className="row"><h2>Notifications</h2>{!!notes?.unread && <button className="btn ghost small right" onClick={() => read.all.mutate()}>Mark all read</button>}</div>
        {!notes?.items.length && <div className="muted">No notifications yet.</div>}
        {notes?.items.map((n) => <div key={n.id} style={{ opacity: n.read ? 0.6 : 1 }} onClick={() => !n.read && read.one.mutate(n.id)}>
          <strong>{n.title}</strong> <span className="muted small">{ago(n.created_at)}</span><div className="small" style={{ whiteSpace: "pre-line" }}>{n.body}</div></div>)}
      </div>
    </div>
  </div>);
}
function Preview({ id }: { id: number }) {
  const { data } = useQuery({ queryKey: ["preview", id], queryFn: () => api.get<SearchResult>(`/me/searches/${id}/preview`), staleTime: 60_000 });
  return data ? <div className="small">{data.total} current matches</div> : null;
}
