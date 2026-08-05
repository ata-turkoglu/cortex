import type { ActiveJob } from "../app/jobs";
import { ADialog, AProgress } from "../components/ui";
export function AWorkflowDialog({
  jobs,
  visible,
  onHide,
}: {
  jobs: ActiveJob[];
  visible: boolean;
  onHide: () => void;
}) {
  return (
    <ADialog
      header="Active processes"
      visible={visible}
      onHide={onHide}
      style={{ width: "min(42rem, 96vw)" }}
    >
      {jobs.length ? (
        jobs.map((job) => (
          <div key={job.id} className="mb-4">
            <div className="mb-1 flex justify-between text-sm">
              <span>{job.label}</span>
              <span>{job.progress ?? 0}%</span>
            </div>
            <AProgress value={job.progress ?? 0} />
          </div>
        ))
      ) : (
        <p>No active background jobs.</p>
      )}
    </ADialog>
  );
}
