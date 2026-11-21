import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

/* ---------- toasts: every action says what happened, in a place you can't miss ---------- */
type Toast = { id: number; text: string; tone: "ok" | "bad" | "info" };
const Ctx = createContext<(text: string, tone?: Toast["tone"]) => void>(() => {});
export const useNotify = () => useContext(Ctx);

export function NotifyProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const push = useCallback((text: string, tone: Toast["tone"] = "info") => {
    const id = Date.now() + Math.random();
    setItems((x) => [...x.slice(-3), { id, text, tone }]);
    setTimeout(() => setItems((x) => x.filter((t) => t.id !== id)), tone === "bad" ? 9000 : 6000);
  }, []);
  return <Ctx.Provider value={push}>{children}<div className="toast-wrap" role="status" aria-live="polite">{items.map((t) => <div key={t.id} className={`toast ${t.tone === "info" ? "" : t.tone}`}>{t.text}</div>)}</div></Ctx.Provider>;
}

/* ---------- modal ---------- */
export function Modal({ title, onClose, children, wide }: { title: string; onClose(): void; children: ReactNode; wide?: boolean }) {
  useEffect(() => { const k = (e: KeyboardEvent) => e.key === "Escape" && onClose(); window.addEventListener("keydown", k); return () => window.removeEventListener("keydown", k); }, [onClose]);
  return <div className="modal-back" onMouseDown={(e) => e.target === e.currentTarget && onClose()}><div className={`modal${wide ? " wide" : ""}`} role="dialog" aria-modal="true" aria-label={title}><h3>{title}</h3>{children}</div></div>;
}

export function Spinner() { return <span className="spin" aria-label="working" />; }

export const num = (n?: number | null) => (n ?? 0).toLocaleString();
export const ago = (iso?: string | null) => {
  if (!iso) return "never";
  const s = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  return s < 90 ? "just now" : s < 3600 ? `${Math.round(s / 60)} min ago` : s < 172800 ? `${Math.round(s / 3600)} h ago` : `${Math.round(s / 86400)} d ago`;
};
export const when = (iso?: string | null) => (iso ? new Date(iso).toLocaleString() : "—");

/** One button that shows a spinner while its async action runs, so a click always visibly does something. */
export function ActionButton({ run, children, className = "btn small", disabled, title }: { run(): Promise<unknown>; children: ReactNode; className?: string; disabled?: boolean; title?: string }) {
  const [busy, setBusy] = useState(false);
  return <button className={className} title={title} disabled={disabled || busy} onClick={async () => { setBusy(true); try { await run(); } finally { setBusy(false); } }}>{busy ? <Spinner /> : null} {children}</button>;
}

export function Pager({ page, limit, total, onPage }: { page: number; limit: number; total: number; onPage(p: number): void }) {
  const pages = Math.max(1, Math.ceil(total / limit));
  return <div className="row small muted" style={{ justifyContent: "space-between" }}>
    <span>{total ? `${num((page - 1) * limit + 1)}–${num(Math.min(page * limit, total))} of ${num(total)}` : "0 results"}</span>
    <span className="row" style={{ gap: 6 }}><button className="iconbtn" disabled={page <= 1} onClick={() => onPage(page - 1)}>‹ Prev</button><span>page {page} / {pages}</span><button className="iconbtn" disabled={page >= pages} onClick={() => onPage(page + 1)}>Next ›</button></span>
  </div>;
}

/** Debounced value, so typing in a search box doesn't fire a request per keystroke. */
export function useDebounced<T>(v: T, ms = 300): T {
  const [d, setD] = useState(v);
  useEffect(() => { const t = setTimeout(() => setD(v), ms); return () => clearTimeout(t); }, [v, ms]);
  return d;
}

/** Download a file from an authenticated endpoint (a plain link can't send the login header). */
export async function download(path: string, filename: string, token?: string) {
  const { request } = await import("@/shared/api/client");
  const text = await request<string>("GET", path);
  const url = URL.createObjectURL(new Blob([typeof text === "string" ? text : JSON.stringify(text)], { type: "text/csv" }));
  const a = document.createElement("a"); a.href = url; a.download = filename; a.click(); URL.revokeObjectURL(url); void token;
}
