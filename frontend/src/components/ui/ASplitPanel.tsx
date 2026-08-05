import type { ReactNode } from "react";
export const ASplitPanel = ({ children }: { children: ReactNode }) => <div className="grid gap-4 lg:grid-cols-2">{children}</div>;
