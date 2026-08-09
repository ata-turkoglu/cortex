import { useEffect, useState } from "react";
import { apiClient } from "../api/client";
import { AButton, ADialog, AInfoPanel } from "../components/ui";
export function GraphRAGConfirmationDialog() {
  const [visible, setVisible] = useState(false);
  const [estimate, setEstimate] = useState<{ update_mode: string; pending_document_threshold: number; confirmation_threshold_usd: number; requires_confirmation: boolean }>();
  useEffect(() => { if (visible) void apiClient.graphragEstimate().then(setEstimate); }, [visible]);
  return <><AButton label="Estimate GraphRAG run" onClick={() => setVisible(true)} /><ADialog header="Confirm GraphRAG operation" visible={visible} onHide={() => setVisible(false)}><AInfoPanel title="Estimated cost">{estimate ? `Mode: ${estimate.update_mode}; pending-document threshold: ${estimate.pending_document_threshold}; confirmation threshold: $${estimate.confirmation_threshold_usd.toFixed(2)}.` : "Loading configured cost controls…"}</AInfoPanel><div className="mt-4"><AButton label="Close" onClick={() => setVisible(false)} /></div></ADialog></>;
}
