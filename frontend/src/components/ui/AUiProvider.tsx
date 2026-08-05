import { PrimeReactProvider } from "primereact/api";
import type { ReactNode } from "react";
export function AUiProvider({ children }: { children: ReactNode }) { return <PrimeReactProvider value={{ ripple: true }}>{children}</PrimeReactProvider>; }
