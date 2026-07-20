"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import * as api from "@/lib/apiClient";
import { ApiError } from "@/lib/apiClient";
import type { AssetRecord, DirectorPlan, JobStatusSummary, Project, RenderPlan, Storyboard } from "@/lib/types";
import { Button, Card, Timeline } from "@/components/ui";
import { SceneTimeline } from "./SceneTimeline";
import { StoryboardReview } from "./StoryboardReview";
import { RenderPlanReview } from "./RenderPlanReview";
import { JobsPanel } from "./JobsPanel";
import { AssetLibrary } from "./AssetLibrary";

async function fetchOptional<T>(fn: () => Promise<T>): Promise<T | null> {
  try {
    return await fn();
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      return null;
    }
    throw err;
  }
}

export function ProjectWorkspace({ projectId }: { projectId: string }) {
  const { token } = useAuth();

  const [project, setProject] = useState<Project | null>(null);
  const [plan, setPlan] = useState<DirectorPlan | null>(null);
  const [storyboard, setStoryboard] = useState<Storyboard | null>(null);
  const [renderPlan, setRenderPlan] = useState<RenderPlan | null>(null);
  const [jobs, setJobs] = useState<JobStatusSummary[]>([]);
  const [assets, setAssets] = useState<AssetRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [actionPending, setActionPending] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!token) return;
    try {
      const fetchedProject = await api.getProject(token, projectId);
      setProject(fetchedProject);

      const [fetchedPlan, fetchedStoryboard, fetchedRenderPlan] = await Promise.all([
        fetchOptional(() => api.getPlan(token, projectId)),
        fetchOptional(() => api.getStoryboard(token, projectId)),
        fetchOptional(() => api.getRenderPlan(token, projectId)),
      ]);
      setPlan(fetchedPlan);
      setStoryboard(fetchedStoryboard);
      setRenderPlan(fetchedRenderPlan);

      if (fetchedProject.generation_job_ids.length > 0) {
        const fetchedJobs = await Promise.all(
          fetchedProject.generation_job_ids.map((jobId) => api.getJobStatus(token, jobId)),
        );
        setJobs(fetchedJobs);
      } else {
        setJobs([]);
      }

      if (fetchedProject.asset_ids.length > 0) {
        const { assets: fetchedAssets } = await api.listAssets(token, projectId);
        setAssets(fetchedAssets);
      } else {
        setAssets([]);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load project");
    } finally {
      setLoading(false);
    }
  }, [token, projectId]);

  useEffect(() => {
    async function initialLoad() {
      await refresh();
    }
    initialLoad();
  }, [refresh]);

  // Poll while a generation is actually in flight (relevant once a durable/async
  // compute backend is wired in - see docs/adr/0010; the default sync/local stack
  // finishes generate-video synchronously, so this loop is mostly a no-op today).
  useEffect(() => {
    if (project?.status !== "generating") return;
    const interval = setInterval(refresh, 3000);
    return () => clearInterval(interval);
  }, [project?.status, refresh]);

  async function runAction<T>(name: string, fn: () => Promise<T>) {
    setActionPending(name);
    setError(null);
    try {
      await fn();
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Action failed");
    } finally {
      setActionPending(null);
    }
  }

  if (loading) {
    return <p className="p-8 text-sm text-zinc-500 dark:text-zinc-400">Loading...</p>;
  }

  if (!project) {
    return <p className="p-8 text-sm text-red-600 dark:text-red-400">{error ?? "Project not found"}</p>;
  }

  return (
    <div className="mx-auto w-full max-w-3xl space-y-6 px-4 py-8">
      <div>
        <h1 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">{project.brief.prompt}</h1>
        <p className="text-xs text-zinc-400">{project.project_id}</p>
      </div>

      <Card>
        <Timeline status={project.status} rejectedStage={project.rejected_stage} />
      </Card>

      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}

      {project.status === "created" && (
        <Card>
          <Button
            onClick={() => runAction("generate-plan", () => api.generatePlan(token!, projectId))}
            loading={actionPending === "generate-plan"}
          >
            Generate creative plan
          </Button>
        </Card>
      )}

      {project.status === "planning" && (
        <Card>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">Generating the creative plan...</p>
        </Card>
      )}

      {plan && <SceneTimeline plan={plan} />}

      {project.status === "waiting_storyboard_approval" && storyboard && (
        <StoryboardReview
          storyboard={storyboard}
          onApprove={() => runAction("approve-storyboard", () => api.approveStoryboard(token!, projectId))}
          onReject={(feedback) =>
            runAction("reject-storyboard", () => api.rejectStoryboard(token!, projectId, { feedback }))
          }
          approving={actionPending === "approve-storyboard"}
          rejecting={actionPending === "reject-storyboard"}
        />
      )}

      {project.status === "waiting_render_approval" && renderPlan && (
        <RenderPlanReview
          renderPlan={renderPlan}
          onApprove={() => runAction("approve-render", () => api.approveRender(token!, projectId))}
          onReject={(feedback, qualityTier) =>
            runAction("reject-render", () =>
              api.rejectRender(token!, projectId, { feedback, quality_tier: qualityTier }),
            )
          }
          approving={actionPending === "approve-render"}
          rejecting={actionPending === "reject-render"}
        />
      )}

      {project.status === "rejected" && (
        <Card>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">Applying feedback and regenerating...</p>
        </Card>
      )}

      {project.status === "approved" && (
        <Card>
          <Button
            onClick={() => runAction("generate-video", () => api.generateVideo(token!, projectId))}
            loading={actionPending === "generate-video"}
          >
            Start generation
          </Button>
        </Card>
      )}

      {project.status === "generating" && (
        <Card>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">Generating video...</p>
        </Card>
      )}

      {jobs.length > 0 && (
        <JobsPanel
          jobs={jobs}
          showRetry={project.status === "failed"}
          onRetry={() => runAction("retry-generation", () => api.retryGeneration(token!, projectId))}
          retrying={actionPending === "retry-generation"}
        />
      )}

      {project.status === "failed" && project.error_message && (
        <Card>
          <p className="text-sm text-red-600 dark:text-red-400">{project.error_message}</p>
        </Card>
      )}

      <AssetLibrary assets={assets} />
    </div>
  );
}
