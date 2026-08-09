import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { AConfirmDialog } from "./AConfirmDialog";

export type ConfirmationOptions = {
  title: string;
  message: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
};

type PendingConfirmation = ConfirmationOptions & { resolve: (accepted: boolean) => void };

const ConfirmationContext = createContext<((options: ConfirmationOptions) => Promise<boolean>) | undefined>(undefined);

export function AConfirmationProvider({ children }: { children: ReactNode }) {
  const [pending, setPending] = useState<PendingConfirmation>();
  const confirm = useCallback((options: ConfirmationOptions) => new Promise<boolean>((resolve) => {
    setPending({ ...options, resolve });
  }), []);
  const settle = useCallback((accepted: boolean) => {
    if (!pending) return;
    pending.resolve(accepted);
    setPending(undefined);
  }, [pending]);

  return (
    <ConfirmationContext.Provider value={confirm}>
      {children}
      <AConfirmDialog
        visible={Boolean(pending)}
        title={pending?.title ?? "Onay gerekli"}
        message={pending?.message ?? ""}
        confirmLabel={pending?.confirmLabel}
        cancelLabel={pending?.cancelLabel}
        danger={pending?.danger}
        onConfirm={() => settle(true)}
        onCancel={() => settle(false)}
      />
    </ConfirmationContext.Provider>
  );
}

export function useConfirmation() {
  const confirm = useContext(ConfirmationContext);
  if (!confirm) throw new Error("useConfirmation must be used within AConfirmationProvider");
  return confirm;
}
