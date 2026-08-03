import { NavLink, useLocation } from "react-router-dom";
import { useEffect, useState, type ReactNode } from "react";
import { AIcon, type IconName } from "../icons/AIcon";
import { AButton, AProgress, ATooltip } from "../ui/primitives";
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
  { to: "/settings", label: "Ayarlar", icon: "settings" },
];
export function APlatformLayout({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  const [expanded, setExpanded] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const jobs = useJobsStore((state) => state.jobs);
  const setJobs = useJobsStore((state) => state.setJobs);
  const location = useLocation();
  useEffect(() => {
    const refresh = async () => {
      try {
        const runs = await apiClient.listWorkflows();
        setJobs(
          runs
            .filter((run) =>
              ["queued", "running", "cancelling"].includes(run.state),
            )
            .map((run) => ({
              id: run.id,
              label: run.job_type,
              progress: Math.round(
                (run.steps.filter((step) => step.state === "completed").length /
                  Math.max(run.steps.length, 1)) *
                  100,
              ),
            })),
        );
      } catch {
        /* Health UI remains usable while backend is unavailable. */
      }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 5000);
    return () => window.clearInterval(timer);
  }, [setJobs]);
  return (
    <div className="cortex-shell" data-expanded={expanded}>
      <aside
        className="cortex-sidebar"
        data-collapsed={!expanded}
        data-mobile-open={mobileOpen}
      >
        <strong className="flex items-center gap-2">
          <AIcon name="database" size={22} />
          <span className="nav-label">Cortex</span>
        </strong>
        <nav className="cortex-nav">
          {navigation.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              aria-current={location.pathname === item.to ? "page" : undefined}
              title={!expanded ? item.label : undefined}
              onClick={() => setMobileOpen(false)}
            >
              <AIcon name={item.icon} size={20} />
              <span className="nav-label">{item.label}</span>
            </NavLink>
          ))}
        </nav>
      </aside>
      <main>
        <div className="activity-bar" data-active={jobs.length > 0} />
        <header className="cortex-header">
          <AButton
            aria-label="Menüyü aç veya kapat"
            icon="pi pi-bars"
            text
            onClick={() => {
              setExpanded((value) => !value);
              setMobileOpen((value) => !value);
            }}
          />
          <div className="min-w-0 flex-1">
            <div className="font-semibold">{title}</div>
            <div className="text-xs opacity-65">{location.pathname}</div>
          </div>
          <button
            className="rounded px-2 py-1 text-sm"
            type="button"
            onClick={() => window.location.assign("/processes")}
            aria-label="Aktif işler"
          >
            {jobs.length ? `${jobs.length} aktif iş` : "İş yok"}
          </button>
          <span
            title="Sistem sağlıklı"
            className="flex items-center gap-1 text-sm text-green-600"
          >
            <AIcon name="health" size={17} /> Sağlıklı
          </span>
          {jobs.length > 0 && (
            <AProgress
              value={jobs[0].progress ?? undefined}
              showValue={false}
              style={{ width: 96, height: 7 }}
            />
          )}
        </header>
        <div className="cortex-content">{children}</div>
      </main>
      <ATooltip target="[title]" />
    </div>
  );
}
