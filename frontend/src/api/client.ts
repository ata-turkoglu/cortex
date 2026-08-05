/** Boundary for OpenAPI-generated code. Feature code imports from this module only. */
import type { components } from "./generated/schema";
export type WorkflowStep = {
  id: string;
  step_name: string;
  state: string;
  retry_count: number;
  checkpoint_json: string | null;
};
export type WorkflowRun = {
  id: string;
  workspace_id: string;
  definition_id: string;
  job_type: string;
  state: string;
  recovery_state: string | null;
  created_at: string;
  updated_at: string;
  finished_at: string | null;
  steps: WorkflowStep[];
};
export type WorkflowEvent = {
  id: string;
  event_type: string;
  payload_json: string | null;
  created_at: string;
};
export type Conversation = components["schemas"]["ConversationRead"];
export type ChatMessage = components["schemas"]["MessageRead"];
export type QueryDebug = components["schemas"]["QueryDebug"];
export type Workspace = components["schemas"]["WorkspaceRead"];
export type CatalogDocument = components["schemas"]["DocumentRead"];
export type WorkspaceOverview = components["schemas"]["WorkspaceOverview"];
export type DashboardOverview = components["schemas"]["DashboardOverview"];
export type DocumentDetail = components["schemas"]["DocumentDetail"];
const base = "/api/v1";
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${base}${path}`, init);
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { message?: string } | null;
    throw new Error(body?.message ?? "İstek tamamlanamadı.");
  }
  return response.json() as Promise<T>;
}
export const apiClient = {
  listWorkspaces: () => request<Workspace[]>("/workspaces"),
  createWorkspace: (name: string, slug: string, description?: string) => request<Workspace>("/workspaces", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, slug, description: description || null }) }),
  deleteWorkspace: (workspaceId: string) => request<void>(`/workspaces/${workspaceId}`, { method: "DELETE" }),
  overview: () => request<DashboardOverview>("/overview"),
  workspaceOverview: (workspaceId: string) => request<WorkspaceOverview>(`/workspaces/${workspaceId}/overview`),
  listDocuments: (workspaceId: string) => request<CatalogDocument[]>(`/workspaces/${workspaceId}/documents`),
  documentDetails: (workspaceId: string, documentId: string) => request<DocumentDetail>(`/workspaces/${workspaceId}/documents/${documentId}`),
  upload: async (workspaceId: string, files: File[]) => {
    const data = new FormData(); files.forEach((file) => data.append("files", file));
    return request<{ uploads: { document_id: string; workflow_run_id: string; filename: string; chunk_count: number }[] }>(`/workspaces/${workspaceId}/uploads`, { method: "POST", body: data });
  },
  deleteDocument: (workspaceId: string, documentId: string) => request<{ workflow_run_id: string }>(`/workspaces/${workspaceId}/documents/${documentId}`, { method: "DELETE" }),
  getHealth: async () => request<{ status: string; services: Record<string, string> }>("/health"),
  getSettings: () => request<{ settings: Record<string, unknown>; global_only: boolean }>("/settings"),
  updateSettings: (settings: Record<string, unknown>) => request<{ settings: Record<string, unknown>; reindex_required: boolean }>("/settings", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(settings) }),
  providerStatus: () => request<{ providers: { provider: string; configured: boolean }[] }>("/settings/providers"),
  validateProvider: (provider: "openai" | "anthropic" | "ollama", apiKey?: string) =>
    request<{ provider: string; status: string }>(`/settings/providers/${provider}/validate`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(apiKey ? { api_key: apiKey } : {}) }),
  embeddingHealth: () => request<{ provider: string; model: string; dimension: number }>("/settings/embedding/health", { method: "POST" }),
  completeSetup: (dataPath?: string) => request<{ completed: boolean }>("/settings/setup/complete", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ data_path: dataPath }) }),
  resetSettings: () => request<{ settings: Record<string, unknown>; reindex_required: boolean }>("/settings/reset-defaults", { method: "POST" }),
  diagnostics: () => request<{ windows: { data_path: string; ollama_base_url: string }; workflows: Record<string, number>; reconciliation: { state: string; message: string } }>("/settings/diagnostics"),
  embeddingStatus: () => request<{ provider: string; model: string; installed: boolean; dimension: number | null; model_digest: string | null; last_benchmark: string | null; requires_full_reindex: boolean }>("/settings/embedding/status"),
  graphragEstimate: () => request<{ update_mode: string; pending_document_threshold: number; confirmation_threshold_usd: number; requires_confirmation: boolean }>("/settings/graphrag/estimate"),
  listWorkflows: async () => request<WorkflowRun[]>("/workflows"),
  cancelWorkflow: async (id: string) =>
    request<WorkflowRun>(`/workflows/${id}/cancel`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    }),
  retryWorkflow: async (id: string) =>
    request<WorkflowRun>(`/workflows/${id}/retry`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    }),
  workflowEventHistory: async (id: string) =>
    request<WorkflowEvent[]>(`/workflows/${id}/events/history`),
  workflowEvents: (id: string, after?: string) =>
    new EventSource(
      `${base}/workflows/${id}/events${after ? `?after=${encodeURIComponent(after)}` : ""}`,
    ),
  listConversations: (workspaceId: string) =>
    request<Conversation[]>(`/workspaces/${workspaceId}/conversations`),
  createConversation: (workspaceId: string, title = "New conversation") =>
    request<Conversation>(`/workspaces/${workspaceId}/conversations`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    }),
  listMessages: (workspaceId: string, conversationId: string, limit = 50, offset = 0) =>
    request<ChatMessage[]>(
      `/workspaces/${workspaceId}/conversations/${conversationId}/messages?limit=${limit}&offset=${offset}`,
    ),
  ask: (
    workspaceId: string,
    conversationId: string,
    content: string,
    mode: "automatic" | "document_search" | "deep_analysis",
  ) =>
    request<ChatMessage>(
      `/workspaces/${workspaceId}/conversations/${conversationId}/messages`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content, mode }),
      },
    ),
  editMessage: (
    workspaceId: string,
    conversationId: string,
    messageId: string,
    content: string,
  ) =>
    request<ChatMessage>(
      `/workspaces/${workspaceId}/conversations/${conversationId}/messages/${messageId}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      },
    ),
  sourceDetails: (workspaceId: string, chunkId: string) =>
    request<{
      chunk_id: string;
      content: string;
      document_title: string;
      document_version_id: string;
      version_number: number;
    }>(`/workspaces/${workspaceId}/sources/${chunkId}`),
  queryDebug: (workspaceId: string, queryRunId: string) =>
    request<QueryDebug>(`/workspaces/${workspaceId}/query-runs/${queryRunId}`),
};
