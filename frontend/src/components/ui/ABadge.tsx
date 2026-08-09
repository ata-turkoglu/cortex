import type { ReactNode } from "react";

export type ABadgeTone = "info" | "success" | "warning" | "danger" | "secondary";

export function ABadge({
  value,
  severity = "info",
}: {
  value: ReactNode;
  severity?: ABadgeTone;
}) {
  return (
    <span className={`cortex-badge cortex-badge--${severity}`}>
      {value}
    </span>
  );
}
