import type { Shot } from "@/lib/types";

function Badge({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded bg-zinc-100 px-1.5 py-0.5 text-xs text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
      {children}
    </span>
  );
}

export function ShotCard({ shot }: { shot: Shot }) {
  return (
    <div className="min-w-56 rounded-md border border-zinc-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-950">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-zinc-500 dark:text-zinc-400">Shot {shot.order + 1}</span>
        <span className="text-xs text-zinc-400 dark:text-zinc-500">{shot.duration_sec}s</span>
      </div>
      <p className="mt-1.5 text-sm text-zinc-900 dark:text-zinc-50">{shot.description}</p>
      <div className="mt-2 flex flex-wrap gap-1">
        {shot.camera?.shot_type && <Badge>{shot.camera.shot_type.replace(/_/g, " ")}</Badge>}
        {shot.camera?.movement?.type && <Badge>{shot.camera.movement.type.replace(/_/g, " ")}</Badge>}
        {shot.lighting?.mood && <Badge>{shot.lighting.mood}</Badge>}
        {shot.motion?.subject_motion && <Badge>{shot.motion.subject_motion}</Badge>}
      </div>
    </div>
  );
}
