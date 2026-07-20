"use client";

import Link from "next/link";
import type { Project } from "@/lib/types";
import { Card, StatusBadge } from "@/components/ui";

export function ProjectList({ projects }: { projects: Project[] }) {
  if (projects.length === 0) {
    return (
      <Card>
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          No projects yet - create one to get started.
        </p>
      </Card>
    );
  }

  return (
    <div className="space-y-2">
      {projects
        .slice()
        .sort((a, b) => b.created_at.localeCompare(a.created_at))
        .map((project) => (
          <Link
            key={project.project_id}
            href={`/projects/${project.project_id}`}
            className="block rounded-lg border border-zinc-200 bg-white p-4 transition-colors hover:border-zinc-300 dark:border-zinc-800 dark:bg-zinc-950 dark:hover:border-zinc-700"
          >
            <div className="flex items-center justify-between gap-4">
              <p className="truncate text-sm text-zinc-900 dark:text-zinc-50">{project.brief.prompt}</p>
              <StatusBadge status={project.status} />
            </div>
            <p className="mt-1 text-xs text-zinc-400 dark:text-zinc-500">
              {project.brief.target_duration_sec}s &middot; {project.brief.aspect_ratio}
            </p>
          </Link>
        ))}
    </div>
  );
}
