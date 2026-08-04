import { createContext, useContext, useEffect, type ReactNode } from "react";
import { create } from "zustand";
import { persist } from "zustand/middleware";
import laraDarkIndigo from "primereact/resources/themes/lara-dark-indigo/theme.css?url";
import laraDarkTeal from "primereact/resources/themes/lara-dark-teal/theme.css?url";
import laraLightIndigo from "primereact/resources/themes/lara-light-indigo/theme.css?url";
import laraLightTeal from "primereact/resources/themes/lara-light-teal/theme.css?url";
import vivaDark from "primereact/resources/themes/viva-dark/theme.css?url";
import vivaLight from "primereact/resources/themes/viva-light/theme.css?url";

export type ThemeMode = "light" | "dark" | "system";
export type PrimeThemePreset =
  | "lara-light-indigo"
  | "lara-dark-indigo"
  | "lara-light-teal"
  | "lara-dark-teal"
  | "viva-light"
  | "viva-dark";
export type Appearance = {
  mode: ThemeMode;
  preset: PrimeThemePreset;
  primary: string;
  secondary: string;
  surface: "slate" | "zinc";
  radius: "sm" | "md" | "lg";
  density: "compact" | "comfortable";
  fontScale: "sm" | "md" | "lg";
  animations: boolean;
};
const defaults: Appearance = {
  mode: "system",
  preset: "lara-light-indigo",
  primary: "#4f46e5",
  secondary: "#64748b",
  surface: "slate",
  radius: "md",
  density: "comfortable",
  fontScale: "md",
  animations: true,
};
type AppearanceState = Appearance & {
  update: (patch: Partial<Appearance>) => void;
  reset: () => void;
};
export const primeThemePresets: Record<PrimeThemePreset, string> = {
  "lara-light-indigo": laraLightIndigo,
  "lara-dark-indigo": laraDarkIndigo,
  "lara-light-teal": laraLightTeal,
  "lara-dark-teal": laraDarkTeal,
  "viva-light": vivaLight,
  "viva-dark": vivaDark,
};
export const useAppearanceStore = create<AppearanceState>()(
  persist(
    (set) => ({
      ...defaults,
      update: (patch) => set(patch),
      reset: () => set(defaults),
    }),
    { name: "cortex-appearance", partialize: (state) => ({ ...defaults, ...state }) },
  ),
);
const AppearanceContext = createContext<AppearanceState | null>(null);
function resolvedTheme(mode: ThemeMode): "light" | "dark" {
  return mode === "system"
    ? window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light"
    : mode;
}
export function AppearanceProvider({ children }: { children: ReactNode }) {
  const state = useAppearanceStore();
  useEffect(() => {
    const root = document.documentElement;
    let themeLink = document.getElementById("cortex-prime-theme") as HTMLLinkElement | null;
    if (!themeLink) {
      themeLink = document.createElement("link");
      themeLink.id = "cortex-prime-theme";
      themeLink.rel = "stylesheet";
      document.head.append(themeLink);
    }
    themeLink.href = primeThemePresets[state.preset];
    root.dataset.theme = resolvedTheme(state.mode);
    root.style.setProperty("--cortex-primary", state.primary);
    root.style.setProperty("--cortex-secondary", state.secondary);
    root.style.setProperty("--primary-color", state.primary);
    root.style.setProperty("--primary-color-text", "#ffffff");
    root.style.setProperty("--secondary-color", state.secondary);
    root.style.setProperty("--secondary-color-text", "#ffffff");
    root.style.setProperty(
      "--cortex-surface",
      state.surface === "slate" ? "#f8fafc" : "#fafafa",
    );
    root.style.setProperty(
      "--cortex-radius",
      { sm: "0.25rem", md: "0.5rem", lg: "0.75rem" }[state.radius],
    );
    root.style.fontSize = { sm: "14px", md: "16px", lg: "18px" }[
      state.fontScale
    ];
    root.dataset.density = state.density;
    root.dataset.animations = String(state.animations);
  }, [state]);
  return (
    <AppearanceContext.Provider value={state}>
      {children}
    </AppearanceContext.Provider>
  );
}
export function useAppearance() {
  const state = useContext(AppearanceContext);
  if (!state) throw new Error("AppearanceProvider is required");
  return state;
}
