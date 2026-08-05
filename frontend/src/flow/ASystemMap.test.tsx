import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "../api/client";
import { ASystemMap } from "./ASystemMap";

describe("ASystemMap", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders live health and switches detailed map tabs", async () => {
    vi.spyOn(apiClient, "getHealth").mockResolvedValue({
      status: "healthy",
      services: { backend: "healthy", worker: "healthy" },
    });
    vi.spyOn(apiClient, "diagnostics").mockResolvedValue({
      windows: { data_path: "D:\\Cortex", ollama_base_url: "http://localhost" },
      workflows: { interrupted: 0, failed: 0, repairing: 0 },
      reconciliation: { state: "idle", message: "idle" },
    });
    render(<ASystemMap />);
    await waitFor(() => expect(screen.getAllByText(/backend/).length).toBeGreaterThan(0));
    await waitFor(() => expect(screen.getAllByText(/recovery/).length).toBeGreaterThan(0));
    fireEvent.click(screen.getByRole("tab", { name: "Belge akışı" }));
    expect(screen.getByText("Docling normalizasyonu")).toBeInTheDocument();
    expect(screen.getByText("Sürüm kararı")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Sorgu akışı" }));
    expect(screen.getAllByText("Dense retrieval").length).toBeGreaterThan(0);
    expect(screen.getByText("Graph DRIFT")).toBeInTheDocument();
  });
});
