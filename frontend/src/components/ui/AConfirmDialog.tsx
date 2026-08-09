import type { ReactNode } from "react";
import { AButton } from "./AButton";
import { ADialog } from "./ADialog";

export type AConfirmDialogProps = {
  visible: boolean;
  title: string;
  message: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
};

export function AConfirmDialog({
  visible,
  title,
  message,
  confirmLabel = "Onayla",
  cancelLabel = "Vazgeç",
  danger = false,
  onConfirm,
  onCancel,
}: AConfirmDialogProps) {
  return (
    <ADialog
      className="a-confirm-dialog"
      header={title}
      visible={visible}
      modal
      closable
      onHide={onCancel}
      footer={<div className="a-confirm-dialog__actions"><AButton label={cancelLabel} text onClick={onCancel} /><AButton label={confirmLabel} severity={danger ? "danger" : undefined} onClick={onConfirm} /></div>}
    >
      <p className="a-confirm-dialog__message">{message}</p>
    </ADialog>
  );
}
