import type { HTMLAttributes, ReactNode } from "react";
import { cx } from "./classNames";

export const ATabs = ({ children, className, ...props }: HTMLAttributes<HTMLDivElement> & { children: ReactNode }) => (
  <div role="tablist" className={cx("a-tabs", className)} {...props}>{children}</div>
);
