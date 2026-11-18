import { useState } from "react";
import type { SearchParams } from "@/shared/api/types";
import { useSearchMutations } from "./api";

export function SaveSearchButton({ params }: { params: SearchParams }) {
  const { create } = useSearchMutations(); const [msg, setMsg] = useState("");
  async function save() {
    const name = window.prompt("Name this search (you'll get alerts for new matches)", params.q || "My search"); if (!name) return;
    const { page: _p, limit: _l, ...rest } = params; void _p; void _l;
    try { await create.mutateAsync({ name, params: rest, alert_frequency: "daily" }); setMsg("Saved — daily alerts on"); } catch (e) { setMsg((e as Error).message); }
  }
  return <><button type="button" className="btn ghost" onClick={save}>Save & alert</button>{msg && <span className="small muted">{msg}</span>}</>;
}
