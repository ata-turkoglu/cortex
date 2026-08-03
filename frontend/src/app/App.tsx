import { Navigate, Route, Routes } from "react-router-dom";
import { APlatformLayout } from "../layout/APlatformLayout";
import { AppearanceSettingsPage } from "../pages/AppearanceSettingsPage";
import { CostControls } from "../pages/CostControls";
import { PagePlaceholder } from "../pages/PagePlaceholder";
import { SetupWizard } from "../pages/SetupWizard";
import { ProviderSettingsPage } from "../pages/ProviderSettingsPage";
import { ASystemMap } from "../flow/ASystemMap";
import { ProcessesPage } from "../pages/ProcessesPage";
import { ChatPage } from "../pages/ChatPage";
import { OperationalSettingsPage } from "../pages/OperationalSettingsPage";
const routes: Record<string, [string, string]> = {
  "/": ["Dashboard", "Workspace summary and recent activity."],
  "/workspaces": ["Workspaces", "Manage isolated knowledge applications."],
  "/workspace/:workspaceId": ["Workspace", "Workspace overview."],
  "/documents": ["Documents", "Server-side paginated document list."],
  "/documents/:documentId": [
    "Document details",
    "Versions and source details.",
  ],
  "/upload": ["Upload", "Secure document intake."],
  "/chat": ["Chat", "Grounded querying experience."],
  "/conversations": ["Conversations", "Saved conversations."],
  "/processes": ["Processes", "Background workflows and diagnostics."],
  "/failed-jobs": ["Failed jobs", "Sanitized technical details."],
  "/graph": ["Graph explorer", "Knowledge graph visualization."],
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
  "/health": ["Health", "Service statuses."],
};
function RoutedPage({ title, detail }: { title: string; detail: string }) {
  return (
    <APlatformLayout title={title}>
      <PagePlaceholder title={title} detail={detail} />
    </APlatformLayout>
  );
}
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
export function App() {
  return (
    <Routes>
      {Object.entries(routes).map(([path, [title, detail]]) => (
        <Route
          key={path}
          path={path}
          element={
            path === "/chat" ? (
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
            ) : (
              <RoutedPage title={title} detail={detail} />
            )
          }
        />
      ))}
      <Route path="/setup" element={<SetupRoute />} />
      <Route path="/settings/costs" element={<CostRoute />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
