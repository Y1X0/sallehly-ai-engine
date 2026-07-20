const STATUS_STYLES: Record<string, string> = {
  created: "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
  planning: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300",
  waiting_storyboard_approval: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  waiting_render_approval: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  approved: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300",
  rejected: "bg-orange-100 text-orange-800 dark:bg-orange-950 dark:text-orange-300",
  queued: "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
  running: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300",
  generating: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300",
  completed: "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-300",
  failed: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300",
};

const STATUS_LABELS: Record<string, string> = {
  created: "Created",
  planning: "Planning",
  waiting_storyboard_approval: "Storyboard review",
  waiting_render_approval: "Render plan review",
  approved: "Approved",
  rejected: "Changes requested",
  queued: "Queued",
  running: "Running",
  generating: "Generating",
  completed: "Completed",
  failed: "Failed",
};

const PULSING_STATUSES = new Set(["planning", "generating", "running", "queued"]);

export function StatusBadge({ status }: { status: string }) {
  const styles = STATUS_STYLES[status] ?? "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300";
  const label = STATUS_LABELS[status] ?? status;

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${styles}`}
    >
      {PULSING_STATUSES.has(status) && (
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" aria-hidden="true" />
      )}
      {label}
    </span>
  );
}
