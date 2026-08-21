/** Boundary for OpenAPI-generated code. Feature code imports from this module only. */
import type { components } from "./generated/schema";
import { sanitizeToastDetail, toast } from "../components/ui";
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
  source_filename?: string | null;
  steps: WorkflowStep[];
  usage?: { recorded: boolean; model_calls: number; input_tokens: number | null; output_tokens: number | null; total_tokens: number | null; cost: string | null; currency: string | null; calls: unknown[] };
};
export type WorkflowEvent = {
  id: string;
  event_type: string;
  payload_json: string | null;
  created_at: string;
};
export type Conversation = components["schemas"]["ConversationRead"];
export type ChatMessage = components["schemas"]["MessageRead"];
export type QueryDebug = components["schemas"]["QueryDebug"] & {
  usage: {
    recorded: boolean;
    model_calls: number;
    input_tokens: number | null;
    output_tokens: number | null;
    total_tokens: number | null;
    cost: string | null;
    currency: string | null;
    calls: unknown[];
  };
};
export type Workspace = components["schemas"]["WorkspaceRead"];
export type CatalogDocument = components["schemas"]["DocumentRead"];
export type WorkspaceOverview = components["schemas"]["WorkspaceOverview"];
export type DashboardOverview = components["schemas"]["DashboardOverview"];
export type DocumentDetail = components["schemas"]["DocumentDetail"];
export type ProviderName = "openai" | "anthropic" | "ollama";
export type ModelCapability = {
  provider: ProviderName;
  model: string;
  chat: boolean;
  embeddings: boolean;
  digest: string | null;
};
export type ProviderStatus = {
  providers: { provider: ProviderName; configured: boolean; base_url?: string }[];
  capabilities: Record<ProviderName, ModelCapability[]>;
};
export type OllamaPullOperation = {
  operation_id: string;
  model: string;
  status: "running" | "completed" | "failed";
  completed: number;
  total: number;
  error: string | null;
};
export type OllamaCatalogModel = {
  name: string;
  description: string;
  capabilities: string[];
  sizes: string[];
  kind?: "llm" | "embedding";
};
export type GraphExplorer = {
  state: string;
  nodes: { id: string; label: string; description: string; attributes: Record<string, string> }[];
  edges: { id: string; source: string; target: string; label: string | null }[];
};
export type CanonicalEntity = components["schemas"]["CanonicalEntityRead"];
export type EntityEvidence = components["schemas"]["EntityEvidenceRead"];
export type IdentityOperation = components["schemas"]["IdentityOperationRead"];
export type MergeCurationRequest = components["schemas"]["MergeCurationRequest"];
export type SplitCurationRequest = components["schemas"]["SplitCurationRequest"];
export type KnowledgeGeneration = {
  generation_id: string;
  workflow_run_id: string | null;
  state: string;
  source_fingerprint: string;
  created_at: string;
  activated_at: string | null;
  failure: Record<string, unknown> | null;
  stages: {
    stage: string;
    state: string;
    input_fingerprint: string | null;
    output_fingerprint: string | null;
    metrics: Record<string, unknown>;
    error: Record<string, unknown> | null;
  }[];
};
const base = "/api/v1";
function mutationMessage(path: string, method: string) {
  if (path === "/workspaces" && method === "POST") return "Çalışma alanı oluşturuldu.";
  if (path.startsWith("/workspaces/") && method === "DELETE" && !path.includes("/documents/")) return "Çalışma alanı silindi.";
  if (path.includes("/uploads")) return "Yükleme ve indeksleme başlatıldı.";
  if (path.includes("/documents/") && method === "DELETE") return "Belge silme işlemi başlatıldı.";
  if (path.includes("/messages") && method === "POST") return "Yanıt hazır.";
  if (path.includes("/messages") && method === "PATCH") return "Mesaj güncellendi.";
  if (path.includes("/conversations") && method === "POST") return "Yeni sohbet oluşturuldu.";
  if (path.includes("/conversations/") && method === "DELETE") return "Sohbet silindi.";
  if (path.includes("/reset-defaults")) return "Varsayılan ayarlar geri yüklendi.";
  if (path.includes("/validate")) return "Sağlayıcı doğrulandı.";
  if (path.includes("/models/pull")) return "Model indirme işlemi başlatıldı.";
  if (path.includes("/embedding/health")) return "Embedding sağlık testi tamamlandı.";
  if (path.includes("/setup/complete")) return "Kurulum tamamlandı.";
  if (path.includes("/workflows/history")) return "Süreç geçmişi temizlendi.";
  if (path.startsWith("/workflows/")) return "Süreç güncellendi.";
  if (path === "/workflows" && method === "POST") return "Süreç başlatıldı.";
  if (path === "/settings" && method === "PUT") return "Ayarlar kaydedildi.";
  if (path.includes("/knowledge/")) return "Canonical bilgi düzenlendi.";
  return "İşlem tamamlandı.";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const method = init?.method?.toUpperCase() ?? "GET";
  try {
    const response = await fetch(`${base}${path}`, init);
    if (!response.ok) {
      const body = await response.json().catch(() => null) as { message?: string } | null;
      throw new Error(body?.message ?? "İstek tamamlanamadı.");
    }
    if (method !== "GET") toast.success(mutationMessage(path, method));
    if (response.status === 204) return undefined as T;
    return response.json() as Promise<T>;
  } catch (error) {
    const detail = sanitizeToastDetail(error);
    toast.error("İşlem tamamlanamadı.", detail);
    throw error;
  }
}
export const apiClient = {
  listWorkspaces: () => request<Workspace[]>("/workspaces"),
  createWorkspace: (name: string, slug: string, description?: string) => request<Workspace>("/workspaces", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, slug, description: description || null }) }),
  deleteWorkspace: (workspaceId: string) => request<void>(`/workspaces/${workspaceId}`, { method: "DELETE" }),
  overview: () => request<DashboardOverview>("/overview"),
  workspaceOverview: (workspaceId: string) => request<WorkspaceOverview>(`/workspaces/${workspaceId}/overview`),
  graph: (workspaceId: string) => request<GraphExplorer>(`/workspaces/${workspaceId}/graph`),
  knowledgeReadiness: (workspaceId: string) =>
    request<KnowledgeGeneration[]>(`/workspaces/${workspaceId}/knowledge/readiness`),
  listCanonicalEntities: (workspaceId: string) =>
    request<CanonicalEntity[]>(`/workspaces/${workspaceId}/knowledge/entities`),
  entityEvidence: (workspaceId: string, entityId: string) =>
    request<EntityEvidence[]>(`/workspaces/${workspaceId}/knowledge/entities/${entityId}/evidence`),
  identityHistory: (workspaceId: string) =>
    request<IdentityOperation[]>(`/workspaces/${workspaceId}/knowledge/identity-history`),
  addCanonicalAlias: (workspaceId: string, entityId: string, value: string, reason: string) =>
    request<IdentityOperation>(`/workspaces/${workspaceId}/knowledge/entities/${entityId}/aliases`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ value, reason }),
    }),
  removeCanonicalAlias: (workspaceId: string, entityId: string, value: string, reason: string) =>
    request<IdentityOperation>(`/workspaces/${workspaceId}/knowledge/entities/${entityId}/aliases/remove`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ value, reason }),
    }),
  mergeCanonicalEntities: (workspaceId: string, payload: MergeCurationRequest) =>
    request<IdentityOperation>(`/workspaces/${workspaceId}/knowledge/entities/merge`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    }),
  splitCanonicalEntity: (workspaceId: string, entityId: string, payload: SplitCurationRequest) =>
    request<IdentityOperation>(`/workspaces/${workspaceId}/knowledge/entities/${entityId}/split`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    }),
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
  providerStatus: () => request<ProviderStatus>("/settings/providers"),
  validateProvider: (provider: ProviderName, apiKey?: string) =>
    request<{ provider: string; status: string }>(`/settings/providers/${provider}/validate`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(apiKey ? { api_key: apiKey } : {}) }),
  pullOllamaModel: (model: string) => request<OllamaPullOperation>("/settings/ollama/models/pull", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ model }) }),
  ollamaPullStatus: (operationId: string) => request<OllamaPullOperation>(`/settings/ollama/models/pull/${operationId}`),
  ollamaCatalog: () => request<{ models: OllamaCatalogModel[] }>("/settings/ollama/catalog"),
  embeddingHealth: () => request<{ provider: string; model: string; dimension: number }>("/settings/embedding/health", { method: "POST" }),
  completeSetup: (dataPath?: string) => request<{ completed: boolean }>("/settings/setup/complete", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ data_path: dataPath }) }),
  resetSettings: () => request<{ settings: Record<string, unknown>; reindex_required: boolean }>("/settings/reset-defaults", { method: "POST" }),
  diagnostics: () => request<{ windows: { data_path: string; ollama_base_url: string }; workflows: Record<string, number>; reconciliation: { state: string; message: string } }>("/settings/diagnostics"),
  embeddingStatus: () => request<{ provider: string; model: string; installed: boolean; dimension: number | null; model_digest: string | null; last_benchmark: string | null; requires_full_reindex: boolean }>("/settings/embedding/status"),
  graphragEstimate: () => request<{ update_mode: string; pending_document_threshold: number; confirmation_threshold_usd: number; requires_confirmation: boolean }>("/settings/graphrag/estimate"),
  listWorkflows: async () => request<WorkflowRun[]>("/workflows"),
  clearWorkflowHistory: () => request<{ deleted: number }>("/workflows/history", { method: "DELETE" }),
  workflow: (id: string) => request<WorkflowRun>(`/workflows/${id}`),
  createWorkflow: (workspaceId: string, jobType: "graphrag_reindex" | "knowledge_reindex") =>
    request<WorkflowRun>("/workflows", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ workspace_id: workspaceId, job_type: jobType }),
    }),
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
  deleteConversation: (workspaceId: string, conversationId: string) =>
    request<void>(`/workspaces/${workspaceId}/conversations/${conversationId}`, { method: "DELETE" }),
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
