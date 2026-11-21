export interface Company { id: number; name: string; logo?: string | null; website?: string | null; sponsor_status: string; sponsor_match?: string | null; careers_url?: string | null; city?: string | null; description?: string | null; ats?: string | null; last_scan?: string | null; open_jobs?: number }
export interface Job {
  id: number; title: string; company: Company; location?: string | null; city?: string | null; url: string; job_type: string; category: string; domain?: string | null; language: string; remote: boolean;
  salary?: { min?: number; max?: number; period?: string; verdict?: string } | null; posted_at?: string | null; first_seen?: string | null; status: string; skills: string[];
  snippet?: string | null; relevance?: number | null; matched: string[]; fit?: number | null; fit_reason?: string | null; stage?: string | null; description?: string | null; notes?: string | null;
}
export interface Facet { value: string; count: number }
export interface SearchResult { items: Job[]; total: number; page: number; limit: number; facets: Record<string, Facet[]>; query: Record<string, unknown>; sort: string }
export interface User { id: string; email: string; name: string; role: "user" | "admin"; profile: Profile; email_verified?: boolean }
export interface Profile { skills?: string[]; titles?: string[]; cities?: string[]; job_types?: string[]; english_only?: boolean; salary_category?: string }
export interface TokenOut { access_token: string; refresh_token: string; expires_in: number; user: User }
export interface SearchParams {
  q?: string; mode?: "hybrid" | "keyword" | "semantic"; sort?: string; category?: string; kind?: string; job_type?: string[]; domain?: string[]; language?: string[]; city?: string[];
  remote?: boolean; sponsor?: boolean; skills?: string[]; skills_mode?: "any" | "all"; min_salary?: number; days?: number; page?: number; limit?: number; company_id?: number;
}
export interface SavedSearch { id: number; name: string; params: SearchParams; alert_frequency: string; channel_email: boolean; last_run_at?: string | null }
export interface Notification { id: number; kind: string; title: string; body: string; data: { job_ids?: number[]; saved_search_id?: number }; read: boolean; created_at: string }
