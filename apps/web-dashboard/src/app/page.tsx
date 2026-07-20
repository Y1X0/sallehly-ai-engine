"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import * as api from "@/lib/apiClient";
import { ApiError } from "@/lib/apiClient";
import type { Project } from "@/lib/types";
import { RequireAuth } from "@/components/RequireAuth";
import { AppHeader } from "@/components/AppHeader";
import { CreateProjectForm } from "@/components/dashboard/CreateProjectForm";
import { ProjectList } from "@/components/dashboard/ProjectList";

function Dashboard() {
  const { token } = useAuth();
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    async function loadProjects() {
      try {
        const { projects: fetched } = await api.listProjects(token!);
        setProjects(fetched);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Could not load projects");
      } finally {
        setLoading(false);
      }
    }
    loadProjects();
  }, [token]);

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-8">
      <h1 className="mb-6 text-xl font-semibold text-zinc-900 dark:text-zinc-50">Your projects</h1>
      <div className="space-y-6">
        <CreateProjectForm />
        {loading ? (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">Loading...</p>
        ) : error ? (
          <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
        ) : (
          <ProjectList projects={projects} />
        )}
      </div>
    </div>
  );
}

export default function Home() {
  return (
    <RequireAuth>
      <AppHeader />
      <Dashboard />
    </RequireAuth>
  );
}
