import { Navigate, Route, Routes } from "react-router-dom";
import type { ReactNode } from "react";
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
function AppearanceRoute() {
  return (
    <APlatformLayout title="Appearance">
      <AppearanceSettingsPage />
    </APlatformLayout>
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
    <APlatformLayout title="Cost controls">
      <CostControls />
    </APlatformLayout>
  );
}
function ProviderRoute() {
  return (
    <APlatformLayout title="Providers and models">
      <ProviderSettingsPage />
    </APlatformLayout>
  );
}
function SettingsRoute() {
  return (
    <APlatformLayout title="Settings">
      <OperationalSettingsPage />
    </APlatformLayout>
  );
}
function SystemMapRoute() {
  return (
    <APlatformLayout title="System map">
      <ASystemMap />
    </APlatformLayout>
  );
}
function ProcessesRoute() {
  return (
    <APlatformLayout title="Processes">
      <ProcessesPage />
    </APlatformLayout>
  );
}
function ChatRoute() {
  return (
    <APlatformLayout title="Chat">
      <ChatPage />
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
            : path === "/failed-jobs" ? <ContentRoute title={title}><FailedJobsPage /></ContentRoute>
            : path === "/chat" || path === "/conversations" ? (
              <ChatRoute />
            ) : path === "/processes" ? (
              <ProcessesRoute />
            ) : path === "/settings/appearance" ? (
              <AppearanceRoute />
            ) : path === "/settings/providers" ? (
              <ProviderRoute />
            ) : path === "/settings" ? (
              <SettingsRoute />
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
