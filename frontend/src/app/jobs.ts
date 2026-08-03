import { create } from "zustand";
export type ActiveJob = { id: string; label: string; progress?: number };
type JobsState = { jobs: ActiveJob[]; setJobs: (jobs: ActiveJob[]) => void };
export const useJobsStore = create<JobsState>((set) => ({
  jobs: [],
  setJobs: (jobs) => set({ jobs }),
}));
