import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "../api/client";
import { ASystemMap } from "./ASystemMap";

describe("ASystemMap", () => {
  afterEach(() => vi.restoreAllMocks());
  it("renders live health and recovery nodes", async () => {
    vi.spyOn(apiClient, "getHealth").mockResolvedValue({ status: "healthy", services: { backend: "healthy", worker: "healthy" } });
    vi.spyOn(apiClient, "diagnostics").mockResolvedValue({ windows: { data_path: "D:\\Cortex", ollama_base_url: "http://localhost" }, workflows: { interrupted: 0, failed: 0, repairing: 0 }, reconciliation: { state: "idle", message: "idle" } });
    render(<ASystemMap />);
    await waitFor(() => expect(screen.getByText(/backend · healthy/)).toBeInTheDocument());
    expect(screen.getByText(/recovery · healthy/)).toBeInTheDocument();
  });
});
