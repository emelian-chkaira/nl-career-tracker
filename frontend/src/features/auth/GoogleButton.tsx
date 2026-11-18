import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/shared/api/client";

declare global { interface Window { google?: { accounts: { id: { initialize(o: object): void; renderButton(el: HTMLElement, o: object): void } } } } }
const SRC = "https://accounts.google.com/gsi/client";

/** "Continue with Google" (Google Identity Services). Renders nothing until the server has a Google client ID configured. */
export function GoogleButton({ onCredential, onError }: { onCredential: (credential: string) => void; onError?: (m: string) => void }) {
  const cfg = useQuery({ queryKey: ["auth-config"], queryFn: () => api.get<{ google_client_id: string | null }>("/auth/config"), staleTime: Infinity });
  const box = useRef<HTMLDivElement>(null); const [failed, setFailed] = useState(false);
  const id = cfg.data?.google_client_id;
  useEffect(() => {
    if (!id) return;
    const start = () => {
      if (!window.google || !box.current) return;
      window.google.accounts.id.initialize({ client_id: id, callback: (r: { credential: string }) => onCredential(r.credential) });
      window.google.accounts.id.renderButton(box.current, { theme: "outline", size: "large", width: 360, text: "continue_with", shape: "pill" });
    };
    if (window.google) { start(); return; }
    let s = document.querySelector<HTMLScriptElement>(`script[src="${SRC}"]`);
    if (!s) { s = document.createElement("script"); s.src = SRC; s.async = true; document.head.appendChild(s); }
    s.addEventListener("load", start); s.addEventListener("error", () => { setFailed(true); onError?.("Could not load Google sign-in"); });
    return () => s?.removeEventListener("load", start);
  }, [id, onCredential, onError]);
  if (!id || failed) return null;
  return (<><div ref={box} style={{ display: "flex", justifyContent: "center", minHeight: 44 }} />
    <div className="small muted" style={{ textAlign: "center" }}>or use your email</div></>);
}
