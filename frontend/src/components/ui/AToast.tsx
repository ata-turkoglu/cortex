import { Toast } from "primereact/toast";
import type { ToastMessage } from "primereact/toast";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  Component,
  type ReactNode,
} from "react";

export type ToastSeverity = "success" | "info" | "warn" | "error";

export type ToastOptions = {
  severity?: ToastSeverity;
  summary: string;
  detail?: string;
  life?: number;
};

export type ToastActions = {
  show: (options: ToastOptions) => void;
  success: (summary: string, detail?: string) => void;
  info: (summary: string, detail?: string) => void;
  warning: (summary: string, detail?: string) => void;
  error: (summary: string, detail?: string) => void;
};

let activeToast: ToastActions | undefined;

export function sanitizeToastDetail(reason: unknown) {
  const detail = reason instanceof Error ? reason.message : typeof reason === "string" ? reason : "Beklenmeyen bir hata oluştu.";
  return detail
    .replace(/sk-[A-Za-z0-9_-]+/g, "[gizli değer]")
    .replace(/((?:api|access|secret)[_-]?key\s*[=:]\s*)\S+/gi, "$1[gizli değer]");
}

/**
 * Imperative notification boundary for non-React callers such as the API client.
 * Feature components should prefer useToast().
 */
export const toast: ToastActions = {
  show: (options) => activeToast?.show(options),
  success: (summary, detail) => activeToast?.success(summary, detail),
  info: (summary, detail) => activeToast?.info(summary, detail),
  warning: (summary, detail) => activeToast?.warning(summary, detail),
  error: (summary, detail) => activeToast?.error(summary, detail),
};

const ToastContext = createContext<ToastActions | undefined>(undefined);

export function AToastProvider({ children }: { children: ReactNode }) {
  const ref = useRef<Toast>(null);
  const recentErrors = useRef(new Map<string, number>());
  const show = useCallback((options: ToastOptions) => {
    const key = `${options.severity ?? "info"}:${options.summary}:${options.detail ?? ""}`;
    const now = Date.now();
    if (options.severity === "error" && now - (recentErrors.current.get(key) ?? 0) < 3_000) return;
    if (options.severity === "error") recentErrors.current.set(key, now);
    const message: ToastMessage = {
      severity: options.severity ?? "info",
      summary: options.summary,
      detail: options.detail,
      life: options.life ?? (options.severity === "error" ? 7000 : 4500),
    };
    ref.current?.show(message);
  }, []);
  const actions = useMemo<ToastActions>(
    () => ({
      show,
      success: (summary, detail) => show({ severity: "success", summary, detail }),
      info: (summary, detail) => show({ severity: "info", summary, detail }),
      warning: (summary, detail) => show({ severity: "warn", summary, detail }),
      error: (summary, detail) => show({ severity: "error", summary, detail }),
    }),
    [show],
  );

  useEffect(() => {
    activeToast = actions;
    return () => {
      if (activeToast === actions) activeToast = undefined;
    };
  }, [actions]);

  useEffect(() => {
    const handleError = (event: ErrorEvent) => {
      actions.error("Beklenmeyen hata.", sanitizeToastDetail(event.error ?? event.message));
    };
    const handleUnhandledRejection = (event: PromiseRejectionEvent) => {
      actions.error("İşlem tamamlanamadı.", sanitizeToastDetail(event.reason));
    };
    window.addEventListener("error", handleError);
    window.addEventListener("unhandledrejection", handleUnhandledRejection);
    return () => {
      window.removeEventListener("error", handleError);
      window.removeEventListener("unhandledrejection", handleUnhandledRejection);
    };
  }, [actions]);

  return (
    <ToastContext.Provider value={actions}>
      {children}
      <Toast ref={ref} position="top-right" />
    </ToastContext.Provider>
  );
}

export function useToast() {
  const value = useContext(ToastContext);
  if (!value) throw new Error("useToast must be used within AToastProvider");
  return value;
}

type ErrorBoundaryState = { failed: boolean };

/** Keeps an unexpected render failure visible and reports it through AToast. */
export class AErrorBoundary extends Component<{ children: ReactNode }, ErrorBoundaryState> {
  state: ErrorBoundaryState = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: Error) {
    toast.error("Sayfa yüklenemedi.", sanitizeToastDetail(error));
  }

  render() {
    if (this.state.failed) {
      return <div role="alert">Beklenmeyen bir hata oluştu. Sayfayı yenileyip yeniden deneyin.</div>;
    }
    return this.props.children;
  }
}
