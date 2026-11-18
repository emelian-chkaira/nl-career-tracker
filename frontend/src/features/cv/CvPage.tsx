import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "@/shared/api/client";

interface CvData { name: string; email: string; phone: string; location: string; links: string[]; summary: string; skills: string[]; languages: string[]; references?: string[]; skill_groups?: unknown; certifications: string[]; order?: string[]; [k: string]: unknown }
interface Extracted { cv: CvData; latex: string; source?: string }
interface Tailored { text: string; latex?: string; changes?: string[]; matched: string[]; gaps: string[]; match_score: number; keywords: string[] }
interface AiOut { cv: CvData; latex: string; changes: { section: string; title: string; before: string; after: string }[]; gaps: string[]; notes: string; job: { title: string; company: string } }
interface PdfOut { pdf_b64: string; engine: string; bytes: number }
type Mode = "local" | "public";
const KEY = "cv-draft-v2";
const load = (): Extracted | null => { try { return JSON.parse(localStorage.getItem(KEY) ?? "null"); } catch { return null; } };
const save = (v: Extracted | null) => { try { v ? localStorage.setItem(KEY, JSON.stringify(v)) : localStorage.removeItem(KEY); } catch { /* quota */ } };

function Tags({ items, onChange, placeholder }: { items: string[]; onChange(v: string[]): void; placeholder: string }) {
  const [v, setV] = useState("");
  const add = () => { const t = v.trim(); if (t) onChange([...items, t]); setV(""); };
  return (<div className="stack" style={{ gap: 8 }}>
    <div className="tags">{items.map((t, i) => <span className="tag" key={i}>{t}<button aria-label="remove" onClick={() => onChange(items.filter((_, j) => j !== i))}>×</button></span>)}</div>
    <input type="text" value={v} placeholder={placeholder} onChange={(e) => setV(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }} onBlur={add} />
  </div>);
}
const Field = ({ label, children }: { label: string; children: React.ReactNode }) => <div className="field"><label>{label}</label>{children}</div>;

export function CvPage() {
  const [sp] = useSearchParams(); const [jobId, setJobId] = useState(sp.get("job") ?? "");
  const [cv, setCvState] = useState<Extracted | null>(load); const [tailored, setTailored] = useState<Tailored | null>(null); const [letter, setLetter] = useState("");
  const [pdf, setPdf] = useState<{ url: string; engine: string; bytes: number } | null>(null);
  const [busy, setBusy] = useState(""); const [err, setErr] = useState(""); const [tone, setTone] = useState("professional");
  const [mode, setMode] = useState<Mode>("local"); const [consent, setConsent] = useState(false); const [localOk, setLocalOk] = useState<boolean | null>(null);
  const [aiOk, setAiOk] = useState(false); const [aiConsent, setAiConsent] = useState(false); const [ai, setAi] = useState<AiOut | null>(null);
  const [over, setOver] = useState(false); const fileRef = useRef<HTMLInputElement>(null); const [dirty, setDirty] = useState(false);

  useEffect(() => { api.get<{ local: boolean; ai: boolean }>("/cv/compilers").then((r) => { setLocalOk(r.local); setAiOk(r.ai); if (!r.local) setMode("public"); }).catch(() => setLocalOk(false)); }, []);
  const setCv = (v: Extracted | null) => { setCvState(v); save(v); };
  const run = async (name: string, fn: () => Promise<void>) => { setBusy(name); setErr(""); try { await fn(); } catch (e) { setErr((e as Error).message); } finally { setBusy(""); } };
  const edit = (patch: Partial<CvData>) => { if (!cv) return; setCv({ ...cv, cv: { ...cv.cv, ...patch } }); setDirty(true); };

  /** Keep the grouped skills table in sync: removed skills leave their group, new ones go to an "Other" group. */
  const setSkills = (v: string[]) => {
    const old = cv?.cv.skills ?? []; const groups = (cv?.cv.skill_groups as { label: string; items: string[] }[] | undefined) ?? [];
    if (!groups.length) return edit({ skills: v });
    const kept = groups.map((g) => ({ ...g, items: g.items.filter((x) => v.includes(x)) })).filter((g) => g.items.length);
    const added = v.filter((x) => !old.includes(x));
    if (added.length) { const o = kept.find((g) => g.label === "Other"); if (o) o.items.push(...added); else kept.push({ label: "Other", items: added }); }
    edit({ skills: v, skill_groups: kept });
  };
  const upload = (f: File) => run("upload", async () => { const r = await api.upload<Extracted>("/cv/extract", f, { filename: f.name }); setCv(r); setTailored(null); setPdf(null); setDirty(false); });
  const rebuild = () => run("rebuild", async () => { const r = await api.post<{ latex: string }>("/cv/latex", { cv: cv!.cv }); setCv({ ...cv!, latex: r.latex }); setDirty(false); });
  const build = (latex: string, name: string) => run("pdf", async () => {
    if (mode === "public" && !consent) throw new Error("Tick the consent box to use a public LaTeX service.");
    const r = await api.post<PdfOut>("/cv/pdf", { latex, mode, allow_public: consent });
    const url = URL.createObjectURL(new Blob([Uint8Array.from(atob(r.pdf_b64), (c) => c.charCodeAt(0))], { type: "application/pdf" }));
    if (pdf) URL.revokeObjectURL(pdf.url); setPdf({ url, engine: r.engine, bytes: r.bytes }); void name;
  });
  const tailor = () => run("tailor", async () => { const t = await api.post<Tailored>("/cv/tailor", { cv: cv!.cv, latex: cv!.latex, job_id: +jobId }); setTailored(t); });
  const aiTailor = () => run("ai", async () => setAi(await api.post<AiOut>("/cv/ai-tailor", { cv: cv!.cv, job_id: +jobId, consent: aiConsent })));
  const applyAi = () => { if (!ai || !cv) return; setCv({ ...cv, cv: ai.cv, latex: ai.latex }); setPdf(null); setAi(null); setDirty(false); };
  const cover = () => run("letter", async () => setLetter((await api.post<{ text: string }>("/cv/cover-letter", { cv: cv!.cv, job_id: +jobId, tone })).text));
  const download = (name: string, data: BlobPart, type: string) => { const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([data], { type })); a.download = name; a.click(); };
  const step = !cv ? 1 : tailored ? 4 : 2;

  return (<div className="stack">
    <div><h1>CV Studio</h1><div className="muted">Import your CV, fix what the parser got wrong, tailor it to a job, and export a clean LaTeX PDF. Nothing is stored on our server — the draft stays in this browser.</div></div>
    <div className="steps">{["Import", "Review", "Tailor to a job", "Export PDF"].map((s, i) => <div key={s} className={"step" + (step === i + 1 ? " on" : step > i + 1 ? " done" : "")}><b>{step > i + 1 ? "✓" : i + 1}</b>{s}</div>)}</div>
    {err && <div className="notice err">{err}</div>}

    {!cv && <div className={"drop" + (over ? " over" : "")} onClick={() => fileRef.current?.click()} onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); e.dataTransfer.files[0] && upload(e.dataTransfer.files[0]); }}>
      <div style={{ fontSize: 34 }}>📄</div><h2>{busy === "upload" ? "Reading your CV…" : "Drop your CV here or click to browse"}</h2><div className="muted">PDF, DOCX, LaTeX (.tex) or plain text · max 3 MB</div>
      <input ref={fileRef} hidden type="file" accept=".pdf,.docx,.txt,.tex,.md" onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} /></div>}

    {cv && <div className="studio">
      <div className="stack">
        <div className="card stack">
          <div className="row"><h2 style={{ margin: 0 }}>Extracted details</h2><span className="chip plain">{cv.source ?? "text"}</span>
            <button className="btn ghost small right" onClick={() => { setCv(null); setTailored(null); setPdf(null); setLetter(""); }}>Replace CV</button></div>
          <div className="grid two" style={{ gridTemplateColumns: "1fr 1fr" }}>
            <Field label="Name"><input type="text" value={cv.cv.name} onChange={(e) => edit({ name: e.target.value })} /></Field>
            <Field label="Email"><input type="text" value={cv.cv.email} onChange={(e) => edit({ email: e.target.value })} /></Field>
            <Field label="Phone"><input type="text" value={cv.cv.phone} onChange={(e) => edit({ phone: e.target.value })} /></Field>
            <Field label="Location"><input type="text" value={cv.cv.location} onChange={(e) => edit({ location: e.target.value })} /></Field></div>
          <Field label="Summary"><textarea rows={3} style={{ fontFamily: "inherit", fontSize: 14 }} value={cv.cv.summary} onChange={(e) => edit({ summary: e.target.value })} /></Field>
          <Field label="Languages"><Tags items={cv.cv.languages ?? []} onChange={(v) => edit({ languages: v })} placeholder="e.g. Arabic: native — press Enter" /></Field>
          <Field label="Skills"><Tags items={cv.cv.skills ?? []} onChange={(v) => setSkills(v)} placeholder="Add a skill — press Enter" /></Field>
          <Field label="References"><Tags items={cv.cv.references ?? []} onChange={(v) => edit({ references: v, order: [...new Set([...(cv.cv.order ?? []), "references"])] })} placeholder="Name, role, organisation" /></Field>
          <Field label="Certifications"><Tags items={cv.cv.certifications ?? []} onChange={(v) => edit({ certifications: v })} placeholder="Add a certification" /></Field>
          <div className="row"><button className="btn" onClick={rebuild} disabled={!!busy}>{busy === "rebuild" ? "Rebuilding…" : dirty ? "Apply edits → LaTeX" : "Rebuild LaTeX"}</button>
            {dirty && <span className="small muted">You have edits not yet in the LaTeX.</span>}</div>
          <details><summary className="small">LaTeX source ({cv.latex.length.toLocaleString()} chars) — editable</summary><textarea rows={14} value={cv.latex} onChange={(e) => setCv({ ...cv, latex: e.target.value })} /></details>
        </div>

        <div className="card stack"><h2 style={{ margin: 0 }}>Tailor to a job</h2>
          <div className="row"><input type="number" placeholder="Job ID" value={jobId} onChange={(e) => setJobId(e.target.value)} style={{ width: 120 }} />
            <select value={tone} onChange={(e) => setTone(e.target.value)}><option value="professional">Professional</option><option value="warm">Warm</option><option value="concise">Concise</option></select>
            <button className="btn" disabled={!jobId || !!busy} onClick={tailor}>{busy === "tailor" ? "Tailoring…" : "Tailor CV"}</button>
            <button className="btn ghost" disabled={!jobId || !!busy} onClick={cover}>{busy === "letter" ? "Writing…" : "Cover letter"}</button></div>
          <div className="small muted">Open a job and press “Tailor CV & letter” to fill the ID. Tailoring only re-orders what is already in your CV; missing requirements are listed as gaps, never added.</div>
          {tailored && <div className="stack" style={{ gap: 8 }}>
            <div className="row"><strong>Match {tailored.match_score}%</strong><span className="small muted">{tailored.matched.length} of {tailored.keywords.length} keywords</span></div>
            <div>{tailored.matched.map((m) => <span key={m} className="chip ok">{m}</span>)}{tailored.gaps.slice(0, 8).map((m) => <span key={m} className="chip plain" title="Not in your CV">gap: {m}</span>)}</div>
            {tailored.changes?.map((c) => <div key={c} className="small muted">• {c}</div>)}
            <div className="row">{tailored.latex && <button className="btn small" onClick={() => build(tailored.latex!, "tailored")} disabled={!!busy}>Build tailored PDF</button>}
              {tailored.latex && <button className="btn ghost small" onClick={() => download("tailored-cv.tex", tailored.latex!, "text/x-tex")}>.tex</button>}
              <button className="btn ghost small" onClick={() => download("tailored-cv.txt", tailored.text, "text/plain")}>Text</button></div></div>}
        </div>
        <div className="card stack"><div className="row"><h2 style={{ margin: 0 }}>AI tailoring</h2><span className="chip plain">Claude</span></div>
          {!aiOk ? <div className="small muted">Not enabled on this server. Set <code>ANTHROPIC_API_KEY</code> to let Claude rewrite your CV for a job. It only rewords what your CV already says and never adds skills or experience.</div> : <>
            <div className="small muted">Claude rewrites the summary and bullets using the posting's vocabulary, reorders your skills, and lists gaps. You review every change before it is applied.</div>
            <label className="notice row" style={{ alignItems: "flex-start", flexWrap: "nowrap" }}><input type="checkbox" checked={aiConsent} onChange={(e) => setAiConsent(e.target.checked)} style={{ marginTop: 4 }} /><span>Send my CV and this job posting to Anthropic. Your CV contains personal data and leaves this server.</span></label>
            <div className="row"><button className="btn" disabled={!jobId || !aiConsent || !!busy} onClick={aiTailor}>{busy === "ai" ? "Claude is tailoring…" : "Tailor with AI"}</button>{!jobId && <span className="small muted">Enter a job ID above first.</span>}</div></>}
          {ai && <div className="stack" style={{ gap: 10 }}>
            <strong>{ai.changes.length} suggested change{ai.changes.length === 1 ? "" : "s"} for {ai.job.title} at {ai.job.company}</strong>
            {ai.notes && <div className="small muted">{ai.notes}</div>}
            {ai.changes.map((c, i) => <div key={i} className="card" style={{ padding: 12, boxShadow: "none" }}><div className="small muted">{c.section}{c.title ? ` · ${c.title}` : ""}</div>
              <div className="small" style={{ textDecoration: "line-through", opacity: .6 }}>{c.before || "—"}</div><div className="small">{c.after}</div></div>)}
            {ai.gaps.length > 0 && <div><span className="small muted">Requirements your CV does not show (not added): </span>{ai.gaps.map((g) => <span key={g} className="chip plain">{g}</span>)}</div>}
            <div className="row"><button className="btn" onClick={applyAi}>Apply changes</button><button className="btn ghost" onClick={() => setAi(null)}>Discard</button><span className="small muted">After applying, press “Build PDF”.</span></div></div>}
        </div>
        {letter && <div className="card stack"><h2 style={{ margin: 0 }}>Cover letter</h2><textarea rows={14} value={letter} onChange={(e) => setLetter(e.target.value)} style={{ fontFamily: "inherit", fontSize: 14 }} />
          <div className="row"><button className="btn ghost small" onClick={() => navigator.clipboard.writeText(letter)}>Copy</button><button className="btn ghost small" onClick={() => download("cover-letter.txt", letter, "text/plain")}>Download</button></div></div>}
      </div>

      <div className="stack" style={{ position: "sticky", top: 78 }}>
        <div className="card stack"><div className="row"><h2 style={{ margin: 0 }}>PDF export</h2>
          <div className="seg right"><button className={mode === "local" ? "on" : ""} disabled={localOk === false} onClick={() => setMode("local")} title={localOk === false ? "No LaTeX compiler on this server" : ""}>This server</button><button className={mode === "public" ? "on" : ""} onClick={() => setMode("public")}>Public LaTeX service</button></div></div>
          {mode === "public" && <label className="notice row" style={{ alignItems: "flex-start", flexWrap: "nowrap" }}><input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} style={{ marginTop: 4 }} />
            <span>Send this CV to a third-party compiler (latex.ytotech.com, then texlive.net as fallback). Your CV contains personal data and leaves this server. Leave unticked to keep it private.</span></label>}
          <div className="row"><button className="btn" disabled={!!busy || (mode === "public" && !consent)} onClick={() => build(cv.latex, "cv")}>{busy === "pdf" ? "Compiling…" : "Build PDF from LaTeX"}</button>
            {pdf && <a className="btn ghost" href={pdf.url} download="cv.pdf">Download PDF</a>}
            <button className="btn ghost" onClick={() => download("cv.tex", cv.latex, "text/x-tex")}>.tex</button>
            <a className="small" href="https://www.overleaf.com/docs" target="_blank" rel="noreferrer noopener">Open in Overleaf ↗</a></div>
          {pdf && <div className="small muted">Built with {pdf.engine} · {(pdf.bytes / 1024).toFixed(0)} KB</div>}
        </div>
        {pdf ? <iframe className="pdfview" title="PDF preview" src={pdf.url} /> : <div className="card empty">Your PDF preview appears here.</div>}
      </div>
    </div>}
  </div>);
}
