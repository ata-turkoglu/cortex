import { create } from "zustand";
import type { WorkflowRun } from "../api/client";

export type ActiveJob = { id: string; label: string; progress?: number };
type JobsState = {
  jobs: ActiveJob[];
  workflowRuns: WorkflowRun[];
  setJobs: (jobs: ActiveJob[]) => void;
  setWorkflowRuns: (runs: WorkflowRun[]) => void;
};
export const useJobsStore = create<JobsState>((set) => ({
  jobs: [],
  workflowRuns: [],
  setJobs: (jobs) => set({ jobs }),
  setWorkflowRuns: (workflowRuns) => set({ workflowRuns }),
}));
