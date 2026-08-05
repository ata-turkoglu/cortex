import type { LabelHTMLAttributes } from "react";
import { cx } from "./classNames";

export function ALabel({ className, ...props }: LabelHTMLAttributes<HTMLLabelElement>) {
  return <label {...props} className={cx("a-label grid gap-1", className)} />;
}
