import type { CinematicReport, RepairAction } from "@/lib/types";
import { Button, Card, ProgressBar } from "@/components/ui";

interface CinematicIntelligencePanelProps {
  report: CinematicReport;
  repairs: RepairAction[];
  onRepair: (shotId: string) => void;
  repairingShotId: string | null;
  onApproveRepair: (repairId: string) => void;
  onRejectRepair: (repairId: string) => void;
  reviewingRepairId: string | null;
}

const SCORE_LABELS: { key: keyof CinematicReport["scores"]; label: string }[] = [
  { key: "character_consistency", label: "Character consistency" },
  { key: "object_consistency", label: "Object consistency" },
  { key: "scene_continuity", label: "Scene continuity" },
  { key: "camera_consistency", label: "Camera continuity" },
  { key: "style", label: "Style lock" },
];

const SEVERITY_COLOR: Record<string, string> = {
  critical: "text-red-600 dark:text-red-400",
  warning: "text-amber-600 dark:text-amber-400",
  info: "text-zinc-500 dark:text-zinc-400",
};

function formatScore(score: number | null): string {
  return score === null ? "not analyzed" : `${Math.round(score * 100)}%`;
}

/** Character/object/scene/camera/style consistency scores, detected
 * problems, and repair suggestions - the dashboard view of
 * CinematicIntelligenceCoordinator.get_project_report(). Populated
 * automatically once the storyboard is approved (see
 * ProjectLifecycle._enrich_render_plan, ADR 0014) - this panel is
 * read-only plus the repair/approve/reject actions, it never triggers
 * analysis itself. */
export function CinematicIntelligencePanel({
  report,
  repairs,
  onRepair,
  repairingShotId,
  onApproveRepair,
  onRejectRepair,
  reviewingRepairId,
}: CinematicIntelligencePanelProps) {
  const pendingRepairShotIds = new Set(repairs.map((repair) => repair.shot_id));

  return (
    <Card title="Cinematic Intelligence">
      <div className="space-y-5">
        <div>
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs font-medium text-zinc-500 dark:text-zinc-400">Overall</span>
            <span className="text-xs font-semibold text-zinc-900 dark:text-zinc-50">
              {formatScore(report.scores.overall)}
            </span>
          </div>
          <ProgressBar percent={report.scores.overall === null ? undefined : report.scores.overall * 100} />
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {SCORE_LABELS.map(({ key, label }) => {
            const score = report.scores[key];
            return (
              <div key={key}>
                <div className="mb-1 flex items-center justify-between">
                  <span className="text-xs text-zinc-500 dark:text-zinc-400">{label}</span>
                  <span className="text-xs text-zinc-700 dark:text-zinc-300">{formatScore(score)}</span>
                </div>
                <ProgressBar percent={score === null ? undefined : score * 100} />
              </div>
            );
          })}
        </div>

        <p className="text-xs text-zinc-400">
          {report.shots_analyzed} shot(s) analyzed · {report.character_count} character(s) ·{" "}
          {report.object_count} object(s) tracked
        </p>

        {report.problems.length > 0 && (
          <div>
            <h4 className="mb-2 text-xs font-semibold text-zinc-700 dark:text-zinc-300">
              Detected problems ({report.problems.length})
            </h4>
            <ul className="space-y-1.5">
              {report.problems.map((problem, index) => (
                <li key={index} className="text-xs">
                  <span className={`font-medium ${SEVERITY_COLOR[problem.severity]}`}>
                    [{problem.severity}]
                  </span>{" "}
                  <span className="text-zinc-600 dark:text-zinc-400">{problem.description}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {report.repair_suggestions.length > 0 && (
          <div>
            <h4 className="mb-2 text-xs font-semibold text-zinc-700 dark:text-zinc-300">Repair suggestions</h4>
            <ul className="space-y-2">
              {report.repair_suggestions.map((suggestion) => (
                <li
                  key={suggestion.shot_id}
                  className="flex items-center justify-between rounded-md border border-zinc-200 px-3 py-2 dark:border-zinc-800"
                >
                  <div>
                    <p className="text-xs font-medium text-zinc-900 dark:text-zinc-50">{suggestion.shot_id}</p>
                    <p className="text-xs text-zinc-400">
                      worst dimension: {suggestion.worst_dimension} ({Math.round(suggestion.overall_score * 100)}%)
                    </p>
                  </div>
                  {!pendingRepairShotIds.has(suggestion.shot_id) && (
                    <Button
                      size="sm"
                      onClick={() => onRepair(suggestion.shot_id)}
                      loading={repairingShotId === suggestion.shot_id}
                    >
                      Repair
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}

        {repairs.length > 0 && (
          <div>
            <h4 className="mb-2 text-xs font-semibold text-zinc-700 dark:text-zinc-300">Proposed repairs</h4>
            <ul className="space-y-2">
              {repairs.map((repair) => (
                <li
                  key={repair.repair_id}
                  className="rounded-md border border-zinc-200 px-3 py-2 dark:border-zinc-800"
                >
                  <div className="mb-1 flex items-center justify-between">
                    <p className="text-xs font-medium text-zinc-900 dark:text-zinc-50">
                      {repair.shot_id} &middot; {repair.repair_type}
                    </p>
                    <span className="text-xs text-zinc-400">
                      {repair.status}
                      {repair.review_status && repair.review_status !== "pending" ? ` · ${repair.review_status}` : ""}
                    </span>
                  </div>
                  {repair.after_summary && (
                    <p className="mb-2 text-xs text-zinc-500 dark:text-zinc-400">{repair.after_summary}</p>
                  )}
                  {(!repair.review_status || repair.review_status === "pending") && (
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        onClick={() => onApproveRepair(repair.repair_id)}
                        loading={reviewingRepairId === repair.repair_id}
                      >
                        Approve
                      </Button>
                      <Button
                        size="sm"
                        variant="danger"
                        onClick={() => onRejectRepair(repair.repair_id)}
                        loading={reviewingRepairId === repair.repair_id}
                      >
                        Reject
                      </Button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}

        {report.problems.length === 0 && report.shots_analyzed > 0 && (
          <p className="text-xs text-zinc-500 dark:text-zinc-400">No consistency problems detected.</p>
        )}
      </div>
    </Card>
  );
}
