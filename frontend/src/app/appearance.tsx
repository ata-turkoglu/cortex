import { createContext, useContext, useEffect, type ReactNode } from "react";
import { create } from "zustand";
export type ThemeMode = "light" | "dark" | "system";
export type Appearance = { mode: ThemeMode; primary: string; surface: "slate" | "zinc"; radius: "sm" | "md" | "lg"; density: "compact" | "comfortable"; fontScale: "sm" | "md" | "lg"; animations: boolean };
const defaults: Appearance = { mode: "system", primary: "#4f46e5", surface: "slate", radius: "md", density: "comfortable", fontScale: "md", animations: true };
type AppearanceState = Appearance & { update: (patch: Partial<Appearance>) => void };
export const useAppearanceStore = create<AppearanceState>((set) => ({ ...defaults, update: (patch) => set(patch) }));
const AppearanceContext = createContext<AppearanceState | null>(null);
function resolvedTheme(mode: ThemeMode): "light" | "dark" { return mode === "system" ? (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light") : mode; }
export function AppearanceProvider({ children }: { children: ReactNode }) { const state = useAppearanceStore(); useEffect(() => { const root = document.documentElement; root.dataset.theme = resolvedTheme(state.mode); root.style.setProperty("--cortex-primary", state.primary); root.style.setProperty("--cortex-surface", state.surface === "slate" ? "#f8fafc" : "#fafafa"); root.style.setProperty("--cortex-radius", { sm: "0.25rem", md: "0.5rem", lg: "0.75rem" }[state.radius]); root.style.fontSize = { sm: "14px", md: "16px", lg: "18px" }[state.fontScale]; root.dataset.density = state.density; root.dataset.animations = String(state.animations); }, [state]); return <AppearanceContext.Provider value={state}>{children}</AppearanceContext.Provider>; }
export function useAppearance() { const state = useContext(AppearanceContext); if (!state) throw new Error("AppearanceProvider is required"); return state; }
