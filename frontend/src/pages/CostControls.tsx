import { ACard, AInfo } from "../ui/primitives";
import { GraphRAGConfirmationDialog } from "./GraphRAGConfirmationDialog";
export function CostControls() {
  return (
    <ACard title="Cost controls">
      <AInfo title="Budget warning">
        GraphRAG is manual by default. Cost-incurring queued work will require
        confirmation when configured thresholds are exceeded.
      </AInfo>
      <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
        <dt>Daily budget</dt>
        <dd>$0.00 / not configured</dd>
        <dt>Monthly budget</dt>
        <dd>$0.00 / not configured</dd>
        <dt>Query expansion</dt>
        <dd>Off</dd>
      </dl>
      <div className="mt-4">
        <GraphRAGConfirmationDialog />
      </div>
    </ACard>
  );
}
