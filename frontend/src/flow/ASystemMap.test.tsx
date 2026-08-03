import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ASystemMap } from "./ASystemMap";
describe("ASystemMap", () => {
  it("exposes the architecture nodes", () => {
    render(<ASystemMap />);
    expect(screen.getByText("Frontend")).toBeInTheDocument();
    expect(screen.getByText("Backend API")).toBeInTheDocument();
  });
});
