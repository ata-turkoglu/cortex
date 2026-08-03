import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "../api/client";
import { useJobsStore } from "../app/jobs";
import { APlatformLayout } from "./APlatformLayout";

const activeRun = {
  id: "run-1",
  workspace_id: "workspace-1",
  definition_id: "ingestion",
  job_type: "ingestion",
  state: "running",
  recovery_state: null,
  created_at: "2026-08-03T00:00:00Z",
  updated_at: "2026-08-03T00:00:00Z",
  finished_at: null,
  steps: [
    {
      id: "step-1",
      step_name: "parse",
      state: "completed",
      retry_count: 0,
      checkpoint_json: null,
    },
  ],
};

describe("platform workflow progress", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    useJobsStore.getState().setJobs([]);
  });
  it("restores active background work after navigation", async () => {
    vi.spyOn(apiClient, "listWorkflows").mockResolvedValue([activeRun]);
    const first = render(
      <MemoryRouter>
        <APlatformLayout title="First">
          <p>first</p>
        </APlatformLayout>
      </MemoryRouter>,
    );
    await waitFor(() =>
      expect(screen.getByText("1 aktif iş")).toBeInTheDocument(),
    );
    first.unmount();
    render(
      <MemoryRouter>
        <APlatformLayout title="Second">
          <p>second</p>
        </APlatformLayout>
      </MemoryRouter>,
    );
    await waitFor(() =>
      expect(screen.getByText("1 aktif iş")).toBeInTheDocument(),
    );
  });

  it("aggregates a large active-job list without dropping progress indicators", async () => {
    vi.spyOn(apiClient, "listWorkflows").mockResolvedValue(
      Array.from({ length: 120 }, (_, index) => ({
        ...activeRun,
        id: `run-${index}`,
        steps: index % 2 ? activeRun.steps : [],
      })),
    );
    render(
      <MemoryRouter>
        <APlatformLayout title="Busy">
          <p>busy</p>
        </APlatformLayout>
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getAllByText(/120 aktif/).length).toBeGreaterThan(0));
  });
});
