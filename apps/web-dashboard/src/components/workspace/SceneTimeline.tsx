import type { DirectorPlan } from "@/lib/types";
import { Card, ShotCard } from "@/components/ui";

export function SceneTimeline({ plan }: { plan: DirectorPlan }) {
  return (
    <Card title="Story">
      <p className="mb-3 text-sm text-zinc-600 dark:text-zinc-400">{plan.logline}</p>
      <div className="space-y-4">
        {plan.scenes
          .slice()
          .sort((a, b) => a.order - b.order)
          .map((scene) => (
            <div key={scene.scene_id}>
              <p className="mb-2 text-xs font-medium text-zinc-500 dark:text-zinc-400">
                Scene {scene.order + 1}
                {scene.location ? ` · ${scene.location}` : ""} &mdash; {scene.summary}
              </p>
              <div className="flex gap-3 overflow-x-auto pb-1">
                {scene.shots
                  .slice()
                  .sort((a, b) => a.order - b.order)
                  .map((shot) => (
                    <ShotCard key={shot.shot_id} shot={shot} />
                  ))}
              </div>
            </div>
          ))}
      </div>
    </Card>
  );
}
