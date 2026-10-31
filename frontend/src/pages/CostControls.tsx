import { useEffect, useState } from "react";
import { apiClient, type BudgetPeriod, type BudgetStatus } from "../api/client";
import { AButton, ACard, AInfoPanel, AInput, ALabel } from "../components/ui";
import { GraphRAGConfirmationDialog } from "./GraphRAGConfirmationDialog";
export function CostControls() {
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [notice, setNotice] = useState("");
  const [status, setStatus] = useState<BudgetStatus>();
  const refreshStatus = () => void apiClient.budgetStatus().then(setStatus).catch(() => setStatus(undefined));
  useEffect(() => {
    void apiClient.getSettings().then((data) => setValues(data.settings));
    refreshStatus();
  }, []);
  const period = (label: string, item: BudgetPeriod) => (
    <p className="text-sm">
      {label}: ${Number(item.spent_usd).toFixed(4)}
      {item.state === "unbounded"
        ? " (no budget set)"
        : ` of $${item.budget_usd} (${item.percent}%)${item.state === "exceeded" ? " — budget exceeded" : item.state === "warning" ? " — warning threshold reached" : ""}`}
      {item.unpriced_calls > 0 && ` · ${item.unpriced_calls} call(s) without a known price`}
    </p>
  );
  const field = (key: string, label: string) => (
    <ALabel className="grid gap-1">
      {label}
      <AInput
        value={String(values[key] ?? 0)}
        onChange={(event) =>
          setValues({ ...values, [key]: Number(event.target.value) })
        }
      />
    </ALabel>
  );
  return (
    <ACard title="Cost controls">
      <AInfoPanel title="Budget warning">
        Soft budgets warn when recorded provider spend reaches the warning
        percentage; they never pause or block work. Spend covers semantic
        planning, knowledge extraction, answer synthesis, conversation summary, and smart GraphRAG
        search calls. GraphRAG stays manual unless
        explicitly configured.
      </AInfoPanel>
      {status && (
        <div className="mt-3 grid gap-1">
          {period("Today", status.daily)}
          {period("This month", status.monthly)}
        </div>
      )}
      <div className="mt-4 grid max-w-xl grid-cols-2 gap-3">
        {field("daily_soft_budget_usd", "Daily soft budget (USD)")}
        {field("monthly_soft_budget_usd", "Monthly soft budget (USD)")}
        {field("budget_warning_percent", "Warning percentage")}
      </div>
      <div className="mt-4 flex gap-3">
        <AButton
          label="Save budgets"
          onClick={() =>
            void apiClient
              .updateSettings(values)
              .then(() => {
                setNotice("Budget controls saved.");
                refreshStatus();
              })
              .catch(() => setNotice("Could not save budgets."))
          }
        />
        <span className="text-sm">{notice}</span>
      </div>
      <div className="mt-4">
        <GraphRAGConfirmationDialog />
      </div>
    </ACard>
  );
}
