import type { ReactNode } from "react";
import { AProgress } from "../components/ui";
import { AIcon } from "../icons/AIcon";
export const ASidebar = ({ children }: { children: ReactNode }) => (
  <aside className="cortex-sidebar">{children}</aside>
);
export const AHeader = ({ children }: { children: ReactNode }) => (
  <header className="cortex-header">{children}</header>
);
export const APageContent = ({ children }: { children: ReactNode }) => (
  <div className="cortex-content">{children}</div>
);
export function AGlobalProgress({
  active,
  value,
}: {
  active: boolean;
  value?: number;
}) {
  return (
    <>
      <div className="activity-bar" data-active={active} />
      {active && value !== undefined && (
        <AProgress
          value={value}
          showValue={false}
          style={{ width: 96, height: 6 }}
        />
      )}
    </>
  );
}
export function ASystemHealth({ healthy = true }: { healthy?: boolean }) {
  return (
    <span
      title={healthy ? "System healthy" : "System requires attention"}
      className="cortex-system-health"
      data-state={healthy ? "healthy" : "attention"}
    >
      <AIcon name="health" size={17} />
      {healthy ? "Healthy" : "Attention"}
    </span>
  );
}
