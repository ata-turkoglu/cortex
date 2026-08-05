import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { AppearanceProvider, useAppearance, useAppearanceStore } from "./appearance";
import { AButton } from "../components/ui";
function Probe() {
  const appearance = useAppearance();
  return (
    <AButton
      label="dark"
      onClick={() =>
        appearance.update({
          mode: "dark",
          preset: "viva-dark",
          primary: "#112233",
          secondary: "#445566",
        })
      }
    />
  );
}
describe("appearance", () => {
  afterEach(() => {
    localStorage.clear();
    useAppearanceStore.getState().reset();
    document.getElementById("cortex-prime-theme")?.remove();
  });
  it("applies selected theme", async () => {
    render(
      <AppearanceProvider>
        <Probe />
      </AppearanceProvider>,
    );
    fireEvent.click(screen.getByRole("button"));
    await waitFor(() =>
      expect(document.documentElement.dataset.theme).toBe("dark"),
    );
    expect(document.documentElement.style.getPropertyValue("--cortex-primary")).toBe("#112233");
    expect(document.documentElement.style.getPropertyValue("--cortex-secondary")).toBe("#445566");
    expect(document.getElementById("cortex-prime-theme")).toHaveAttribute("href", expect.stringContaining("theme.css"));
    expect(localStorage.getItem("cortex-appearance")).toContain("viva-dark");
  });
});
