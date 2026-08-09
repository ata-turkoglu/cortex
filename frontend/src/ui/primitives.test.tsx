import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ACard, AInfo, AInfoPanel } from "../components/ui";
describe("Cortex UI abstractions", () => {
  it("renders card and explanatory information", () => {
    render(
      <ACard title="Başlık">
        <AInfoPanel>Açıklama</AInfoPanel>
      </ACard>,
    );
    expect(screen.getByText("Başlık")).toBeInTheDocument();
    expect(screen.getByText("Açıklama")).toBeInTheDocument();
  });

  it("renders accessible tooltip information", () => {
    render(<AInfo description="Katmanın ne yaptığını gösterir." />);
    expect(screen.getByRole("button", { name: "Katmanın ne yaptığını gösterir." })).toBeInTheDocument();
  });
});
