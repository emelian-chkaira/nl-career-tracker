import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, request } from "@/shared/api/client";
import { label } from "@/shared/lib/format";

type Provider = { id: string; label: string; kind: string; needs_key: boolean; base_url: string | null; models: string[]; tier: string; note: string };
type AiSettings = { provider: string; model: string | null; base_url: string | null; has_key: boolean };
type Account = { id: number; provider?: string; label: string; username: string; days_back: number; last_sync_at?: string | null; last_error?: string | null };
type Ev = { id: number; category: string; company?: string | null; role?: string | null; location?: string | null; event_date?: string | null; summary?: string | null; subject?: string | null; sender?: string | null;
  received_at?: string | null; confidence: number; classifier: string; status: string; company_known?: string | null; job?: { id: number; title: string } | null; suggested_stage?: string | null };
type Events = { items: Ev[]; counts: { category: Record<string, number>; status: Record<string, number> } };
type Prog = { phase?: string; scanned?: number; total?: number; found?: number; skipped?: number; duplicate?: number; unclassified?: number; ai_failed?: number };

const CATS = ["application_received", "interview_invite", "assessment", "offer", "rejection", "recruiter_outreach"];
const ICON: Record<string, string> = { application_received: "", interview_invite: "", assessment: "", offer: "", rejection: "", recruiter_outreach: "" };
const COLOR: Record<string, string> = { application_received: "#3b82f6", interview_invite: "#8b5cf6", assessment: "#f59e0b", offer: "#10b981", rejection: "#ef4444", recruiter_outreach: "#06b6d4" };
const hue = (t: string) => { let h = 0; for (const ch of t) h = (h * 31 + ch.charCodeAt(0)) % 360; return h; };
const TONE: Record<string, string> = { offer: "ok", interview_invite: "ok", assessment: "ok", rejection: "warn" };
const errText = (e: unknown) => (e instanceof Error ? e.message : String(e));
const when = (iso?: string | null) => { if (!iso) return "never"; const m = Math.round((Date.now() - new Date(iso).getTime()) / 60000); return m < 1 ? "just now" : m < 60 ? `${m} min ago` : m < 1440 ? `${Math.round(m / 60)} h ago` : `${Math.round(m / 1440)} d ago`; };

export function InboxPage() {
  const [tab, setTab] = useState<"review" | "manual" | "ai">("review");
  const [cat, setCat] = useState("");
  const events = useQuery({ queryKey: ["mail-events"], queryFn: () => api.get<Events>("/mail/events") });
  const c = events.data?.counts; const n = c?.status.new ?? 0;
  const tiles: [string, string, number, string][] = [["new", "To review", n, ""], ["interview_invite", "Interviews", c?.category.interview_invite ?? 0, ""], ["assessment", "Tests", c?.category.assessment ?? 0, ""], ["offer", "Offers", c?.category.offer ?? 0, ""], ["rejection", "Rejections", c?.category.rejection ?? 0, ""], ["application_received", "Applied", c?.category.application_received ?? 0, ""]];
  return (
    <div className="stack">
      <div className="inbox-banner">
        <div><h1>Inbox assistant</h1>
          <p>Your job-search mail, sorted for you. We read your Gmail <b>read-only</b> and pick out the replies that matter: interviews, tests, offers and, yes, the rejections too.</p></div>
        <div className="inbox-banner-n"><b>{(c?.status.new ?? 0) + (c?.status.accepted ?? 0)}</b><span>job e-mails tracked</span></div>
      </div>
      <Connection />
      <div className="inbox-tiles">
        {tiles.map(([k, t, v, ic]) => <button key={k} className={`inbox-tile ${k !== "new" && cat === k ? "on" : ""}`} style={{ ["--c" as string]: COLOR[k] ?? "var(--brand)" }} onClick={() => { setTab("review"); setCat(k === "new" || cat === k ? "" : k); }}>
          <span className="ic">{ic}</span><b>{v}</b><span className="lb">{t}</span></button>)}
      </div>
      <div className="tabs">
        {([["review", `Review${n ? ` (${n})` : ""}`], ["manual", "Add manually"], ["ai", "AI model"]] as const).map(([k, t]) => <button key={k} className={`tab ${tab === k ? "on" : ""}`} onClick={() => setTab(k)}>{t}</button>)}
      </div>
      {tab === "review" && <Review cat={cat} setCat={setCat} />}
      {tab === "manual" && <Manual />}
      {tab === "ai" && <AiPanel />}
    </div>
  );
}

/* ------------------------------------------------------------------ Gmail connection + sync */
function Connection() {
  const qc = useQueryClient();
  const accs = useQuery({ queryKey: ["mail-accounts"], queryFn: () => api.get<Account[]>("/mail/accounts") });
  const ai = useQuery({ queryKey: ["ai-settings"], queryFn: () => api.get<AiSettings>("/ai/settings") });
  const gm = useQuery({ queryKey: ["gmail-status"], queryFn: () => api.get<{ configured: boolean; redirect_uri: string }>("/mail/gmail/status"), staleTime: Infinity });
  const [msg, setMsg] = useState(""); const [prog, setProg] = useState<Prog | null>(null); const [state, setState] = useState<"idle" | "running" | "done" | "failed">("idle");
  const [days, setDays] = useState(60); const [consent, setConsent] = useState(false);
  const a = accs.data?.[0];
  const usesExternalAi = !!ai.data && !["rules", "ollama"].includes(ai.data.provider);
  const refresh = () => { qc.invalidateQueries({ queryKey: ["mail-accounts"] }); qc.invalidateQueries({ queryKey: ["mail-events"] }); };
  useEffect(() => {
    const q = new URLSearchParams(window.location.search), g = q.get("gmail"); if (!g) return;
    setMsg(g === "connected" ? "✓ Gmail connected. Press “Sync now” to read your recent e-mails." : g === "denied" ? "✗ Google sign-in was cancelled." : "✗ Gmail sign-in failed" + (q.get("reason") ? `: ${q.get("reason")}` : "."));
    window.history.replaceState({}, "", window.location.pathname); refresh();
  }, []);
  const connect = async () => { setMsg(""); try { const { url } = await api.post<{ url: string }>("/mail/gmail/start", {}); window.location.href = url; } catch (e) { setMsg("✗ " + errText(e)); } };
  const run = async () => {
    if (!a) return; setState("running"); setMsg(""); setProg({ phase: "starting" });
    try {
      const { task_id } = await api.post<{ task_id: number }>("/mail/sync", { account_id: a.id, days, consent });
      for (let i = 0; i < 1200; i++) {
        await new Promise((r) => setTimeout(r, 1500));
        const t = await api.get<{ status: string; progress: Prog; error?: string }>(`/mail/sync/${task_id}`);
        setProg(t.progress ?? {}); if (i % 3 === 0) qc.invalidateQueries({ queryKey: ["mail-events"] });
        if (t.status === "failed") { setState("failed"); setMsg("✗ " + (t.error ?? "Sync failed")); break; }
        if (t.status === "done") { setState("done"); break; }
      }
    } catch (e) { setState("failed"); setMsg("✗ " + errText(e)); }
    refresh();
  };
  const disconnect = async () => { if (window.confirm("Disconnect Gmail? The saved Google access is deleted. Events already extracted stay until you delete them.")) { await api.del(`/mail/accounts/${a!.id}`); setState("idle"); setProg(null); refresh(); } };
  const pct = prog?.total ? Math.min(100, Math.round(((prog.scanned ?? 0) / prog.total) * 100)) : 0;
  if (!a) return (
    <div className="card inbox-hero fancy">
      <div style={{ flex: 1, minWidth: 260 }}>
        <h2 style={{ margin: "0 0 6px" }}>Connect your Gmail</h2>
        <ul className="small muted" style={{ margin: 0, paddingLeft: 18, lineHeight: 1.7 }}>
          <li>You sign in on <b>Google's own page</b>. No password is shared.</li>
          <li><b>Read-only</b>: nothing is deleted, moved or marked as read.</li>
          <li>Only extracted facts (company, role, status) are kept, <b>never the e-mail text</b>.</li>
          <li>Revoke any time at myaccount.google.com/permissions.</li>
        </ul>
        {msg && <div className={`small ${msg.startsWith("✗") ? "err" : "ok"}`} style={{ marginTop: 8 }}>{msg}</div>}
      </div>
      <div className="stack" style={{ alignItems: "flex-start", gap: 8 }}>
        <button className="btn" disabled={!gm.data?.configured} onClick={connect}>Connect Gmail</button>
        {gm.data && !gm.data.configured && <span className="small muted" style={{ maxWidth: 320 }}>Not set up on this server yet. Add <code>CAREERS_GOOGLE_CLIENT_SECRET</code> and the redirect URI <code>{gm.data.redirect_uri}</code>, see docs/GMAIL_OAUTH.md.</span>}
      </div>
    </div>);
  return (
    <div className="card stack fancy">
      <div className="row" style={{ gap: 12, flexWrap: "wrap", alignItems: "center" }}>
        <span className="avatar" style={{ flex: "none" }}>{a.username[0]?.toUpperCase()}</span>
        <div style={{ flex: 1, minWidth: 200 }}><b>{a.username}</b> <span className="chip ok" style={{ margin: 0 }}>● connected</span>
          <div className="small muted">{a.last_error ? <span className="err">{a.last_error}</span> : `last read ${when(a.last_sync_at)}`}</div></div>
        <select value={days} onChange={(e) => setDays(+e.target.value)} aria-label="How far back to read" disabled={state === "running"}>{[[14, "Last 2 weeks"], [30, "Last 30 days"], [60, "Last 60 days"], [90, "Last 90 days"], [180, "Last 6 months"], [365, "Last year"]].map(([v, t]) => <option key={v} value={v}>{t}</option>)}</select>
        <button className="btn" disabled={state === "running" || (usesExternalAi && !consent)} onClick={run}>{state === "running" ? "Reading…" : "Sync now"}</button>
        <button className="btn ghost small" onClick={disconnect}>Disconnect</button>
      </div>
      {usesExternalAi && <label className="small"><input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} /> I agree that the text of my job e-mails is sent to <b>{ai.data?.provider}</b> to be analysed.</label>}
      {state === "running" && prog && <div className="stack" style={{ gap: 4 }}>
        <div className="progress"><div style={{ width: `${prog.phase === "analysing" ? pct : 6}%` }} /></div>
        <div className="small muted">{prog.phase === "analysing" ? `Analysing ${prog.scanned ?? 0} / ${prog.total ?? 0} e-mails · ${prog.found ?? 0} job e-mails found` : "Reading your mailbox from Gmail… this can take a minute or two."}</div></div>}
      {state === "done" && prog && <div className="small">
        <span className="ok">✓ Read {prog.scanned ?? 0} e-mails</span> · <b>{prog.found ?? 0}</b> job e-mails added to Review{prog.duplicate ? ` · ${prog.duplicate} already known` : ""} · {Math.max(0, (prog.skipped ?? 0) - (prog.unclassified ?? 0))} not job related.
        {!!prog.unclassified && <div className="muted">{prog.unclassified} looked job-related but the built-in rules could not tell what they are. Choose an AI model (tab “AI model”) to classify them.</div>}
        {!!prog.ai_failed && <div className="muted">The AI failed on {prog.ai_failed} e-mails; the rules were used instead.</div>}
        {!prog.found && !prog.unclassified && !prog.duplicate && <div className="muted">Nothing job-related in this period. Try a longer period.</div>}
      </div>}
      {msg && <div className={`small ${msg.startsWith("✗") ? "err" : "ok"}`}>{msg}</div>}
    </div>);
}

/* ------------------------------------------------------------------ Manual */
function Manual() {
  const qc = useQueryClient();
  const ai = useQuery({ queryKey: ["ai-settings"], queryFn: () => api.get<AiSettings>("/ai/settings") });
  const [paste, setPaste] = useState({ subject: "", sender: "", text: "" }); const [consent, setConsent] = useState(false); const [msg, setMsg] = useState(""); const files = useRef<HTMLInputElement>(null);
  const usesExternalAi = !!ai.data && !["rules", "ollama"].includes(ai.data.provider);
  const done = () => qc.invalidateQueries({ queryKey: ["mail-events"] });
  const importPaste = async () => {
    setMsg("");
    try { const r = await api.post<{ found: number; duplicate: number }>("/mail/import", { ...paste, consent }); setMsg(r.found ? "✓ Added to Review." : r.duplicate ? "Already imported." : "Not recognised as a job e-mail."); if (r.found) setPaste({ subject: "", sender: "", text: "" }); done(); }
    catch (e) { setMsg("✗ " + errText(e)); }
  };
  const importFiles = async () => {
    const list = files.current?.files; if (!list?.length) return; const fd = new FormData(); Array.from(list).forEach((x) => fd.append("files", x));
    try { const r = await request<{ found: number }>("POST", "/mail/import-eml", { raw: fd, query: { consent } }); setMsg(`✓ ${r.found} job e-mails found.`); done(); } catch (e) { setMsg("✗ " + errText(e)); }
  };
  return (
    <div className="card stack">
      <h2 style={{ margin: 0 }}>Paste an e-mail or upload .eml files</h2>
      <div className="small muted">For mail that is not in your Gmail (another provider, a forwarded message). Handled the same way as synced mail.</div>
      <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
        <input type="text" placeholder="Subject" value={paste.subject} onChange={(e) => setPaste({ ...paste, subject: e.target.value })} style={{ flex: 1, minWidth: 180 }} />
        <input type="text" placeholder="From (e.g. Acme Talent <jobs@acme.com>)" value={paste.sender} onChange={(e) => setPaste({ ...paste, sender: e.target.value })} style={{ flex: 1, minWidth: 180 }} />
      </div>
      <textarea rows={6} placeholder="Paste the e-mail text here" value={paste.text} onChange={(e) => setPaste({ ...paste, text: e.target.value })} />
      {usesExternalAi && <label className="small"><input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} /> Send this text to {ai.data?.provider} for analysis</label>}
      <div className="row" style={{ gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <button className="btn small" disabled={paste.text.length < 10 || (usesExternalAi && !consent)} onClick={importPaste}>Analyse pasted e-mail</button>
        <span className="muted small">or</span><input ref={files} type="file" accept=".eml" multiple onChange={importFiles} />
      </div>
      {msg && <div className={`small ${msg.startsWith("✗") ? "err" : "ok"}`}>{msg}</div>}
    </div>);
}

/* ------------------------------------------------------------------ AI */
function AiPanel() {
  const qc = useQueryClient();
  const provs = useQuery({ queryKey: ["ai-providers"], queryFn: () => api.get<Provider[]>("/ai/providers"), staleTime: Infinity });
  const cur = useQuery({ queryKey: ["ai-settings"], queryFn: () => api.get<AiSettings>("/ai/settings") });
  const [f, setF] = useState({ provider: "rules", model: "", base_url: "", api_key: "" });
  const [msg, setMsg] = useState(""); const [busy, setBusy] = useState(false);
  useEffect(() => { if (cur.data) setF({ provider: cur.data.provider, model: cur.data.model ?? "", base_url: cur.data.base_url ?? "", api_key: "" }); }, [cur.data]);
  const p = provs.data?.find((x) => x.id === f.provider);
  const pick = (id: string) => { const q = provs.data?.find((x) => x.id === id); setF({ provider: id, model: q?.models[0] ?? "", base_url: "", api_key: "" }); setMsg(""); };
  const save = async (test = false) => {
    setBusy(true); setMsg("");
    try {
      await api.put("/ai/settings", { provider: f.provider, model: f.model || null, base_url: f.base_url || null, ...(f.api_key ? { api_key: f.api_key } : {}) });
      await qc.invalidateQueries({ queryKey: ["ai-settings"] });
      if (test) { const r = await api.post<{ detail: string }>("/ai/test"); setMsg("✓ " + r.detail); } else setMsg("Saved.");
    } catch (e) { setMsg("✗ " + errText(e)); } finally { setBusy(false); }
  };
  const groups: [string, string[]][] = [["Free / private", ["rules", "ollama"]], ["Chinese models (free tiers or very cheap)", ["zhipu", "qwen", "deepseek", "moonshot"]], ["Many models, some free", ["openrouter"]], ["Bring your own paid key", ["anthropic", "openai"]], ["Your own endpoint", ["custom"]]];
  return (
    <div className="card stack">
      <h2 style={{ margin: 0 }}>Which AI should read your e-mails?</h2>
      <div className="field"><label htmlFor="prov">Provider</label>
        <select id="prov" value={f.provider} onChange={(e) => pick(e.target.value)}>
          {groups.map(([g, ids]) => <optgroup key={g} label={g}>{ids.map((id) => { const q = provs.data?.find((x) => x.id === id); return q ? <option key={id} value={id}>{q.label}</option> : null; })}</optgroup>)}
        </select></div>
      {p && <div className="small muted">{p.note} {p.tier !== "free" && <span className="chip plain">{p.tier}</span>}</div>}
      {p && p.kind !== "rules" && <>
        <div className="field"><label htmlFor="model">Model <span className="muted small">(pick one or type any model name)</span></label>
          <input id="model" type="text" list="models" value={f.model} onChange={(e) => setF({ ...f, model: e.target.value })} placeholder="model name" />
          <datalist id="models">{p.models.map((m) => <option key={m} value={m} />)}</datalist></div>
        {(f.provider === "custom" || f.provider === "ollama" || f.base_url) && <div className="field"><label htmlFor="url">Base URL</label>
          <input id="url" type="text" value={f.base_url} onChange={(e) => setF({ ...f, base_url: e.target.value })} placeholder={p.base_url || "https://your-server/v1"} /></div>}
        {(p.needs_key || f.provider === "custom") && <div className="field"><label htmlFor="key">API key {cur.data?.has_key && cur.data.provider === f.provider && <span className="chip ok">saved</span>}</label>
          <input id="key" type="password" value={f.api_key} onChange={(e) => setF({ ...f, api_key: e.target.value })} autoComplete="off" placeholder={cur.data?.has_key && cur.data.provider === f.provider ? "leave empty to keep the saved key" : "paste your key"} />
          <div className="small muted">Stored encrypted on the server, never shown again. Remove it any time by saving an empty key.</div></div>}
        {f.provider !== "ollama" && <div className="small muted">⚠ Your e-mails' text is sent to this provider to be analysed, so the provider's privacy terms apply. Choose the built-in rules or a local Ollama model to keep everything on your machine.</div>}
      </>}
      <div className="row" style={{ gap: 8 }}>
        <button className="btn" disabled={busy} onClick={() => save(false)}>Save</button>
        {p?.kind !== "rules" && <button className="btn ghost" disabled={busy} onClick={() => save(true)}>Save and test</button>}
      </div>
      {msg && <div className={`small ${msg.startsWith("✗") ? "err" : "ok"}`}>{msg}</div>}
    </div>
  );
}

/* ------------------------------------------------------------------ Review */
function Review({ cat, setCat }: { cat: string; setCat: (c: string) => void }) {
  const qc = useQueryClient();
  const [status, setStatus] = useState("new"); const [q, setQ] = useState(""); const [note, setNote] = useState("");
  const all = useQuery({ queryKey: ["mail-events"], queryFn: () => api.get<Events>("/mail/events") });
  const list = useQuery({ queryKey: ["mail-events", status, cat, q], queryFn: () => api.get<Events>("/mail/events", { status, category: cat, q }) });
  const act = async (id: number, a: "accept" | "dismiss") => {
    const r = await api.post<{ stage?: string | null }>(`/mail/events/${id}/${a}`); if (a === "accept") setNote(r.stage ? `Moved your pipeline job to “${label(r.stage)}”.` : "Kept. No pipeline job was linked, so nothing moved."); qc.invalidateQueries({ queryKey: ["mail-events"] });
  };
  const edit = async (id: number, body: object) => { await api.patch(`/mail/events/${id}`, body); qc.invalidateQueries({ queryKey: ["mail-events"] }); };
  const bulk = async (ids: number[], action: string) => { await api.post("/mail/events/bulk", { ids, action }); qc.invalidateQueries({ queryKey: ["mail-events"] }); };
  const counts = all.data?.counts; const items = list.data?.items ?? [];
  const sure = items.filter((e) => e.confidence >= 0.75 && e.status === "new").map((e) => e.id);
  return (
    <div className="stack">
      <div className="inbox-bar">
        <div className="seg">{([["new", "To review", counts?.status.new ?? 0], ["accepted", "Kept", counts?.status.accepted ?? 0], ["dismissed", "Dismissed", counts?.status.dismissed ?? 0], ["", "All", 0]] as const).map(([k, t, v]) =>
          <button key={k} className={status === k ? "on" : ""} onClick={() => setStatus(k)}>{t}{k ? <i>{v}</i> : null}</button>)}</div>
        <div className="searchwrap"><input type="search" placeholder="Search company, role or subject" value={q} onChange={(e) => setQ(e.target.value)} /></div>
        {!!sure.length && <button className="btn small" onClick={() => bulk(sure, "accept")}>Accept {sure.length} confident</button>}
        {!!items.length && <button className="btn ghost small" onClick={async () => { if (window.confirm("Delete everything extracted from your e-mails?")) { await api.del("/mail/events"); qc.invalidateQueries({ queryKey: ["mail-events"] }); } }}>Delete all</button>}
      </div>
      <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
        {CATS.map((c) => <button key={c} className={`catchip ${cat === c ? "on" : ""}`} style={{ ["--c" as string]: COLOR[c] }} onClick={() => setCat(cat === c ? "" : c)}>{label(c)} <i>{counts?.category[c] ?? 0}</i></button>)}
        {cat && <button className="catchip" onClick={() => setCat("")}>Clear filter ✕</button>}
      </div>
      {note && <div className="small ok">{note}</div>}
      {list.isLoading && [0, 1, 2].map((i) => <div key={i} className="skel" style={{ height: 96 }} />)}
      {!list.isLoading && !items.length && <div className="card empty">{counts && Object.keys(counts.status).length ? "Nothing here with these filters." : "It's quiet in here. Press “Sync now” and we'll look through your Gmail, or add an e-mail by hand."}</div>}
      {items.map((e) => (
        <div key={e.id} className="inbox-ev" style={{ ["--c" as string]: COLOR[e.category] ?? "var(--brand)", opacity: e.status === "dismissed" ? 0.55 : 1 }}>
          <div className="logo" style={{ background: `hsl(${hue(e.company ?? e.sender ?? "?")} 70% 45%)` }}>{(e.company ?? e.sender ?? "?").trim()[0]?.toUpperCase()}</div>
          <div className="body">
            <div className="evtop">
              <b>{e.company ?? "Unknown company"}</b>{e.role && <span className="role">{e.role}</span>}
              <span className="pill">{label(e.category)}</span>
              <span className="meta">{e.received_at ? new Date(e.received_at).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : ""}</span>
            </div>
            {e.summary && <div className="sum">{e.summary}</div>}
            <div className="sub">{e.subject}{e.event_date ? ` · ${e.event_date}` : ""}</div>
            <div className="link">{e.job ? <>Linked to your pipeline job <b>{e.job.title}</b>{e.suggested_stage && <> → will move to <b>{label(e.suggested_stage)}</b></>}</> : <span className="muted">{e.company_known ? `“${e.company_known}” is in the tracker, but none of your pipeline jobs matches.` : "Not linked to a job."}</span>}</div>
            <div className="foot">
              <span className="conf" title={`${Math.round(e.confidence * 100)}% confident · ${e.classifier}`}><i style={{ width: `${Math.round(e.confidence * 100)}%` }} /></span><span className="muted small">{Math.round(e.confidence * 100)}% · {e.classifier}</span>
              {e.status === "new" && <span className="acts">
                <select value={e.category} onChange={(x) => edit(e.id, { category: x.target.value })} aria-label="Change category">{CATS.map((c) => <option key={c} value={c}>{label(c)}</option>)}</select>
                <button className="btn ghost small" onClick={() => { const c = window.prompt("Company", e.company ?? ""); if (c !== null) edit(e.id, { company: c }); }}>Edit company</button>
                <button className="btn ghost small" onClick={() => act(e.id, "dismiss")}>Dismiss</button>
                <button className="btn small" onClick={() => act(e.id, "accept")}>{e.job ? "Accept & update pipeline" : "Keep"}</button>
              </span>}
            </div>
          </div>
        </div>))}
    </div>
  );
}
