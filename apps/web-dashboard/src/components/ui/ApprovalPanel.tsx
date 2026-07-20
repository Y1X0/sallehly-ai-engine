"use client";

import { useState, type ReactNode } from "react";
import { Button } from "./Button";

interface ApprovalPanelProps {
  title: string;
  description?: string;
  onApprove: () => void;
  onReject: (feedback: string[]) => void;
  approving?: boolean;
  rejecting?: boolean;
  disabled?: boolean;
  /** Extra controls rendered above the feedback textarea (e.g. a quality-tier select for the render-plan gate). */
  extra?: ReactNode;
}

export function ApprovalPanel({
  title,
  description,
  onApprove,
  onReject,
  approving = false,
  rejecting = false,
  disabled = false,
  extra,
}: ApprovalPanelProps) {
  const [requestingChanges, setRequestingChanges] = useState(false);
  const [feedback, setFeedback] = useState("");

  const busy = approving || rejecting;

  function submitRejection() {
    const items = feedback
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);
    if (items.length === 0) return;
    onReject(items);
  }

  return (
    <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 dark:border-amber-800 dark:bg-amber-950/40">
      <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">{title}</h3>
      {description && <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">{description}</p>}

      {!requestingChanges ? (
        <div className="mt-3 flex gap-2">
          <Button onClick={onApprove} loading={approving} disabled={disabled || busy}>
            Approve
          </Button>
          <Button
            variant="secondary"
            onClick={() => setRequestingChanges(true)}
            disabled={disabled || busy}
          >
            Request changes
          </Button>
        </div>
      ) : (
        <div className="mt-3 space-y-2">
          {extra}
          <textarea
            className="w-full rounded-md border border-zinc-300 bg-white p-2 text-sm text-zinc-900 placeholder:text-zinc-400 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-50"
            rows={3}
            placeholder="One piece of feedback per line, e.g. &quot;too static, add more camera movement&quot;"
            value={feedback}
            onChange={(event) => setFeedback(event.target.value)}
            disabled={busy}
          />
          <div className="flex gap-2">
            <Button
              variant="danger"
              onClick={submitRejection}
              loading={rejecting}
              disabled={disabled || busy || feedback.trim().length === 0}
            >
              Submit feedback
            </Button>
            <Button
              variant="ghost"
              onClick={() => {
                setRequestingChanges(false);
                setFeedback("");
              }}
              disabled={busy}
            >
              Cancel
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
