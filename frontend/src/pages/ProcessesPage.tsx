import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiClient, type WorkflowEvent, type WorkflowRun } from "../api/client";
import { useJobsStore } from "../app/jobs";
import {
  AFlowCanvas,
  type AFlowEdge,
  type AFlowNode,
} from "../flow/AFlowCanvas";
import { AButton, ACard, ADialog, AInfoPanel } from "../components/ui";

const activeStates = new Set(["queued", "running", "cancelling"]);

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

const workflowSchemas: Record<string, { label: string; steps: string[] }> = {
  ingestion: {
    label: "Belge ingestion",
    steps: ["parse", "normalize", "logical_documents", "chunk", "index"],
  },
  dense_reindex: {
    label: "Dense embedding reindex",
    steps: ["clear_active_vectors", "embed", "upsert", "activate"],
  },
  graphrag_reindex: {
    label: "GraphRAG reindex",
    steps: ["snapshot", "materialize", "index", "mirror"],
  },
  document_delete: {
    label: "Belge silme",
    steps: ["mark", "cleanup", "reconcile"],
  },
  workspace_delete: {
    label: "Workspace silme",
    steps: ["mark", "cleanup", "reconcile"],
  },
  reconcile: { label: "Orphan uzlaştırma", steps: ["scan", "repair"] },
};

function displayStepName(step: string) {
  return step.replaceAll("_", " ");
}
export function ProcessesPage() {
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [details, setDetails] = useState<WorkflowEvent[]>([]);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [copyMessage, setCopyMessage] = useState<string | null>(null);
  const refreshInFlight = useRef(false);
  const setJobs = useJobsStore((state) => state.setJobs);
  const refresh = useCallback(async () => {
    if (refreshInFlight.current) return;
    refreshInFlight.current = true;
    try {
      const next = await apiClient.listWorkflows();
      setRuns((current) => (sameWorkflowRuns(current, next) ? current : next));
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
      setError(null);
    } catch {
      setError("Süreç durumu alınamadı.");
    } finally {
      refreshInFlight.current = false;
    }
  }, [setJobs]);
  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 5000);
    return () => window.clearInterval(timer);
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
    const streams = activeRunIds
      .split(",")
      .filter(Boolean)
      .map((runId) => {
        const stream = apiClient.workflowEvents(runId);
        stream.onmessage = () => void refresh();
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
          stream.addEventListener(eventType, () => void refresh());
        return stream;
      });
    return () => streams.forEach((stream) => stream.close());
  }, [activeRunIds, refresh]);
  const selected = runs.find((run) => run.id === selectedId) ?? runs[0];
  const displayedSteps = useMemo(() => {
    if (!selected) return [];
    const persisted = new Map(
      selected.steps.map((step) => [step.step_name, step]),
    );
    const stepNames =
      workflowSchemas[selected.job_type]?.steps ??
      selected.steps.map((step) => step.step_name);
    return stepNames.map(
      (stepName) =>
        persisted.get(stepName) ?? {
          id: `schema-${selected.id}-${stepName}`,
          step_name: stepName,
          state: "pending",
          retry_count: 0,
          checkpoint_json: null,
        },
    );
  }, [selected]);
  const { nodes, edges } = useMemo(
    () => ({
      nodes: selected
        ? [
            {
              id: "workflow-group",
              type: "group",
              position: { x: 0, y: 0 },
              data: { label: selected.job_type },
              style: {
                width: Math.max(displayedSteps.length * 180, 260),
                height: 220,
                zIndex: 0,
              },
            } as AFlowNode,
            ...displayedSteps.map(
              (step, index): AFlowNode => ({
                id: step.id,
                parentId: "workflow-group",
                extent: "parent",
                position: { x: 20 + index * 160, y: 70 },
                data: { label: `${step.step_name} · ${step.state}` },
                className: `workflow-${step.state}`,
                style: { width: 150, zIndex: 1 },
              }),
            ),
          ]
        : [],
      edges:
        displayedSteps.slice(1).map(
          (step, index): AFlowEdge => ({
            id: `${index}`,
            source: displayedSteps[index].id,
            target: step.id,
          }),
        ) ?? [],
    }),
    [displayedSteps, selected],
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
  return (
    <div className="grid gap-4">
      <AInfoPanel title="Kalıcı süreçler">
        Bu ekran sayfa değiştirildiğinde de çalışan işler için SQLite durumunu
        yeniden yükler. Canlı olay akışı bağlantı kesilirse son durum geri
        alınır.
      </AInfoPanel>
      {error && <p role="alert">{error}</p>}
      <ACard title="Canlı iş akışı">
        {selected ? (
          <>
            <p className="mb-3 text-sm">
              {selected.job_type} — {selected.state}
              {selected.recovery_state ? ` (${selected.recovery_state})` : ""}
            </p>
            {selected.state === "interrupted" && (
              <AInfoPanel title="Kurtarma gerekli">
                Bu iş uygulama yeniden başladığında kesildi. Güvenli
                checkpoint’ten yeniden çalıştırmak için yeniden dene.
              </AInfoPanel>
            )}
            <AFlowCanvas nodes={nodes} edges={edges} />
            <div className="mt-3 text-sm">
              {displayedSteps.map((step) => (
                <div key={step.id}>
                  {displayStepName(step.step_name)}: {step.state}
                  {step.retry_count ? ` · retry ${step.retry_count}` : ""}
                </div>
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
              {(run.state === "failed" || run.state === "interrupted") && (
                <AButton
                  label="Yeniden dene"
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
    </div>
  );
}
