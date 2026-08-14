import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import {
  apiClient,
  type CatalogDocument,
  type WorkflowRun,
  type Workspace,
} from "../api/client";
import { formatCortexDate } from "../utils/date";
import {
  AButton,
  ABadge,
  ACard,
  AFileUpload,
  AInfoPanel,
  AInput,
  ALoading,
  ASelect,
  ATextarea,
  useConfirmation,
} from "../components/ui";
import { AFlowCanvas, type AFlowEdge, type AFlowNode } from "../flow/AFlowCanvas";
import { graphNodePresentation, graphNodeTypes, type GraphNode } from "../flow/AGraphNodes";
import { useWorkspace } from "../app/workspace";

const ingestionSteps = ["parse", "normalize", "logical_documents", "chunk", "index"];
const GRAPH_NODE_COLUMNS = 8;
const terminalWorkflowStates = new Set([
  "completed",
  "failed",
  "cancelled",
  "interrupted",
]);

type UploadedWorkflow = {
  filename: string;
  workflowRunId: string;
  workflow?: WorkflowRun;
};

function UploadWorkflowStatus({ upload }: { upload: UploadedWorkflow }) {
  const workflow = upload.workflow;
  const persisted = new Map(
    workflow?.steps.map((step) => [step.step_name, step]),
  );
  return (
    <section
      className="rounded border p-3"
      aria-label={`${upload.filename} işlem durumu`}
    >
      <div className="mb-2 flex items-center justify-between gap-2">
        <strong className="truncate">{upload.filename}</strong>
        <span className="text-xs opacity-70">
          {workflow?.state ?? "durum alınıyor"}
        </span>
      </div>
      <ol className="grid gap-1 text-sm">
        {ingestionSteps.map((stepName) => {
          const step = persisted.get(stepName);
          const completed =
            step?.state === "completed" ||
            (!step && workflow?.state === "completed");
          const state = step?.state ?? (completed ? "completed" : "pending");
          return (
            <li key={stepName} className="flex items-center gap-2">
              <span
                aria-hidden="true"
                className={completed ? "text-green-600" : "opacity-50"}
              >
                {completed ? "✓" : "○"}
              </span>
              <span>{stepName.replaceAll("_", " ")}</span>
              <span className="text-xs opacity-60">{state}</span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function useWorkspaces() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [error, setError] = useState<string | null>(null);
  const refresh = useCallback(async () => {
    try {
      setWorkspaces(await apiClient.listWorkspaces());
      setError(null);
    } catch {
      setError("Çalışma alanları alınamadı.");
    }
  }, []);
  useEffect(() => {
    void refresh();
  }, [refresh]);
  return { workspaces, error, refresh };
}

export function WorkspaceSelect({
  workspaces,
  value,
  onChange,
  disabled = false,
}: {
  workspaces: Workspace[];
  value: string;
  onChange: (id: string) => void;
  disabled?: boolean;
}) {
  return (
    <ASelect
      value={value}
      onChange={(event) => onChange(event.value)}
      options={workspaces.map((w) => ({ label: w.name, value: w.id }))}
      placeholder="Çalışma alanı seçin"
      className="max-w-md"
      disabled={disabled}
    />
  );
}

export function DashboardPage() {
  const [data, setData] = useState<Awaited<
    ReturnType<typeof apiClient.overview>
  > | null>(null);
  useEffect(() => {
    void apiClient
      .overview()
      .then(setData)
      .catch(() => setData(null));
  }, []);
  return (
    <div className="page-stack">
      <section className="page-hero">
        <div>
          <p className="eyebrow">Genel görünüm</p>
          <h1>Bilgi çalışma alanınız</h1>
          <p>Belgeler, indeksler ve arka plan işlemleri tek yerde.</p>
        </div>
        <Link to="/upload">
          <AButton label="Belge yükle" icon="upload" />
        </Link>
      </section>
      <div className="metric-grid">
        {[
          ["Çalışma alanı", data?.workspace_count],
          ["Belge", data?.document_count],
          ["Parça", data?.chunk_count],
        ].map(([label, value]) => (
          <ACard key={String(label)}>
            <span className="metric-label">{label}</span>
            <strong className="metric-value">{value ?? "—"}</strong>
          </ACard>
        ))}
      </div>
      <ACard title="Son güncellenen belgeler">
        {data?.recent_documents.length ? (
          <div className="resource-list">
            {data.recent_documents.map((doc) => (
              <Link
                key={doc.id}
                to={`/documents/${doc.id}?workspace=${doc.workspace_id}`}
              >
                <strong>{doc.title}</strong>
                <span>
                  {doc.workspace_name} ·{" "}
                  {formatCortexDate(doc.updated_at, { dateStyle: "short" })}
                </span>
              </Link>
            ))}
          </div>
        ) : (
          <AInfoPanel title="Henüz içerik yok">
            Bir çalışma alanı oluşturup belge yükleyerek başlayın.
          </AInfoPanel>
        )}
      </ACard>
    </div>
  );
}

export function WorkspacesPage() {
  const { workspaces, error, refresh } = useWorkspaces();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const [createError, setCreateError] = useState("");
  const create = async (event: FormEvent) => {
    event.preventDefault();
    const slug = slugify(name);
    if (!slug) {
      setCreateError("Çalışma alanı adı en az bir harf veya sayı içermeli.");
      return;
    }
    setSaving(true);
    setCreateError("");
    try {
      await apiClient.createWorkspace(name.trim(), slug, description.trim());
      setName("");
      setDescription("");
      await refresh();
    } catch (reason) {
      setCreateError(
        reason instanceof Error
          ? reason.message
          : "Çalışma alanı oluşturulamadı.",
      );
    } finally {
      setSaving(false);
    }
  };
  return (
    <div className="page-stack two-column">
      <ACard title="Çalışma alanları">
        {error && <p role="alert">{error}</p>}
        <div className="resource-list">
          {workspaces.map((w) => (
            <Link key={w.id} to={`/workspace/${w.id}`}>
              <strong>{w.name}</strong>
              <span>{w.description || w.slug}</span>
            </Link>
          ))}
          {!workspaces.length && (
            <AInfoPanel title="İlk çalışma alanınızı oluşturun">
              Her alan, belgelerini ve indekslerini birbirinden izole tutar.
            </AInfoPanel>
          )}
        </div>
      </ACard>
      <ACard title="Yeni çalışma alanı">
        <form className="form-stack" onSubmit={create}>
          <AInput
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Örn. Osmanlı arşivi"
            required
          />
          <ATextarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Kısa açıklama (isteğe bağlı)"
            rows={3}
          />
          <AButton
            type="submit"
            label={saving ? "Oluşturuluyor…" : "Oluştur"}
            disabled={saving}
          />
          {createError && <p role="alert">{createError}</p>}
        </form>
      </ACard>
    </div>
  );
}

function slugify(value: string) {
  return value
    .trim()
    .toLocaleLowerCase("tr-TR")
    .replaceAll("ı", "i")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "");
}

export function WorkspaceOverviewPage() {
  const { workspaceId = "" } = useParams();
  const [data, setData] = useState<Awaited<
    ReturnType<typeof apiClient.workspaceOverview>
  > | null>(null);
  useEffect(() => {
    if (workspaceId)
      void apiClient.workspaceOverview(workspaceId).then(setData);
  }, [workspaceId]);
  return (
    <div className="page-stack">
      <section className="page-hero">
        <div>
          <p className="eyebrow">Çalışma alanı</p>
          <h1>İndeks ve içerik durumu</h1>
        </div>
        <Link to={`/upload?workspace=${workspaceId}`}>
          <AButton label="Belge yükle" icon="upload" />
        </Link>
      </section>
      <div className="metric-grid">
        {[
          ["Belge", data?.document_count],
          ["Parça", data?.chunk_count],
          ["Graf bekleyen", data?.pending_graph_documents],
        ].map(([label, value]) => (
          <ACard key={String(label)}>
            <span className="metric-label">{label}</span>
            <strong className="metric-value">{value ?? "—"}</strong>
          </ACard>
        ))}
      </div>
      <ACard title="İndeksler">
        <div className="status-grid">
          <span>
            Yoğun arama <b>{data?.dense_state ?? "—"}</b>
          </span>
          <span>
            Seyrek arama <b>{data?.sparse_state ?? "—"}</b>
          </span>
          <span>
            GraphRAG <b>{data?.graphrag_state ?? "—"}</b>
          </span>
        </div>
      </ACard>
    </div>
  );
}

export function DocumentsPage() {
  const { workspaces, workspaceId } = useWorkspace();
  const [documents, setDocuments] = useState<CatalogDocument[]>([]);
  const [selectedDocumentId, setSelectedDocumentId] = useState("");
  const [selectedDetail, setSelectedDetail] = useState<Awaited<
    ReturnType<typeof apiClient.documentDetails>
  > | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const confirm = useConfirmation();
  const [deleting, setDeleting] = useState<Record<string, string>>({});
  const [deleteError, setDeleteError] = useState("");
  const refresh = useCallback(() => {
    if (workspaceId)
      void apiClient.listDocuments(workspaceId).then((nextDocuments) => {
        setDocuments(nextDocuments);
        setSelectedDocumentId((current) =>
          nextDocuments.some((document) => document.id === current)
            ? current
            : nextDocuments[0]?.id ?? "",
        );
      });
  }, [workspaceId]);
  useEffect(refresh, [refresh]);
  useEffect(() => {
    setSelectedDetail(null);
    if (!workspaceId || !selectedDocumentId) return;
    setPreviewLoading(true);
    void apiClient
      .documentDetails(workspaceId, selectedDocumentId)
      .then(setSelectedDetail)
      .finally(() => setPreviewLoading(false));
  }, [workspaceId, selectedDocumentId]);
  useEffect(() => {
    const queuedDeletes = Object.entries(deleting).filter(
      ([, workflowRunId]) => Boolean(workflowRunId),
    );
    if (!queuedDeletes.length) return;
    const timer = window.setInterval(() => {
      void Promise.all(
        queuedDeletes.map(async ([documentId, workflowRunId]) => {
          const workflow = await apiClient.workflow(workflowRunId);
          if (!terminalWorkflowStates.has(workflow.state)) return;
          setDeleting((current) => {
            const remaining = { ...current };
            delete remaining[documentId];
            return remaining;
          });
          if (workflow.state === "completed") {
            refresh();
          } else {
            setDeleteError("Belge silme iÅŸlemi tamamlanamadÄ±. Ä°ÅŸlemler sayfasÄ±ndan ayrÄ±ntÄ±larÄ± inceleyin.");
          }
        }),
      ).catch(() => {
        setDeleteError("Belge silme durumu alÄ±namadÄ±. LÃ¼tfen Ä°ÅŸlemler sayfasÄ±nÄ± kontrol edin.");
      });
    }, 1000);
    return () => window.clearInterval(timer);
  }, [deleting, refresh]);
  const remove = async (documentId: string) => {
    if (
      workspaceId &&
      (await confirm({
        title: "Belgeyi sil",
        message:
          "Belge silme işlemi arka plan sürecinde yürütülecek. Devam edilsin mi?",
        confirmLabel: "Sil",
        danger: true,
      }))
    ) {
      setDeleteError("");
      try {
        const { workflow_run_id: workflowRunId } = await apiClient.deleteDocument(
          workspaceId,
          documentId,
        );
        setDeleting((current) => ({ ...current, [documentId]: workflowRunId }));
      } catch (reason) {
        setDeleteError(
          reason instanceof Error
            ? reason.message
            : "Belge silme iÅŸlemi baÅŸlatÄ±lamadÄ±.",
        );
      }
    }
  };
  return (
    <div className="page-stack">
      <section className="page-hero compact">
        <div>
          <p className="eyebrow">Arşiv</p>
          <h1>Belgeler</h1>
        </div>
        <Link to={`/upload?workspace=${workspaceId}`}>
          <AButton label="Belge yükle" icon="upload" />
        </Link>
      </section>
      <WorkspaceSelect workspaces={workspaces} value={workspaceId} onChange={() => undefined} disabled />
      <div className="documents-split-view">
      <ACard title="Belge listesi">
        {deleteError && <p role="alert">{deleteError}</p>}
        {documents.length ? (
          <div className="document-table">
            {documents.map((doc) => (
              <div key={doc.id} className={selectedDocumentId === doc.id ? "is-selected" : undefined}>
                <button
                  type="button"
                  className="document-link"
                  aria-pressed={selectedDocumentId === doc.id}
                  onClick={() => setSelectedDocumentId(doc.id)}
                >
                  <strong>{doc.title}</strong>
                  <span>
                    {doc.state ?? "hazır"} · sürüm {doc.version_number ?? "—"} ·{" "}
                    {doc.size_bytes
                      ? `${Math.ceil(doc.size_bytes / 1024)} KB`
                      : ""}
                  </span>
                </button>
                <AButton
                  label={deleting[doc.id] ? "Siliniyorâ€¦" : "Sil"}
                  text
                  severity="secondary"
                  onClick={() => void remove(doc.id)}
                  disabled={Boolean(deleting[doc.id])}
                />
              </div>
            ))}
          </div>
        ) : (
          <AInfoPanel title="Belge bulunamadı">
            Seçili çalışma alanına henüz belge yüklenmedi.
          </AInfoPanel>
        )}
      </ACard>
      <ACard title={selectedDetail?.title ?? "Belge önizlemesi"}>
        {previewLoading ? (
          <AInfoPanel title="Önizleme yükleniyor">Belge içeriği getiriliyor.</AInfoPanel>
        ) : selectedDetail ? (
          <div className="document-preview-panel">
            <div className="status-grid">
              <span>Sürüm <b>{selectedDetail.version_number ?? "—"}</b></span>
              <span>Parça <b>{selectedDetail.chunk_count ?? "—"}</b></span>
              <span>Durum <b>{selectedDetail.state ?? "—"}</b></span>
            </div>
            <pre className="document-preview">
              {selectedDetail.normalized_content ?? "İçerik bulunamadı."}
            </pre>
          </div>
        ) : (
          <AInfoPanel title="Belge seçin">Önizlemek için soldaki listeden bir belge seçin.</AInfoPanel>
        )}
      </ACard>
      </div>
    </div>
  );
}

export function DocumentDetailPage() {
  const { documentId = "" } = useParams();
  const [detail, setDetail] = useState<Awaited<
    ReturnType<typeof apiClient.documentDetails>
  > | null>(null);
  const params = new URLSearchParams(window.location.search);
  const workspaceId = params.get("workspace") || "";
  useEffect(() => {
    if (workspaceId && documentId)
      void apiClient.documentDetails(workspaceId, documentId).then(setDetail);
  }, [workspaceId, documentId]);
  if (!workspaceId)
    return (
      <AInfoPanel title="Çalışma alanı gerekli">
        Belgeye çalışma alanı bağlamı olmadan erişilemez.
      </AInfoPanel>
    );
  return (
    <div className="page-stack">
      <Link to="/documents">← Belgelere dön</Link>
      <ACard title={detail?.title ?? "Belge"}>
        <div className="status-grid">
          <span>
            Sürüm <b>{detail?.version_number ?? "—"}</b>
          </span>
          <span>
            Parça <b>{detail?.chunk_count ?? "—"}</b>
          </span>
          <span>
            Durum <b>{detail?.state ?? "—"}</b>
          </span>
        </div>
      </ACard>
      <ACard title="Normalize edilmiş içerik">
        <pre className="document-preview">
          {detail?.normalized_content ??
            "İçerik yükleniyor veya dosya artık erişilebilir değil."}
        </pre>
      </ACard>
    </div>
  );
}

export function UploadPage() {
  const { workspaces, workspaceId } = useWorkspace();
  const [files, setFiles] = useState<File[]>([]);
  const [message, setMessage] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadedWorkflows, setUploadedWorkflows] = useState<
    UploadedWorkflow[]
  >([]);
  const uploadedWorkflowIds = useMemo(
    () => uploadedWorkflows.map((upload) => upload.workflowRunId).join(","),
    [uploadedWorkflows],
  );
  const hasIncompleteUploadedWorkflow = uploadedWorkflows.some(
    (upload) => !upload.workflow || !terminalWorkflowStates.has(upload.workflow.state),
  );
  const refreshUploadedWorkflows = useCallback(async () => {
    if (!uploadedWorkflowIds) return;
    const workflows = await Promise.all(
      uploadedWorkflowIds.split(",").map((workflowRunId) => apiClient.workflow(workflowRunId)),
    );
    const byId = new Map(workflows.map((workflow) => [workflow.id, workflow]));
    setUploadedWorkflows((current) =>
      current.map((upload) => ({
        ...upload,
        workflow: byId.get(upload.workflowRunId),
      })),
    );
  }, [uploadedWorkflowIds]);
  useEffect(() => {
    if (!uploadedWorkflowIds) return;
    void refreshUploadedWorkflows();
    if (!hasIncompleteUploadedWorkflow)
      return;
    const timer = window.setInterval(
      () => void refreshUploadedWorkflows(),
      3000,
    );
    return () => window.clearInterval(timer);
  }, [hasIncompleteUploadedWorkflow, refreshUploadedWorkflows, uploadedWorkflowIds]);
  const upload = async () => {
    if (!workspaceId) {
      setMessage("Önce bir çalışma alanı seçin.");
      return;
    }
    if (!files.length) {
      setMessage("Önce en az bir dosya seçin.");
      return;
    }
    setUploading(true);
    try {
      const result = await apiClient.upload(workspaceId, files);
      setMessage(
        `${result.uploads.length} belge alındı; indeksleme arka planda başlatıldı.`,
      );
      setUploadedWorkflows(
        result.uploads.map((item) => ({
          filename: item.filename,
          workflowRunId: item.workflow_run_id,
        })),
      );
      setFiles([]);
    } catch {
      setMessage(
        "Yükleme tamamlanamadı. Dosya biçimini ve yinelenen içeriği kontrol edin.",
      );
    } finally {
      setUploading(false);
    }
  };
  return (
    <div className="page-stack two-column">
      <ACard title="Belge yükle">
        <div className="form-stack">
          <WorkspaceSelect workspaces={workspaces} value={workspaceId} onChange={() => undefined} disabled />
          <AFileUpload
            multiple
            accept=".md,.txt,.pdf,.docx,text/plain,text/markdown,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
          />
          <AButton
            label={uploading ? "Yükleniyor…" : "Yükle ve indeksle"}
            icon="upload"
            onClick={() => void upload()}
            disabled={uploading}
          />
          {message && (
            <div className="upload-notice">
              <AInfoPanel>{message}</AInfoPanel>
            </div>
          )}
        </div>
      </ACard>
      <ACard title="Yükleme akışı">
        <p>
          Kaynak dosya korunur, Markdown’a dönüştürülür, parçalara ayrılır ve
          kalıcı bir indeksleme süreci başlatılır.
        </p>
        <p className="text-sm opacity-70">
          Desteklenen biçimler: Markdown, metin, PDF ve DOCX.
        </p>
        {uploadedWorkflows.length > 0 && (
          <div className="mt-4 grid gap-3">
            <strong>İşlem durumu</strong>
            {uploadedWorkflows.map((upload) => (
              <UploadWorkflowStatus
                key={upload.workflowRunId}
                upload={upload}
              />
            ))}
          </div>
        )}
      </ACard>
    </div>
  );
}

export function GraphPage() {
  const { workspaces, workspaceId: id } = useWorkspace();
  const [data, setData] = useState<Awaited<
    ReturnType<typeof apiClient.workspaceOverview>
  > | null>(null);
  const [graph, setGraph] = useState<Awaited<
    ReturnType<typeof apiClient.graph>
  > | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [queueing, setQueueing] = useState(false);
  const [graphIndexing, setGraphIndexing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [activeDescriptionId, setActiveDescriptionId] = useState<string | null>(null);
  const refresh = useCallback(() => {
    if (!id) return;
    setLoading(true);
    void Promise.all([
      apiClient.workspaceOverview(id),
      apiClient.graph(id),
      apiClient.listWorkflows(),
    ])
      .then(([overview, explorer, workflows]) => {
        setData(overview);
        setGraph(explorer);
        setGraphIndexing(
          workflows.some(
            (workflow) =>
              workflow.workspace_id === id &&
              workflow.job_type === "graphrag_reindex" &&
              ["queued", "running", "cancelling"].includes(workflow.state),
          ),
        );
        setError(null);
        setLoading(false);
      })
      .catch(() => setError("Graf verisi alınamadı. Bağlantıyı ve çalışma alanı durumunu kontrol edin."));
  }, [id]);
  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => {
    if (error) setLoading(false);
  }, [error]);
  useEffect(() => {
    if (!graphIndexing) return;
    const timer = window.setInterval(refresh, 5000);
    return () => window.clearInterval(timer);
  }, [graphIndexing, refresh]);
  const startIndexing = async () => {
    if (!id) return;
    setQueueing(true);
    try {
      await apiClient.createWorkflow(id, "graphrag_reindex");
      refresh();
    } catch {
      setError("GraphRAG indeksleme işi başlatılamadı.");
    } finally {
      setQueueing(false);
    }
  };
  const nodes: AFlowNode[] = (graph?.nodes ?? []).map((node, index): GraphNode => {
    const presentation = graphNodePresentation(node.attributes);
    const column = index % GRAPH_NODE_COLUMNS;
    const row = Math.floor(index / GRAPH_NODE_COLUMNS);
    return {
    id: node.id,
    type: "graph-entity",
    position: { x: column * 165 + (row % 2) * 82, y: row * 130 },
    data: {
      label: node.label,
      description: node.description,
      ...presentation,
      descriptionOpen: activeDescriptionId === node.id,
      onDescriptionToggle: (nodeId) => setActiveDescriptionId((activeId) => activeId === nodeId ? null : nodeId),
    },
    style: { height: 108, minHeight: 108, width: 108 },
    zIndex: activeDescriptionId === node.id ? 1000 : 0,
    };
  });
  const edges: AFlowEdge[] = (graph?.edges ?? []).map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    label: edge.label ?? undefined,
    type: "bezier",
    style: { stroke: "var(--cortex-secondary)", strokeDasharray: "5 4", strokeWidth: 1.5 },
    labelStyle: { fill: "var(--cortex-text)", fontSize: 10, fontWeight: 750 },
    labelBgPadding: [5, 3],
    labelBgBorderRadius: 4,
    labelBgStyle: { fill: "var(--cortex-panel)", fillOpacity: 0.98, stroke: "var(--cortex-line)", strokeWidth: 1 },
  }));
  const graphBadgeTone =
    data?.graphrag_state === "ready"
      ? "success"
      : data?.graphrag_state === "stale"
        ? "warning"
        : "secondary";
  return (
    <div className="page-stack">
      <WorkspaceSelect workspaces={workspaces} value={id} onChange={() => undefined} disabled />
      {id && loading ? (
        <ALoading label="Graf verisi yükleniyor…" />
      ) : (
      <>
      <ACard title="GraphRAG durumu">
        <AInfoPanel
          title={
            data?.graphrag_state === "ready"
              ? "Graf sorguya hazır"
              : "Graf henüz hazır değil"
          }
        >
          Bekleyen belge: {data?.pending_graph_documents ?? "—"}. Grafik
          düğümleri, GraphRAG indeksleme tamamlandığında burada
          görselleştirilir.
        </AInfoPanel>
      </ACard>
      {data?.graphrag_state === "ready" ? (
        <AInfoPanel title="GraphRAG indeksi güncel">
          {data.document_count} belge GraphRAG için işlenmiş; aşağıdaki düğüm ve ilişkiler bu
          indeksin görselleştirilmiş halidir.
        </AInfoPanel>
      ) : data?.document_count ? (
        <AInfoPanel title="Belgeler henüz bilgi grafiğine dahil değil">
          {data.document_count} belge normal arama indeksine alınmış durumda; GraphRAG durumu
          <b> {data.graphrag_state}</b>. Bu belgeleri graf düğümlerine dönüştürmek için aşağıdaki
          “GraphRAG indeksle” işlemini başlatın.
        </AInfoPanel>
      ) : null}
      <div className="flex flex-wrap items-center gap-2">
        <ABadge value={data?.graphrag_state ?? "bilinmiyor"} severity={graphBadgeTone} />
        <AButton label="Grafı yenile" icon="activity" outlined onClick={refresh} />
        <AButton
          label={graphIndexing ? "GraphRAG indeksleniyor" : "GraphRAG indeksle"}
          icon="graph"
          loading={queueing}
          disabled={!id || queueing || graphIndexing || data?.document_count === 0}
          onClick={() => void startIndexing()}
        />
      </div>
      {error && <AInfoPanel title="Graf kullanılamıyor">{error}</AInfoPanel>}
      {nodes.length > 0 ? (
        <ACard title="Bilgi grafiği">
          <div className="system-map__legend graph-page__legend" aria-label="Graf varlık türleri">
            {["input", "service", "retrieval", "processor", "llm-local", "decision", "storage"].map((kind) => (
              <span key={kind} className={`system-map__legend-item is-${kind}`}><i aria-hidden="true" />{({ input: "Kişi", service: "Organizasyon", retrieval: "Konum", processor: "Olay", "llm-local": "Ürün / teknoloji", decision: "Kavram", storage: "Diğer" } as Record<string, string>)[kind]}</span>
            ))}
          </div>
          <AFlowCanvas nodes={nodes} edges={edges} nodeTypes={graphNodeTypes} height={620} showMiniMap />
        </ACard>
      ) : (
        <AInfoPanel title="Henüz gösterilecek bir grafik yok">
          Çalışma alanındaki belgeler için GraphRAG indekslemesini başlatın. İşin ilerlemesini
          Süreçler sayfasından takip edebilirsiniz.
        </AInfoPanel>
      )}
      </>
      )}
    </div>
  );
}

export function HealthPage() {
  const [health, setHealth] = useState<{
    status: string;
    services: Record<string, string>;
  } | null>(null);
  useEffect(() => {
    void apiClient.getHealth().then(setHealth);
  }, []);
  return (
    <div className="page-stack">
      <ACard title="Sistem sağlığı">
        <div className="status-grid">
          {Object.entries(health?.services ?? {}).map(([name, state]) => (
            <span key={name}>
              {name}
              <b>{state}</b>
            </span>
          ))}
        </div>
      </ACard>
    </div>
  );
}
