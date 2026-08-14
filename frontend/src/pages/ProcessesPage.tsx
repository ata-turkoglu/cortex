import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiClient, type WorkflowEvent, type WorkflowRun } from "../api/client";
import { formatCortexDateTime, formatCortexTime } from "../utils/date";
import { useJobsStore } from "../app/jobs";
import {
  AFlowCanvas,
  type AFlowEdge,
  type AFlowNode,
} from "../flow/AFlowCanvas";
import { processNodeTypes, type ProcessNodeKind } from "../flow/AProcessFlowNodes";
import { workflowSchema } from "../flow/workflowSchemas";
import { AButton, ACard, ADialog, AInfoPanel, ALoading, useConfirmation } from "../components/ui";

const activeStates = new Set(["queued", "running", "cancelling"]);
const terminalStates = new Set(["completed", "failed", "cancelled", "interrupted"]);

function substepState(parentState: string) {
  if (parentState === "completed") return "completed";
  if (parentState === "failed") return "unknown";
  return parentState === "running" ? "running" : "pending";
}

function processNodeKind(id: string, technology: string): ProcessNodeKind {
  if (id === "embedding" || /embedding/i.test(technology)) return "embedding";
  if (/LLM|GraphRAG extraction|GraphRAG summary|GraphRAG community/i.test(technology)) return "api";
  if (/SQLite|Qdrant|filesystem|Parquet|JSON/i.test(technology)) return "storage";
  if (/cleanup|reconcile|clear_active_vectors/i.test(id)) return "maintenance";
  if (/snapshot|materialize|parse|normalize|mark/i.test(id)) return "prepare";
  return "processor";
}

function sameWorkflowRuns(current: WorkflowRun[], next: WorkflowRun[]) {
  if (current.length !== next.length) return false;
  return current.every((run, index) => {
    const candidate = next[index];
    return (
      run.id === candidate.id &&
      run.state === candidate.state &&
      run.recovery_state === candidate.recovery_state &&
      run.updated_at === candidate.updated_at &&
      run.steps.length === candidate.steps.length &&
      run.steps.every((step, stepIndex) => {
        const nextStep = candidate.steps[stepIndex];
        return (
          step.id === nextStep.id &&
          step.state === nextStep.state &&
          step.retry_count === nextStep.retry_count &&
          step.checkpoint_json === nextStep.checkpoint_json
        );
      })
    );
  });
}

export function ProcessesPage() {
  const runs = useJobsStore((state) => state.workflowRuns);
  const setRuns = useJobsStore((state) => state.setWorkflowRuns);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [details, setDetails] = useState<WorkflowEvent[]>([]);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [copyMessage, setCopyMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastSuccessfulRefresh, setLastSuccessfulRefresh] = useState<Date>();
  const [streamStatus, setStreamStatus] = useState<"idle" | "connecting" | "live" | "reconnecting">("idle");
  const refreshInFlight = useRef(false);
  const refreshTimer = useRef<number | undefined>(undefined);
  const setJobs = useJobsStore((state) => state.setJobs);
  const confirm = useConfirmation();
  const [clearingHistory, setClearingHistory] = useState(false);
  const refresh = useCallback(async () => {
    if (refreshInFlight.current) return;
    refreshInFlight.current = true;
    try {
      const next = await apiClient.listWorkflows();
      if (!sameWorkflowRuns(useJobsStore.getState().workflowRuns, next)) {
        setRuns(next);
        setJobs(
          next
            .filter((run) => activeStates.has(run.state))
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
      }
      setError(null);
      setLastSuccessfulRefresh(new Date());
    } catch {
      setError("Süreç durumu alınamadı.");
    } finally {
      refreshInFlight.current = false;
      setLoading(false);
    }
  }, [setJobs, setRuns]);
  const scheduleRefresh = useCallback(() => {
    if (refreshTimer.current !== undefined) return;
    refreshTimer.current = window.setTimeout(() => {
      refreshTimer.current = undefined;
      void refresh();
    }, 500);
  }, [refresh]);
  useEffect(() => {
    void refresh();
    return () => {
      if (refreshTimer.current !== undefined) window.clearTimeout(refreshTimer.current);
    };
  }, [refresh]);
  const activeRunIds = useMemo(
    () =>
      runs
        .filter((run) => activeStates.has(run.state))
        .map((run) => run.id)
        .join(","),
    [runs],
  );
  useEffect(() => {
    if (!activeRunIds) {
      setStreamStatus("idle");
      return undefined;
    }
    setStreamStatus("connecting");
    const connectedRuns = new Set<string>();
    const updateStreamStatus = () => setStreamStatus(connectedRuns.size ? "live" : "reconnecting");
    const streams = activeRunIds
      .split(",")
      .filter(Boolean)
      .map((runId) => {
        const stream = apiClient.workflowEvents(runId);
        stream.onopen = () => {
          connectedRuns.add(runId);
          updateStreamStatus();
        };
        stream.onerror = () => {
          connectedRuns.delete(runId);
          updateStreamStatus();
        };
        stream.onmessage = scheduleRefresh;
        for (const eventType of [
          "queued",
          "started",
          "step_started",
          "step_completed",
          "completed",
          "failed",
          "cancelled",
          "interrupted",
        ])
          stream.addEventListener(eventType, scheduleRefresh);
        return stream;
      });
    return () => streams.forEach((stream) => stream.close());
  }, [activeRunIds, scheduleRefresh]);
  const selected = runs.find((run) => run.id === selectedId) ?? runs[0];
  const displayedSteps = useMemo(() => {
    if (!selected) return [];
    const persisted = new Map(
      selected.steps.map((step) => [step.step_name, step]),
    );
    const schema = workflowSchema(selected.job_type);
    const steps = schema?.steps ?? selected.steps.map((step) => ({ id: step.step_name, label: step.step_name.replaceAll("_", " "), description: "Bu workflow sürümünde açıklama bulunmuyor.", technology: "Workflow definition", guarantee: "Durum SQLite'tan gelir." }));
    return steps.map(
      (schemaStep) =>
        ({
          ...(persisted.get(schemaStep.id) ?? {
            id: `schema-${selected.id}-${schemaStep.id}`,
            step_name: schemaStep.id,
          state: "pending",
          retry_count: 0,
          checkpoint_json: null,
          }),
          schema: schemaStep,
        }),
    );
  }, [selected]);
  const flowSteps = useMemo(
    () =>
      displayedSteps.flatMap((step) => [
        { id: step.id, title: step.schema.label, description: step.schema.description, technology: step.schema.technology, state: step.state, kind: processNodeKind(step.schema.id, step.schema.technology) },
        ...(step.schema.substeps ?? []).map((substep) => ({
          id: `${step.id}:${substep.id}`,
          title: substep.label,
          description: substep.description,
          technology: substep.technology,
          state: substepState(step.state),
          kind: processNodeKind(substep.id, substep.technology),
        })),
      ]),
    [displayedSteps],
  );
  const { nodes, edges } = useMemo(
    () => ({
      nodes: selected
        ? (() => {
            const columns = Math.min(4, Math.max(flowSteps.length, 1));
            const rows = Math.ceil(flowSteps.length / columns);
            const positionFor = (index: number) => {
              const row = Math.floor(index / columns);
              const slot = index % columns;
              const column = row % 2 === 0 ? slot : columns - slot - 1;
              return { x: 20 + column * 230, y: 64 + row * 220 };
            };
            return [
            {
              id: "workflow-group",
              type: "process-group",
              position: { x: 0, y: 0 },
              data: { title: workflowSchema(selected.job_type)?.label ?? selected.job_type, status: selected.state },
              draggable: false,
              selectable: false,
              focusable: false,
              style: {
                width: columns * 230 + 40,
                height: rows * 220 + 78,
                zIndex: 0,
              },
            } as AFlowNode,
            ...flowSteps.map(
              (step, index): AFlowNode => ({
                id: step.id,
                type: "process",
                parentId: "workflow-group",
                extent: "parent",
                position: positionFor(index),
                data: { title: step.title, description: step.description, technology: step.technology, status: step.state, kind: step.kind },
                className: `workflow-${step.state}`,
                style: { width: 190, zIndex: 1 },
              }),
            ),
          ];
          })()
        : [],
      edges:
        flowSteps.slice(1).map(
          (step, index): AFlowEdge => {
            const currentRow = Math.floor(index / Math.min(4, Math.max(flowSteps.length, 1)));
            const nextRow = Math.floor((index + 1) / Math.min(4, Math.max(flowSteps.length, 1)));
            const forward = currentRow % 2 === 0;
            return ({
            id: `${index}`,
            source: flowSteps[index].id,
            target: step.id,
            sourceHandle: nextRow > currentRow ? "source-bottom" : forward ? "source-right" : "source-left",
            targetHandle: nextRow > currentRow ? "target-top" : forward ? "target-left" : "target-right",
            type: "bezier",
            animated: step.state === "running" || flowSteps[index].state === "running",
            style: { stroke: "var(--cortex-secondary)", strokeWidth: 1.75 },
            zIndex: 1,
            });
          },
        ) ?? [],
    }),
    [flowSteps, selected],
  );
  const showDetails = async (run: WorkflowRun) => {
    setSelectedId(run.id);
    setDetails(await apiClient.workflowEventHistory(run.id));
    setCopyMessage(null);
    setDetailsOpen(true);
  };
  const failedDetails = useMemo(
    () =>
      details
        .filter((event) => event.event_type === "failed")
        .map((event) => {
          try {
            const payload = JSON.parse(event.payload_json ?? "{}") as {
              details?: { summary?: string };
            };
            return { id: event.id, summary: payload.details?.summary ?? event.payload_json ?? "" };
          } catch {
            return { id: event.id, summary: event.payload_json ?? "" };
          }
        }),
    [details],
  );
  const copyFailure = async (summary: string) => {
    try {
      await navigator.clipboard.writeText(summary);
      setCopyMessage("Hata kopyalandı.");
    } catch {
      setCopyMessage("Hata kopyalanamadı.");
    }
  };
  const clearHistory = async () => {
    const accepted = await confirm({
      title: "Süreç geçmişi temizlensin mi?",
      message: "Tamamlanmış, başarısız, iptal edilmiş ve kesintiye uğramış süreç kayıtları gizlenecek. Aktif süreçler korunacak.",
      confirmLabel: "Geçmişi temizle",
      danger: true,
    });
    if (!accepted) return;
    setClearingHistory(true);
    try {
      await apiClient.clearWorkflowHistory();
      await refresh();
      setSelectedId(null);
    } catch {
      setError("Süreç geçmişi temizlenemedi.");
    } finally {
      setClearingHistory(false);
    }
  };
  const historicalCount = runs.filter((run) => terminalStates.has(run.state)).length;
  return (
    <div className="grid gap-4">
      <AInfoPanel title="Kalıcı süreçler">
        Bu ekran sayfa değiştirildiğinde de çalışan işler için SQLite durumunu
        yeniden yükler. Canlı olay akışı bağlantı kesilirse son durum geri
        alınır.
      </AInfoPanel>
      {error && <p role="alert">{error}</p>}
      <div className="flex flex-wrap items-center justify-between gap-2 rounded border border-[var(--cortex-line)] px-3 py-2 text-sm">
        <p className="m-0" role="status">
          {streamStatus === "live" ? "Canlı bağlantı açık" : streamStatus === "connecting" ? "Canlı bağlantı kuruluyor" : streamStatus === "reconnecting" ? "Canlı bağlantı yeniden kuruluyor; kayıtlı durum denetleniyor" : "Aktif süreç yok"}
          {lastSuccessfulRefresh && ` · Son kontrol ${formatCortexTime(lastSuccessfulRefresh, true)}`}
        </p>
        <AButton label="Şimdi yenile" size="small" text onClick={() => void refresh()} />
      </div>
      {!loading && (
        <div className="flex justify-end">
          <AButton
            label="Geçmişi temizle"
            icon="trash"
            severity="danger"
            outlined
            loading={clearingHistory}
            disabled={clearingHistory || historicalCount === 0}
            onClick={() => void clearHistory()}
          />
        </div>
      )}
      {loading && runs.length === 0 ? (
        <ALoading label="Süreçler yükleniyor…" />
      ) : (
      <>
      <ACard title="Canlı iş akışı">
        {selected ? (
          <>
            <p className="mb-3 text-sm">
              {workflowSchema(selected.job_type)?.label ?? selected.job_type} — {selected.state}
              {selected.recovery_state ? ` (${selected.recovery_state})` : ""}
            </p>
            <p className="mb-3 text-xs opacity-70">
              Son durum değişikliği: {formatCortexDateTime(selected.updated_at)}
            </p>
            <p className="mb-3 text-xs opacity-70">
              {workflowSchema(selected.job_type)?.version ?? selected.definition_id} · Canlı durum SQLite ve SSE olaylarıyla şema üzerine işlenir.
            </p>
            {selected.state === "interrupted" && (
              <AInfoPanel title="Kurtarma gerekli">
                Bu iş uygulama yeniden başladığında kesildi. Güvenli
                checkpoint’ten yeniden çalıştırmak için yeniden dene.
              </AInfoPanel>
            )}
            <AFlowCanvas nodes={nodes} edges={edges} nodeTypes={processNodeTypes} height={540} />
            <div className="process-step-details mt-4">
              {displayedSteps.map((step) => (
                <article key={step.id} className={`process-step-detail workflow-${step.state}`}>
                  <div className="process-step-detail__header"><strong>{step.schema.label}</strong><span>{step.state}{step.retry_count ? ` · retry ${step.retry_count}` : ""}</span></div>
                  <p>{step.schema.description}</p>
                  <dl><div><dt>Teknoloji</dt><dd>{step.schema.technology}</dd></div><div><dt>Garanti</dt><dd>{step.schema.guarantee}</dd></div></dl>
                  {step.schema.substeps && (
                    <p className="mt-3 text-xs opacity-70">
                      Alt GraphRAG aşamaları yukarıdaki süreç akışında gösterilir; upstream bunlar için ayrı checkpoint yayınlamaz.
                    </p>
                  )}
                </article>
              ))}
            </div>
          </>
        ) : (
          <p>Henüz süreç yok.</p>
        )}
      </ACard>
      <ACard title="Süreçler">
        <div className="grid gap-2">
          {runs.map((run) => (
            <div
              key={run.id}
              className="flex flex-wrap items-center gap-2 border-b py-2"
            >
              <AButton
                label={run.job_type}
                text
                size="small"
                onClick={() => setSelectedId(run.id)}
              />
              <span>{run.state}</span>
              <span className="text-xs opacity-70">{run.id}</span>
              <AButton
                label="Ayrıntılar"
                size="small"
                text
                onClick={() => void showDetails(run)}
              />
              {(run.state === "queued" || run.state === "failed" || run.state === "interrupted") && (
                <AButton
                  label={run.state === "queued" ? "Yeniden gönder" : "Yeniden dene"}
                  size="small"
                  onClick={() =>
                    void apiClient.retryWorkflow(run.id).then(refresh)
                  }
                />
              )}
              {activeStates.has(run.state) && (
                <AButton
                  label="İptal"
                  size="small"
                  severity="secondary"
                  onClick={() =>
                    void apiClient.cancelWorkflow(run.id).then(refresh)
                  }
                />
              )}
            </div>
          ))}
        </div>
      </ACard>
      <ADialog
        header="Teknik süreç ayrıntıları"
        visible={detailsOpen}
        onHide={() => setDetailsOpen(false)}
      >
        {failedDetails.slice(-1).map((failure) => (
          <section key={failure.id} className="grid gap-3 rounded border border-[var(--cortex-line)] bg-[var(--cortex-primary-soft)] p-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <strong>İşlem hatası</strong>
                <p className="m-0 text-xs opacity-70">Sanitize edilmiş teknik özet</p>
              </div>
              <AButton
                icon="copy"
                text
                rounded
                aria-label="Hatayı kopyala"
                title="Hatayı kopyala"
                onClick={() => void copyFailure(failure.summary)}
              />
            </div>
            <pre className="max-h-96 overflow-auto whitespace-pre-wrap break-words rounded bg-[var(--cortex-panel)] p-3 text-xs leading-5">
              {failure.summary}
            </pre>
          </section>
        ))}
        {copyMessage && <p className="m-0 text-sm opacity-70">{copyMessage}</p>}
        {details.every((event) => event.event_type !== "failed") && (
          <p>Sanitize edilmiş hata ayrıntısı yok.</p>
        )}
      </ADialog>
      </>
      )}
    </div>
  );
}
