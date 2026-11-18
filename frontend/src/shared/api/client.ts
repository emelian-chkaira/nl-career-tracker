/** Single HTTP client. Access token lives in memory only; the refresh token is an httpOnly cookie. */
export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

let accessToken: string | null = null;
let refreshing: Promise<string | null> | null = null;
let onAuthLost: () => void = () => {};
export const setAccessToken = (t: string | null) => { accessToken = t; };
export const setAuthLostHandler = (fn: () => void) => { onAuthLost = fn; };

const BASE = "/api/v1";

async function refresh(): Promise<string | null> {
  refreshing ??= fetch(`${BASE}/auth/refresh`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: "{}" })
    .then(async (r) => (r.ok ? ((await r.json()) as { access_token: string }).access_token : null))
    .catch(() => null)
    .finally(() => { refreshing = null; });
  return refreshing;
}

function detail(body: unknown, fallback: string): string {
  const d = (body as { detail?: unknown })?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x: { msg?: string }) => x.msg).filter(Boolean).join("; ") || fallback;
  if (d && typeof d === "object" && typeof (d as { error?: unknown }).error === "string") return (d as { error: string }).error;
  return fallback;
}

export async function request<T = unknown>(method: string, path: string, opts: { body?: unknown; raw?: BodyInit; query?: Record<string, unknown>; retry?: boolean } = {}): Promise<T> {
  const url = new URL(BASE + path, window.location.origin);
  for (const [k, v] of Object.entries(opts.query ?? {})) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => url.searchParams.append(k, String(x)));
    else url.searchParams.set(k, String(v));
  }
  const headers: Record<string, string> = {};
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  const res = await fetch(url, { method, headers, credentials: "include", body: opts.raw ?? (opts.body !== undefined ? JSON.stringify(opts.body) : undefined) });
  if (res.status === 401 && opts.retry !== false && !path.startsWith("/auth/")) {
    const t = await refresh();
    if (t) { accessToken = t; return request<T>(method, path, { ...opts, retry: false }); }
    accessToken = null; onAuthLost();
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let data: unknown = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!res.ok) throw new ApiError(res.status, detail(data, res.statusText || "Request failed"));
  return data as T;
}

export const api = {
  get: <T,>(p: string, query?: Record<string, unknown>) => request<T>("GET", p, { query }),
  post: <T,>(p: string, body?: unknown, query?: Record<string, unknown>) => request<T>("POST", p, { body: body ?? {}, query }),
  put: <T,>(p: string, body?: unknown) => request<T>("PUT", p, { body: body ?? {} }),
  patch: <T,>(p: string, body?: unknown) => request<T>("PATCH", p, { body: body ?? {} }),
  del: <T,>(p: string) => request<T>("DELETE", p),
  upload: <T,>(p: string, file: File, query?: Record<string, unknown>) => request<T>("POST", p, { raw: file, query }),
};
export const silentRefresh = refresh;
