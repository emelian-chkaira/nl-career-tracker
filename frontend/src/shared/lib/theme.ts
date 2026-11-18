import { useEffect, useState } from "react";

export type Theme = "system" | "light" | "dark";
const KEY = "theme";
const read = (): Theme => { try { const v = localStorage.getItem(KEY); return v === "light" || v === "dark" ? v : "system"; } catch { return "system"; } };
const apply = (t: Theme) => { const r = document.documentElement; if (t === "system") r.removeAttribute("data-theme"); else r.setAttribute("data-theme", t); };
apply(read());                                   // before first paint, so there is no flash

/** system -> light -> dark -> system. Choice is remembered in this browser only. */
export function useTheme() {
  const [theme, setTheme] = useState<Theme>(read);
  useEffect(() => { apply(theme); try { theme === "system" ? localStorage.removeItem(KEY) : localStorage.setItem(KEY, theme); } catch { /* private mode */ } }, [theme]);
  const next = () => setTheme((t) => (t === "system" ? "light" : t === "light" ? "dark" : "system"));
  return { theme, next };
}
