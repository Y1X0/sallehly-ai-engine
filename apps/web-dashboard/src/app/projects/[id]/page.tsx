"use client";

import { use } from "react";
import { RequireAuth } from "@/components/RequireAuth";
import { AppHeader } from "@/components/AppHeader";
import { ProjectWorkspace } from "@/components/workspace/ProjectWorkspace";

export default function ProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);

  return (
    <RequireAuth>
      <AppHeader />
      <ProjectWorkspace projectId={id} />
    </RequireAuth>
  );
}
