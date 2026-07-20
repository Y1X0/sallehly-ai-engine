import type { JobStatusSummary } from "@/lib/types";
import { Button, Card, ProgressBar, StatusBadge } from "@/components/ui";

interface JobsPanelProps {
  jobs: JobStatusSummary[];
  showRetry: boolean;
  onRetry: () => void;
  retrying: boolean;
}

export function JobsPanel({ jobs, showRetry, onRetry, retrying }: JobsPanelProps) {
  return (
    <Card
      title="Generation jobs"
      actions={
        showRetry ? (
          <Button size="sm" variant="danger" onClick={onRetry} loading={retrying}>
            Retry failed generation
          </Button>
        ) : undefined
      }
    >
      <div className="space-y-3">
        {jobs.map((job) => (
          <div key={job.job_id}>
            <div className="mb-1 flex items-center justify-between">
              <span className="text-xs text-zinc-500 dark:text-zinc-400">{job.job_id}</span>
              <StatusBadge status={job.status} />
            </div>
            {(job.status === "queued" || job.status === "running") && <ProgressBar />}
            {job.status === "completed" && <ProgressBar percent={100} />}
            {job.error_message && (
              <p className="mt-1 text-xs text-red-600 dark:text-red-400">{job.error_message}</p>
            )}
            {job.retry_count > 0 && (
              <p className="mt-1 text-xs text-zinc-400">retried {job.retry_count} time(s)</p>
            )}
          </div>
        ))}
      </div>
    </Card>
  );
}
