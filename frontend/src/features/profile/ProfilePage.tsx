import { useState } from "react";
import { api } from "@/shared/api/client";
import { useAuth } from "@/features/auth/AuthContext";

const csv = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);
export function ProfilePage() {
  const { user, saveProfile } = useAuth(); const p = user!.profile;
  const [skills, setSkills] = useState((p.skills ?? []).join(", ")); const [titles, setTitles] = useState((p.titles ?? []).join(", ")); const [cities, setCities] = useState((p.cities ?? []).join(", "));
  const [english, setEnglish] = useState(!!p.english_only); const [msg, setMsg] = useState("");
  const [cur, setCur] = useState(""); const [next, setNext] = useState(""); const [pmsg, setPmsg] = useState("");
  return (<div className="stack"><div><h1>Profile</h1><div className="muted">{user!.email} · {user!.role}. Skills and cities power the “My fit” sort.</div></div>
    <form className="card stack" onSubmit={async (e) => { e.preventDefault(); try { await saveProfile({ ...p, skills: csv(skills), titles: csv(titles), cities: csv(cities), english_only: english }); setMsg("Saved"); } catch (x) { setMsg((x as Error).message); } }}>
      <label>Skills (comma separated)<input type="text" style={{ width: "100%" }} value={skills} onChange={(e) => setSkills(e.target.value)} placeholder="flutter, dart, python" /></label>
      <label>Target titles<input type="text" style={{ width: "100%" }} value={titles} onChange={(e) => setTitles(e.target.value)} placeholder="mobile developer, software engineer" /></label>
      <label>Preferred cities<input type="text" style={{ width: "100%" }} value={cities} onChange={(e) => setCities(e.target.value)} placeholder="Eindhoven, Amsterdam" /></label>
      <label className="row"><input type="checkbox" checked={english} onChange={(e) => setEnglish(e.target.checked)} />English-only roles</label>
      <div className="row"><button className="btn">Save profile</button><span className="muted small">{msg}</span></div></form>
    <form className="card stack" onSubmit={async (e) => { e.preventDefault(); try { await api.post("/auth/password", { current_password: cur, new_password: next }); setPmsg("Password changed"); setCur(""); setNext(""); } catch (x) { setPmsg((x as Error).message); } }}>
      <h2>Change password</h2><input type="password" placeholder="Current password" value={cur} onChange={(e) => setCur(e.target.value)} required autoComplete="current-password" />
      <input type="password" placeholder="New password (min 8)" minLength={8} value={next} onChange={(e) => setNext(e.target.value)} required autoComplete="new-password" />
      <div className="row"><button className="btn ghost">Change</button><span className="muted small">{pmsg}</span></div></form>
  </div>);
}
