import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AppearanceProvider, useAppearance } from "./appearance";
function Probe() { const appearance = useAppearance(); return <button onClick={() => appearance.update({ mode: "dark" })}>dark</button>; }
describe("appearance", () => { it("applies selected theme", async () => { render(<AppearanceProvider><Probe /></AppearanceProvider>); fireEvent.click(screen.getByRole("button")); await waitFor(() => expect(document.documentElement.dataset.theme).toBe("dark")); }); });
