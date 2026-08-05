import type { ReactNode } from "react";
export const AInfo = ({ title = "Bilgi", children }: { title?: string; children: ReactNode }) => <aside className="cortex-info"><strong>{title}</strong><div>{children}</div></aside>;
