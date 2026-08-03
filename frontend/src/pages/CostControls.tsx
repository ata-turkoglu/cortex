import { useEffect, useState } from "react";
import { apiClient } from "../api/client";
import { AButton, ACard, AInfo, AInput } from "../ui/primitives";
import { GraphRAGConfirmationDialog } from "./GraphRAGConfirmationDialog";
export function CostControls() {
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [notice, setNotice] = useState("");
  useEffect(() => { void apiClient.getSettings().then((data) => setValues(data.settings)); }, []);
  const field = (key: string, label: string) => <label className="grid gap-1">{label}<AInput value={String(values[key] ?? 0)} onChange={(event) => setValues({ ...values, [key]: Number(event.target.value) })} /></label>;
  return <ACard title="Cost controls"><AInfo title="Budget warning">Queued cost-incurring work pauses at the daily soft budget. GraphRAG stays manual unless explicitly configured.</AInfo><div className="mt-4 grid max-w-xl grid-cols-2 gap-3">{field("daily_soft_budget_usd", "Daily soft budget (USD)")}{field("monthly_soft_budget_usd", "Monthly soft budget (USD)")}{field("budget_warning_percent", "Warning percentage")}</div><div className="mt-4 flex gap-3"><AButton label="Save budgets" onClick={() => void apiClient.updateSettings(values).then(() => setNotice("Budget controls saved.")).catch(() => setNotice("Could not save budgets."))} /><span className="text-sm">{notice}</span></div><div className="mt-4"><GraphRAGConfirmationDialog /></div></ACard>;
}
