import { NavLink, Navigate, Outlet, Route, Routes, useLocation, Link } from "react-router-dom";
import { useTheme } from "@/shared/lib/theme";
import { useAuth } from "@/features/auth/AuthContext";
import { AuthPage } from "@/features/auth/AuthPage";
import { ForgotPage, ResetPage, VerifyPage, VerifyBanner, ActionPage } from "@/features/auth/AccountPages";
import { JobsPage } from "@/features/jobs/JobsPage";
import { CompaniesPage } from "@/features/companies/CompaniesPage";
import { DashboardPage } from "@/features/dashboard/DashboardPage";
import { AlertsPage } from "@/features/alerts/AlertsPage";
import { useNotifications } from "@/features/alerts/api";
import { PipelinePage } from "@/features/pipeline/PipelinePage";
import { CvPage } from "@/features/cv/CvPage";
import { ProfilePage } from "@/features/profile/ProfilePage";
import { AdminPage } from "@/features/admin/AdminPage";

function Layout() {
  const { user, logout } = useAuth(); const n = useNotifications(!!user); const { theme, next } = useTheme();
  const nav = (to: string, text: string, end = false) => <NavLink className="nav" to={to} end={end}>{text}</NavLink>;
  return (<div className="shell"><header className="top"><div className="in">
    <Link to="/" className="brand"><i>NL</i><span>Career Tracker</span></Link>
    <nav className="navs">{nav("/", "Jobs", true)}{nav("/internships", "Internships")}{nav("/companies", "Companies")}{nav("/dashboard", "Market")}{nav("/cv", "CV Studio")}
      {user && <>{nav("/pipeline", "Pipeline")}<NavLink className="nav" to="/alerts">Alerts{!!n.data?.unread && <span className="chip warn" style={{ margin: 0 }}>{n.data.unread}</span>}</NavLink>{user.role === "admin" && nav("/admin", "Admin")}</>}</nav>
    <div className="user"><button className="themebtn" onClick={next} title={`Theme: ${theme} (click to change)`} aria-label="Change theme">{theme === "light" ? "☀️" : theme === "dark" ? "🌙" : "🖥️"}</button>{user ? <><Link to="/profile" className="row" style={{ gap: 8, color: "inherit" }}><span className="avatar">{(user.name || user.email)[0].toUpperCase()}</span><span className="small email">{user.email}</span></Link><button className="btn ghost small" onClick={logout}>Sign out</button></>
      : <><Link className="btn ghost small" to="/login">Sign in</Link><Link className="btn small" to="/register">Sign up</Link></>}</div></div></header>
    <main className="main"><VerifyBanner /><Outlet /></main></div>);
}
function Protected({ admin = false }: { admin?: boolean }) {
  const { user, ready } = useAuth(); const loc = useLocation();
  if (!ready) return <p className="muted">Loading…</p>;
  if (!user) return <Navigate to="/login" state={{ from: loc.pathname + loc.search }} replace />;
  if (admin && user.role !== "admin") return <Navigate to="/" replace />;
  return <Outlet />;
}
export default function App() {
  return (<Routes>
    <Route path="/login" element={<AuthPage mode="login" />} /><Route path="/register" element={<AuthPage mode="register" />} />
    <Route path="/forgot" element={<ForgotPage />} /><Route path="/reset" element={<ResetPage />} /><Route path="/verify" element={<VerifyPage />} /><Route path="/action" element={<ActionPage />} />
    <Route element={<Layout />}>
      <Route index element={<JobsPage />} /><Route path="internships" element={<JobsPage internships />} /><Route path="companies" element={<CompaniesPage />} />
      <Route path="dashboard" element={<DashboardPage />} /><Route path="cv" element={<CvPage />} />
      <Route element={<Protected />}><Route path="pipeline" element={<PipelinePage />} /><Route path="alerts" element={<AlertsPage />} /><Route path="profile" element={<ProfilePage />} /></Route>
      <Route element={<Protected admin />}><Route path="admin" element={<AdminPage />} /></Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Route></Routes>);
}
