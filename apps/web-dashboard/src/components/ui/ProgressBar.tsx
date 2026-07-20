interface ProgressBarProps {
  /** 0-100. Omit for an indeterminate bar (e.g. a running job with no known percentage). */
  percent?: number;
  label?: string;
}

export function ProgressBar({ percent, label }: ProgressBarProps) {
  const indeterminate = percent === undefined;

  return (
    <div>
      {label && <p className="mb-1 text-xs text-zinc-500 dark:text-zinc-400">{label}</p>}
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800">
        {indeterminate ? (
          <div className="h-full w-1/3 animate-[progress-indeterminate_1.2s_ease-in-out_infinite] rounded-full bg-blue-500" />
        ) : (
          <div
            className="h-full rounded-full bg-blue-500 transition-[width]"
            style={{ width: `${Math.min(100, Math.max(0, percent))}%` }}
          />
        )}
      </div>
    </div>
  );
}
