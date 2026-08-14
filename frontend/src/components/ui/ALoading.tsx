import { ProgressSpinner } from "primereact/progressspinner";

export function ALoading({ label = "Yükleniyor…" }: { label?: string }) {
  return (
    <div className="a-loading" role="status" aria-label={label}>
      <ProgressSpinner aria-hidden="true" strokeWidth="4" />
      <span>{label}</span>
    </div>
  );
}
