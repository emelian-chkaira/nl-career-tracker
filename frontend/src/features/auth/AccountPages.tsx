import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "@/shared/api/client";
import { useAuth } from "./AuthContext";

function Shell({ title, sub, children }: { title: string; sub?: string; children: ReactNode }) {
  return (<div className="authwrap" style={{ gridTemplateColumns: "1fr" }}><main className="authmain"><div className="authform stack">
    <Link to="/" className="brand"><i>NL</i><span>Career Tracker</span></Link>
    <div><h1>{title}</h1>{sub && <div className="muted">{sub}</div>}</div>{children}</div></main></div>);
}

export function ForgotPage() {
  const [email, setEmail] = useState(""); const [done, setDone] = useState(false); const [busy, setBusy] = useState(false); const [err, setErr] = useState("");
  async function submit(e: FormEvent) {
    e.preventDefault(); setErr(""); setBusy(true);
    try { await api.post("/auth/forgot", { email }); setDone(true); } catch (x) { setErr((x as Error).message); } finally { setBusy(false); }
  }
  if (done) return (<Shell title="Check your inbox" sub={`If an account exists for ${email}, we sent a link to choose a new password. It expires in 1 hour.`}>
    <Link className="btn lg" style={{ justifyContent: "center" }} to="/login">Back to sign in</Link></Shell>);
  return (<Shell title="Forgot your password?" sub="Enter your email and we'll send you a reset link.">
    <form className="stack" onSubmit={submit}>
      <div className="field"><label htmlFor="e">Email</label><input id="e" type="email" required placeholder="you@example.com" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" /></div>
      {err && <div className="notice err" role="alert">{err}</div>}
      <button className="btn lg" style={{ justifyContent: "center" }} disabled={busy || !email}>{busy ? "Sending…" : "Send reset link"}</button>
      <div className="small muted" style={{ textAlign: "center" }}><Link to="/login">Back to sign in</Link></div>
    </form></Shell>);
}

const codeOf = (q: URLSearchParams) => q.get("oobCode") ?? q.get("token") ?? "";     // Firebase links carry oobCode, the built-in flow token

export function ResetPage() {
  const token = codeOf(useSearchParams()[0]); const nav = useNavigate();
  const [pw, setPw] = useState(""); const [show, setShow] = useState(false); const [busy, setBusy] = useState(false); const [err, setErr] = useState(""); const [done, setDone] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault(); setErr(""); if (pw.length < 8) { setErr("Use at least 8 characters."); return; }
    setBusy(true);
    try { await api.post("/auth/reset", { token, new_password: pw }); setDone(true); setTimeout(() => nav("/login", { replace: true }), 2500); }
    catch (x) { setErr((x as Error).message); } finally { setBusy(false); }
  }
  if (!token) return <Shell title="Link not valid" sub="This reset link is incomplete."><Link className="btn lg" style={{ justifyContent: "center" }} to="/forgot">Request a new link</Link></Shell>;
  if (done) return <Shell title="Password updated" sub="You've been signed out everywhere. Redirecting to sign in…"><Link className="btn lg" style={{ justifyContent: "center" }} to="/login">Sign in now</Link></Shell>;
  return (<Shell title="Choose a new password">
    <form className="stack" onSubmit={submit}>
      <div className="field"><label htmlFor="p">New password</label>
        <div className="pw"><input id="p" type={show ? "text" : "password"} placeholder="At least 8 characters" value={pw} onChange={(e) => setPw(e.target.value)} autoComplete="new-password" />
          <button type="button" className="eye" onClick={() => setShow(!show)}>{show ? "Hide" : "Show"}</button></div></div>
      {err && <div className="notice err" role="alert">{err} {err.includes("expired") && <Link to="/forgot">Request a new link</Link>}</div>}
      <button className="btn lg" style={{ justifyContent: "center" }} disabled={busy}>{busy ? "Saving…" : "Update password"}</button>
    </form></Shell>);
}

export function VerifyPage() {
  const token = codeOf(useSearchParams()[0]); const { refresh } = useAuth();
  const [state, setState] = useState<"working" | "ok" | "bad">("working"); const ran = useRef(false);
  useEffect(() => {
    if (ran.current) return; ran.current = true;                       // React strict mode would otherwise spend the single-use token twice
    api.post("/auth/verify", { token }).then(() => { setState("ok"); refresh(); }).catch(() => setState("bad"));
  }, [token, refresh]);
  if (state === "working") return <Shell title="Confirming your email…"><p className="muted">One moment.</p></Shell>;
  if (state === "ok") return <Shell title="Email confirmed" sub="Thanks, your address is verified."><Link className="btn lg" style={{ justifyContent: "center" }} to="/">Go to jobs</Link></Shell>;
  return <Shell title="Link not valid" sub="This confirmation link is invalid or has expired. Sign in and request a new one."><Link className="btn lg" style={{ justifyContent: "center" }} to="/login">Sign in</Link></Shell>;
}

/** Banner for signed-in users who haven't confirmed their address yet. */
export function VerifyBanner() {
  const { user } = useAuth(); const [sent, setSent] = useState(false); const [err, setErr] = useState("");
  if (!user || user.email_verified) return null;
  return (<div className="notice" style={{ margin: "0 0 12px", display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
    <span>Confirm your email to secure your account and receive alerts.</span>
    {sent ? <b>Sent, check your inbox.</b> : <button className="btn small" onClick={async () => { try { await api.post("/auth/verify/send"); setSent(true); } catch (x) { setErr((x as Error).message); } }}>Resend email</button>}
    {err && <span className="err small">{err}</span>}</div>);
}

/** Single landing page for Firebase e-mail links (Authentication > Templates > customize action URL -> https://your-site/action). */
export function ActionPage() {
  const mode = useSearchParams()[0].get("mode");
  return mode === "verifyEmail" ? <VerifyPage /> : <ResetPage />;
}
