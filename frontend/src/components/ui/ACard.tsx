import type { ReactNode } from "react";
export const ACard = ({ title, children }: { title?: string; children: ReactNode }) => <section className="cortex-card">{title && <h2 className="cortex-card__title">{title}</h2>}{children}</section>;
