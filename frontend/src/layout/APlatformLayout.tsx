import { NavLink, useLocation } from "react-router-dom";
import { useEffect, useState, type ReactNode } from "react";
import { AIcon, type IconName } from "../icons/AIcon";
import { AButton, AProgress, ATooltip } from "../components/ui";
import { useJobsStore } from "../app/jobs";
import { apiClient } from "../api/client";

type NavItem = { to: string; label: string; icon: IconName };
const navigation: NavItem[] = [
  { to: "/", label: "Dashboard", icon: "dashboard" },
  { to: "/workspaces", label: "Çalışma Alanları", icon: "workspaces" },
  { to: "/documents", label: "Belgeler", icon: "documents" },
  { to: "/upload", label: "Yükle", icon: "upload" },
  { to: "/chat", label: "Sohbet", icon: "chat" },
  { to: "/processes", label: "Süreçler", icon: "jobs" },
  { to: "/graph", label: "Graf", icon: "graph" },
  { to: "/system-map", label: "Sistem Haritası", icon: "system" },
];
const bottomNavigation: NavItem[] = [{ to: "/settings", label: "Ayarlar", icon: "settings" }];

export function APlatformLayout({ title, children }: { title: string; children: ReactNode }) {
  const [expanded, setExpanded] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const jobs = useJobsStore((state) => state.jobs);
  const setJobs = useJobsStore((state) => state.setJobs);
  const location = useLocation();

  useEffect(() => {
    const refresh = async () => {
      try {
        const runs = await apiClient.listWorkflows();
        setJobs(runs.filter((run) => ["queued", "running", "cancelling"].includes(run.state)).map((run) => ({
          id: run.id,
          label: run.job_type,
          progress: Math.round((run.steps.filter((step) => step.state === "completed").length / Math.max(run.steps.length, 1)) * 100),
        })));
      } catch { /* Health UI remains usable while backend is unavailable. */ }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 5000);
    return () => window.clearInterval(timer);
  }, [setJobs]);

  const renderNavigation = (items: NavItem[]) => items.map((item) => (
    <NavLink key={item.to} to={item.to} className={location.pathname === item.to ? "active" : undefined}
      aria-current={location.pathname === item.to ? "page" : undefined} title={!expanded ? item.label : undefined}
      onClick={() => setMobileOpen(false)}>
      <AIcon name={item.icon} size={18} />
      {!expanded ? null : <span>{item.label}</span>}
    </NavLink>
  ));

  return (
    <main className="platform-shell">
      <div className="activity-bar" data-active={jobs.length > 0} />
      <header className="platform-header">
        <AButton
          icon={expanded ? "sidebarCollapse" : "sidebarExpand"}
          text
          className="sidebar__toggle"
          onClick={() => { setExpanded((value) => !value); setMobileOpen((value) => !value); }}
          aria-label={expanded ? "Kenar çubuğunu kapat" : "Kenar çubuğunu aç"}
          aria-expanded={expanded}
        />
        <strong className="platform-header__brand">Cortex</strong>
        <div className="platform-header__page"><strong>{title}</strong><small>{location.pathname}</small></div>
        <AButton className="cortex-active-jobs" text onClick={() => window.location.assign("/processes")} aria-label="Aktif işler" label={jobs.length ? `${jobs.length} aktif iş` : "İş yok"} />
        <span title="Sistem sağlıklı" className="flex items-center gap-1 text-sm text-green-600"><AIcon name="health" size={17} /> Sağlıklı</span>
        {jobs.length > 0 && <AProgress value={jobs[0].progress ?? undefined} showValue={false} style={{ width: 96, height: 7 }} />}
      </header>
      <div className={`app-shell${expanded ? "" : " is-sidebar-collapsed"}${mobileOpen ? " is-sidebar-mobile-open" : ""}`}>
        <aside className="sidebar">
          <nav aria-label="Ana menü">{renderNavigation(navigation)}</nav>
          <nav className="sidebar__bottom-nav" aria-label="Platform ayarları">{renderNavigation(bottomNavigation)}</nav>
        </aside>
        <section className="content">{children}</section>
      </div>
      <ATooltip target="[title]" />
    </main>
  );
}
