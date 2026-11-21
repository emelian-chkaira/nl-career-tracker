import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/shared/api/client";
import { ActionButton, ago, useNotify } from "./ui";

type U = { id: string; email: string; role: string; active: boolean; created_at: string };
export function UsersTab() {
  const qc = useQueryClient(); const notify = useNotify();
  const users = useQuery({ queryKey: ["admin-users"], queryFn: () => api.get<U[]>("/admin/users") });
  const set = async (u: U, body: object, msg: string) => { await api.patch(`/admin/users/${u.id}`, body); notify(`${u.email}: ${msg}`, "ok"); qc.invalidateQueries({ queryKey: ["admin-users"] }); };
  return <div className="tablewrap"><table className="dtable"><thead><tr><th>E-mail</th><th>Role</th><th>Status</th><th>Joined</th><th /></tr></thead>
    <tbody>{users.data?.map((u) => <tr key={u.id}><td>{u.email}</td><td><span className={`badge ${u.role === "admin" ? "ok" : ""}`}>{u.role}</span></td><td><span className={`badge ${u.active ? "ok" : "bad"}`}>{u.active ? "active" : "disabled"}</span></td><td className="small muted">{ago(u.created_at)}</td>
      <td><div className="actions"><ActionButton className="iconbtn" run={() => set(u, { role: u.role === "admin" ? "user" : "admin" }, u.role === "admin" ? "now a regular user" : "now an admin")}>{u.role === "admin" ? "Make user" : "Make admin"}</ActionButton>
        <ActionButton className="iconbtn" run={() => set(u, { is_active: !u.active }, u.active ? "disabled" : "enabled")}>{u.active ? "Disable" : "Enable"}</ActionButton></div></td></tr>)}</tbody></table></div>;
}
