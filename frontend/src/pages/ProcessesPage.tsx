import { useCallback, useEffect, useMemo, useState } from "react";
import { apiClient, type WorkflowEvent, type WorkflowRun } from "../api/client";
import { useJobsStore } from "../app/jobs";
import {
  AFlowCanvas,
  type AFlowEdge,
  type AFlowNode,
} from "../flow/AFlowCanvas";
import { AButton, ACard, ADialog, AInfo } from "../ui/primitives";

const activeStates = new Set(["queued", "running", "cancelling"]);
export function ProcessesPage() {
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [details, setDetails] = useState<WorkflowEvent[]>([]);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const setJobs = useJobsStore((state) => state.setJobs);
  const refresh = useCallback(async () => {
    try {
      const next = await apiClient.listWorkflows();
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
      setError(null);
    } catch {
      setError("Süreç durumu alınamadı.");
    }
  }, [setJobs]);
  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 5000);
    return () => window.clearInterval(timer);
  }, [refresh]);
  useEffect(() => {
    const streams = runs
      .filter((run) => activeStates.has(run.state))
      .map((run) => {
        const stream = apiClient.workflowEvents(run.id);
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
  }, [refresh, runs]);
  const selected = runs.find((run) => run.id === selectedId) ?? runs[0];
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
                width: Math.max(selected.steps.length * 180, 260),
                height: 220,
              },
            } as AFlowNode,
            ...selected.steps.map(
              (step, index): AFlowNode => ({
                id: step.id,
                parentId: "workflow-group",
                extent: "parent",
                position: { x: 20 + index * 160, y: 70 },
                data: { label: `${step.step_name} · ${step.state}` },
                className: `workflow-${step.state}`,
              }),
            ),
          ]
        : [],
      edges:
        selected?.steps
          .slice(1)
          .map(
            (step, index): AFlowEdge => ({
              id: `${index}`,
              source: selected.steps[index].id,
              target: step.id,
            }),
          ) ?? [],
    }),
    [selected],
  );
  const showDetails = async (run: WorkflowRun) => {
    setSelectedId(run.id);
    setDetails(await apiClient.workflowEventHistory(run.id));
    setDetailsOpen(true);
  };
  return (
    <div className="grid gap-4">
      <AInfo title="Kalıcı süreçler">
        Bu ekran sayfa değiştirildiğinde de çalışan işler için SQLite durumunu
        yeniden yükler. Canlı olay akışı bağlantı kesilirse son durum geri
        alınır.
      </AInfo>
      {error && <p role="alert">{error}</p>}
      <ACard title="Canlı iş akışı">
        {selected ? (
          <>
            <p className="mb-3 text-sm">
              {selected.job_type} — {selected.state}
              {selected.recovery_state ? ` (${selected.recovery_state})` : ""}
            </p>
            {selected.state === "interrupted" && (
              <AInfo title="Kurtarma gerekli">
                Bu iş uygulama yeniden başladığında kesildi. Güvenli
                checkpoint’ten yeniden çalıştırmak için yeniden dene.
              </AInfo>
            )}
            <AFlowCanvas nodes={nodes} edges={edges} />
            <div className="mt-3 text-sm">
              {selected.steps.map((step) => (
                <div key={step.id}>
                  {step.step_name}: {step.state}
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
        {details
          .filter((event) => event.event_type === "failed")
          .map((event) => (
            <pre key={event.id} className="whitespace-pre-wrap text-xs">
              {event.payload_json}
            </pre>
          ))}
        {details.every((event) => event.event_type !== "failed") && (
          <p>Sanitize edilmiş hata ayrıntısı yok.</p>
        )}
      </ADialog>
    </div>
  );
}
