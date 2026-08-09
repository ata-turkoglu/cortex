import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import type { ReactNode } from "react";
import { ATabs } from "../components/ui";
import { APlatformLayout } from "../layout/APlatformLayout";
import { AppearanceSettingsPage } from "../pages/AppearanceSettingsPage";
import { CostControls } from "../pages/CostControls";
import { SetupWizard } from "../pages/SetupWizard";
import { ProviderSettingsPage } from "../pages/ProviderSettingsPage";
import { ASystemMap } from "../flow/ASystemMap";
import { ProcessesPage } from "../pages/ProcessesPage";
import { ChatPage } from "../pages/ChatPage";
import { OperationalSettingsPage } from "../pages/OperationalSettingsPage";
import { FailedJobsPage } from "../pages/FailedJobsPage";
import { DashboardPage, DocumentDetailPage, DocumentsPage, GraphPage, HealthPage, UploadPage, WorkspaceOverviewPage, WorkspacesPage } from "../pages/WorkspacePages";
const routes: Record<string, [string, string]> = {
  "/": ["Dashboard", ""],
  "/workspaces": ["Çalışma alanları", ""],
  "/workspace/:workspaceId": ["Çalışma alanı", ""],
  "/documents": ["Belgeler", ""],
  "/documents/:documentId": ["Belge", ""],
  "/upload": ["Yükle", ""],
  "/chat": ["Sohbet", ""],
  "/conversations": ["Sohbetler", ""],
  "/processes": ["Processes", "Background workflows and diagnostics."],
  "/failed-jobs": ["Failed jobs", "Sanitized technical details."],
  "/graph": ["Graf", ""],
  "/system-map": ["System map", "Component and data-flow map."],
  "/settings": ["Settings", "Global configuration."],
  "/settings/providers": [
    "Providers and models",
    "Provider configuration state without secrets.",
  ],
  "/settings/appearance": [
    "Appearance",
    "Theme and accessibility preferences.",
  ],
  "/health": ["Sistem sağlığı", ""],
};
function SettingsRoute({ title, children }: { title: string; children: ReactNode }) {
  const { pathname } = useLocation();
  const tabs = [
    ["/settings", "Genel"],
    ["/settings/providers", "Sağlayıcılar"],
    ["/settings/appearance", "Görünüm"],
    ["/settings/costs", "Maliyet"],
  ] as const;
  return (
    <APlatformLayout title={title}>
      <div className="page-stack">
        <ATabs aria-label="Ayar bölümleri">
          {tabs.map(([to, label]) => (
            <Link key={to} to={to} role="tab" aria-selected={pathname === to} className={pathname === to ? "is-active" : undefined}>
              {label}
            </Link>
          ))}
        </ATabs>
        {children}
      </div>
    </APlatformLayout>
  );
}
function AppearanceRoute() {
  return (
    <SettingsRoute title="Appearance">
      <AppearanceSettingsPage />
    </SettingsRoute>
  );
}
function SetupRoute() {
  return (
    <APlatformLayout title="Setup">
      <SetupWizard />
    </APlatformLayout>
  );
}
function CostRoute() {
  return (
    <SettingsRoute title="Cost controls">
      <CostControls />
    </SettingsRoute>
  );
}
function ProviderRoute() {
  return (
    <SettingsRoute title="Providers and models">
      <ProviderSettingsPage />
    </SettingsRoute>
  );
}
function OperationalSettingsRoute() {
  return (
    <SettingsRoute title="Settings">
      <OperationalSettingsPage />
    </SettingsRoute>
  );
}
function SystemMapRoute() {
  return (
    <APlatformLayout title="System map">
      <ASystemMap />
    </APlatformLayout>
  );
}
function WorkflowRoute({ title, children }: { title: string; children: ReactNode }) {
  const { pathname } = useLocation();
  return (
    <APlatformLayout title={title}>
      <div className="page-stack">
        <ATabs aria-label="Süreç bölümleri">
          <Link to="/processes" role="tab" aria-selected={pathname === "/processes"} className={pathname === "/processes" ? "is-active" : undefined}>Süreçler</Link>
          <Link to="/failed-jobs" role="tab" aria-selected={pathname === "/failed-jobs"} className={pathname === "/failed-jobs" ? "is-active" : undefined}>Başarısız işler</Link>
        </ATabs>
        {children}
      </div>
    </APlatformLayout>
  );
}
function ProcessesRoute() {
  return (
    <WorkflowRoute title="Processes">
      <ProcessesPage />
    </WorkflowRoute>
  );
}
function FailedJobsRoute() {
  return (
    <WorkflowRoute title="Failed jobs">
      <FailedJobsPage />
    </WorkflowRoute>
  );
}
function ChatRoute({ title }: { title: string }) {
  const { pathname } = useLocation();
  return (
    <APlatformLayout title={title}>
      <div className="page-stack page-stack--chat">
        <ATabs aria-label="Sohbet bölümleri">
          <Link to="/chat" role="tab" aria-selected={pathname === "/chat"} className={pathname === "/chat" ? "is-active" : undefined}>Sohbet</Link>
          <Link to="/conversations" role="tab" aria-selected={pathname === "/conversations"} className={pathname === "/conversations" ? "is-active" : undefined}>Sohbet geçmişi</Link>
        </ATabs>
        <ChatPage />
      </div>
    </APlatformLayout>
  );
}
function ContentRoute({ title, children }: { title: string; children: ReactNode }) {
  return <APlatformLayout title={title}>{children}</APlatformLayout>;
}
export function App() {
  return (
    <Routes>
      {Object.entries(routes).map(([path, [title]]) => (
        <Route
          key={path}
          path={path}
          element={
            path === "/" ? <ContentRoute title={title}><DashboardPage /></ContentRoute>
            : path === "/workspaces" ? <ContentRoute title={title}><WorkspacesPage /></ContentRoute>
            : path === "/workspace/:workspaceId" ? <ContentRoute title={title}><WorkspaceOverviewPage /></ContentRoute>
            : path === "/documents" ? <ContentRoute title={title}><DocumentsPage /></ContentRoute>
            : path === "/documents/:documentId" ? <ContentRoute title={title}><DocumentDetailPage /></ContentRoute>
            : path === "/upload" ? <ContentRoute title={title}><UploadPage /></ContentRoute>
            : path === "/graph" ? <ContentRoute title={title}><GraphPage /></ContentRoute>
            : path === "/health" ? <ContentRoute title={title}><HealthPage /></ContentRoute>
            : path === "/failed-jobs" ? <FailedJobsRoute />
            : path === "/chat" ? <ChatRoute title="Chat" />
            : path === "/conversations" ? <Navigate to="/chat" replace />
            : path === "/processes" ? (
              <ProcessesRoute />
            ) : path === "/settings/appearance" ? (
              <AppearanceRoute />
            ) : path === "/settings/providers" ? (
              <ProviderRoute />
            ) : path === "/settings" ? (
              <OperationalSettingsRoute />
            ) : path === "/system-map" ? (
              <SystemMapRoute />
            ) : <Navigate to="/" replace />
          }
        />
      ))}
      <Route path="/setup" element={<SetupRoute />} />
      <Route path="/settings/costs" element={<CostRoute />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
