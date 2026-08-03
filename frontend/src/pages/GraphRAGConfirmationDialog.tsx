import { useState } from "react";
import { AButton, AConfirmDialog, AInfo } from "../ui/primitives";
export function GraphRAGConfirmationDialog() {
  const [visible, setVisible] = useState(false);
  return (
    <>
      <AButton label="Estimate GraphRAG run" onClick={() => setVisible(true)} />
      <AConfirmDialog
        header="Confirm GraphRAG operation"
        visible={visible}
        onHide={() => setVisible(false)}
      >
        <AInfo title="Estimated cost">
          A backend estimate will be shown before expensive runs. Automatic
          GraphRAG updates remain off by default.
        </AInfo>
        <div className="mt-4">
          <AButton label="Close" onClick={() => setVisible(false)} />
        </div>
      </AConfirmDialog>
    </>
  );
}
