import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ACard, AInfo } from "./primitives";
describe("Cortex UI abstractions", () => {
  it("renders card and explanatory information", () => {
    render(
      <ACard title="Başlık">
        <AInfo>Açıklama</AInfo>
      </ACard>,
    );
    expect(screen.getByText("Başlık")).toBeInTheDocument();
    expect(screen.getByText("Açıklama")).toBeInTheDocument();
  });
});
