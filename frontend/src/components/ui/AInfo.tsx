import { Tooltip } from "primereact/tooltip";
import type { ReactNode } from "react";
import { useId } from "react";
import { AIcon } from "../../icons/AIcon";

type AInfoProps = {
  description: string;
  className?: string;
  position?: "top" | "bottom" | "left" | "right";
};

/** A compact information icon with an accessible hover and focus tooltip. */
export function AInfo({ description, className, position = "top" }: AInfoProps) {
  const tooltipTargetClass = `a-info-tooltip-${useId().replace(/:/g, "")}`;

  return (
    <>
      <button
        type="button"
        className={["a-info", tooltipTargetClass, className].filter(Boolean).join(" ")}
        aria-label={description}
      >
        <AIcon name="help" size={16} />
      </button>
      <Tooltip target={`.${tooltipTargetClass}`} content={description} position={position} />
    </>
  );
}

/** A persistent inline information panel retained for notices and empty states. */
export function AInfoPanel({ title = "Bilgi", children }: { title?: string; children: ReactNode }) {
  return <aside className="cortex-info"><strong>{title}</strong><div>{children}</div></aside>;
}
