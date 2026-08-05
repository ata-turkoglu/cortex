import { useCallback, useEffect, useState } from "react";
import { apiClient, type WorkflowRun } from "../api/client";
import { AButton, ACard, ADialog, AInfo } from "../components/ui";

const recoverableStates = new Set(["failed", "interrupted"]);

export function FailedJobsPage() {
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [selected, setSelected] = useState<WorkflowRun | null>(null);
  const [details, setDetails] = useState("");
  const [error, setError] = useState("");
  const refresh = useCallback(async () => {
    try {
      setRuns((await apiClient.listWorkflows()).filter((run) => recoverableStates.has(run.state)));
      setError("");
    } catch { setError("Başarısız işler alınamadı."); }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  const showDetails = async (run: WorkflowRun) => {
    setSelected(run);
    try {
      const events = await apiClient.workflowEventHistory(run.id);
      setDetails(events.filter((event) => event.event_type === "failed").map((event) => event.payload_json).filter(Boolean).join("\n\n") || "Sanitize edilmiş teknik ayrıntı yok.");
    } catch { setDetails("Teknik ayrıntılar alınamadı."); }
  };
  return <div className="page-stack">
    <section className="page-hero compact"><div><p className="eyebrow">Kurtarma merkezi</p><h1>Başarısız işler</h1><p>Yalnızca güvenli checkpoint’ten sürdürülebilen işler listelenir.</p></div><AButton label="Yenile" severity="secondary" onClick={() => void refresh()} /></section>
    {error && <p role="alert">{error}</p>}
    <ACard title="Kurtarılabilir işler">{runs.length ? <div className="document-table">{runs.map((run) => <div key={run.id}><div><strong>{run.job_type}</strong><span>{run.recovery_state || run.state} · {new Date(run.updated_at).toLocaleString("tr-TR")}</span></div><div className="flex gap-2"><AButton label="Ayrıntı" text onClick={() => void showDetails(run)} /><AButton label="Yeniden dene" onClick={() => void apiClient.retryWorkflow(run.id).then(refresh)} /></div></div>)}</div> : <AInfo title="Kurtarma gerektiren iş yok">Başarısız veya kesintiye uğramış süreç bulunmuyor.</AInfo>}</ACard>
    <ADialog header="Teknik süreç ayrıntıları" visible={Boolean(selected)} onHide={() => setSelected(null)}><pre className="document-preview">{details}</pre></ADialog>
  </div>;
}
