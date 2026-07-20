"use client";

import { useState } from "react";
import type { RenderPlan } from "@/lib/types";
import { ApprovalPanel, Card } from "@/components/ui";

const QUALITY_TIERS = ["preview", "standard", "final"];

interface RenderPlanReviewProps {
  renderPlan: RenderPlan;
  onApprove: () => void;
  onReject: (feedback: string[], qualityTier?: string) => void;
  approving: boolean;
  rejecting: boolean;
}

export function RenderPlanReview({ renderPlan, onApprove, onReject, approving, rejecting }: RenderPlanReviewProps) {
  const [qualityTier, setQualityTier] = useState("");

  return (
    <div className="space-y-4">
      <Card title="Render plan" actions={<span className="text-xs text-zinc-400">{renderPlan.engine_id}</span>}>
        <div className="space-y-2">
          {renderPlan.render_specs.map((spec) => (
            <div
              key={spec.shot_id}
              className="flex items-center justify-between rounded-md border border-zinc-200 px-3 py-2 text-sm dark:border-zinc-800"
            >
              <span className="text-zinc-900 dark:text-zinc-50">{spec.shot_id}</span>
              <span className="text-xs text-zinc-500 dark:text-zinc-400">
                {spec.duration_sec}s &middot; {spec.resolution} &middot; {spec.fps}fps
                {spec.quality_tier ? ` · ${spec.quality_tier}` : ""}
              </span>
            </div>
          ))}
        </div>
      </Card>

      <ApprovalPanel
        title="Review the render plan"
        description="Approve to unlock generation, or request changes (optionally bumping the quality tier)."
        onApprove={onApprove}
        onReject={(feedback) => onReject(feedback, qualityTier || undefined)}
        approving={approving}
        rejecting={rejecting}
        extra={
          <select
            value={qualityTier}
            onChange={(event) => setQualityTier(event.target.value)}
            className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-50"
          >
            <option value="">Keep current quality tier</option>
            {QUALITY_TIERS.map((tier) => (
              <option key={tier} value={tier}>
                {tier}
              </option>
            ))}
          </select>
        }
      />
    </div>
  );
}
