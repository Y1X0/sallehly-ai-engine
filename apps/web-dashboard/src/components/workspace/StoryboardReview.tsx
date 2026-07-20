import type { Storyboard } from "@/lib/types";
import { ApprovalPanel, Card } from "@/components/ui";

interface StoryboardReviewProps {
  storyboard: Storyboard;
  onApprove: () => void;
  onReject: (feedback: string[]) => void;
  approving: boolean;
  rejecting: boolean;
}

export function StoryboardReview({ storyboard, onApprove, onReject, approving, rejecting }: StoryboardReviewProps) {
  return (
    <div className="space-y-4">
      <Card title="Storyboard">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {storyboard.frames.map((frame) => (
            <div
              key={frame.frame_id}
              className="rounded-md border border-zinc-200 p-3 text-sm dark:border-zinc-800"
            >
              <p className="text-zinc-900 dark:text-zinc-50">{frame.visual_description}</p>
              <dl className="mt-2 grid grid-cols-2 gap-x-2 gap-y-1 text-xs text-zinc-500 dark:text-zinc-400">
                <dt className="font-medium">Framing</dt>
                <dd>{frame.camera_framing}</dd>
                <dt className="font-medium">Lens</dt>
                <dd>{frame.lens_choice}</dd>
                <dt className="font-medium">Movement</dt>
                <dd>{frame.camera_movement}</dd>
                <dt className="font-medium">Lighting</dt>
                <dd>{frame.lighting}</dd>
                <dt className="font-medium">Mood</dt>
                <dd>{frame.mood}</dd>
                <dt className="font-medium">Transition</dt>
                <dd>{frame.transition}</dd>
              </dl>
            </div>
          ))}
        </div>
      </Card>

      <ApprovalPanel
        title="Review the storyboard"
        description="Approve to compile the render plan, or request changes with specific feedback."
        onApprove={onApprove}
        onReject={onReject}
        approving={approving}
        rejecting={rejecting}
      />
    </div>
  );
}
