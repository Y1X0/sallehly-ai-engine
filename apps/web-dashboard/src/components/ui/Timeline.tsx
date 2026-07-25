import type { ProjectStatus, RejectedStage } from "@/lib/types";

const STEPS: { key: ProjectStatus; label: string }[] = [
  { key: "created", label: "Created" },
  { key: "planning", label: "Planning" },
  { key: "waiting_storyboard_approval", label: "Storyboard" },
  { key: "waiting_render_approval", label: "Render plan" },
  { key: "approved", label: "Approved" },
  { key: "generating", label: "Generating" },
  { key: "completed", label: "Completed" },
  { key: "post_processing", label: "Post-processing" },
  { key: "exported", label: "Exported" },
];

function stepIndex(status: ProjectStatus, rejectedStage: RejectedStage): number {
  if (status === "rejected") {
    return rejectedStage === "render_plan" ? 3 : 2;
  }
  return STEPS.findIndex((step) => step.key === status);
}

interface TimelineProps {
  status: ProjectStatus;
  rejectedStage?: RejectedStage;
}

export function Timeline({ status, rejectedStage = null }: TimelineProps) {
  const failed = status === "failed";
  const currentIndex = failed ? STEPS.length - 2 : stepIndex(status, rejectedStage);

  return (
    <ol className="flex items-center">
      {STEPS.map((step, index) => {
        const isDone = index < currentIndex || (index === currentIndex && status === "completed");
        const isCurrent = index === currentIndex;
        const isFailed = failed && index === currentIndex;
        const isChangesRequested = status === "rejected" && index === currentIndex;

        return (
          <li key={step.key} className="flex flex-1 items-center last:flex-none">
            <div className="flex flex-col items-center gap-1">
              <div
                className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-medium ${
                  isFailed
                    ? "bg-red-600 text-white"
                    : isChangesRequested
                      ? "bg-orange-500 text-white"
                      : isDone
                        ? "bg-zinc-900 text-white dark:bg-zinc-50 dark:text-zinc-900"
                        : isCurrent
                          ? "border-2 border-zinc-900 text-zinc-900 dark:border-zinc-50 dark:text-zinc-50"
                          : "border border-zinc-300 text-zinc-400 dark:border-zinc-700 dark:text-zinc-600"
                }`}
              >
                {isFailed ? "!" : isDone ? "✓" : index + 1}
              </div>
              <span
                className={`text-xs whitespace-nowrap ${
                  isCurrent || isDone ? "text-zinc-900 dark:text-zinc-50" : "text-zinc-400 dark:text-zinc-600"
                }`}
              >
                {step.label}
              </span>
            </div>
            {index < STEPS.length - 1 && (
              <div
                className={`mx-2 h-px flex-1 ${
                  index < currentIndex ? "bg-zinc-900 dark:bg-zinc-50" : "bg-zinc-200 dark:bg-zinc-800"
                }`}
              />
            )}
          </li>
        );
      })}
    </ol>
  );
}
