"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import * as api from "@/lib/apiClient";
import { ApiError } from "@/lib/apiClient";
import { Button, Card } from "@/components/ui";

const ASPECT_RATIOS = ["16:9", "9:16", "1:1", "21:9", "4:5"];

interface UploadedReference {
  assetId: string;
  filename: string;
}

export function CreateProjectForm() {
  const { token } = useAuth();
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [prompt, setPrompt] = useState("");
  const [durationSec, setDurationSec] = useState(12);
  const [aspectRatio, setAspectRatio] = useState(ASPECT_RATIOS[0]);
  const [stylePresetId, setStylePresetId] = useState("");
  const [references, setReferences] = useState<UploadedReference[]>([]);
  const [uploading, setUploading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file || !token) return;
    setUploading(true);
    setError(null);
    try {
      const asset = await api.uploadAsset(token, file);
      setReferences((prev) => [...prev, { assetId: asset.asset_id, filename: file.name }]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  function removeReference(assetId: string) {
    setReferences((prev) => prev.filter((ref) => ref.assetId !== assetId));
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!token) return;
    setSubmitting(true);
    setError(null);
    try {
      const project = await api.createProject(token, {
        prompt,
        target_duration_sec: durationSec,
        aspect_ratio: aspectRatio,
        reference_asset_ids: references.map((ref) => ref.assetId),
        style_preset_id: stylePresetId.trim() || undefined,
      });
      router.push(`/projects/${project.project_id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create project");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card title="New project">
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <label className="mb-1 block text-xs font-medium text-zinc-600 dark:text-zinc-400" htmlFor="prompt">
            Creative idea
          </label>
          <textarea
            id="prompt"
            required
            rows={3}
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            placeholder="A 12-second warm premium product ad for a minimalist watch"
            className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 placeholder:text-zinc-400 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-50"
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label
              className="mb-1 block text-xs font-medium text-zinc-600 dark:text-zinc-400"
              htmlFor="duration"
            >
              Duration (sec)
            </label>
            <input
              id="duration"
              type="number"
              min={1}
              required
              value={durationSec}
              onChange={(event) => setDurationSec(Number(event.target.value))}
              className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-50"
            />
          </div>
          <div>
            <label
              className="mb-1 block text-xs font-medium text-zinc-600 dark:text-zinc-400"
              htmlFor="aspect-ratio"
            >
              Aspect ratio
            </label>
            <select
              id="aspect-ratio"
              value={aspectRatio}
              onChange={(event) => setAspectRatio(event.target.value)}
              className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-50"
            >
              {ASPECT_RATIOS.map((ratio) => (
                <option key={ratio} value={ratio}>
                  {ratio}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div>
          <label
            className="mb-1 block text-xs font-medium text-zinc-600 dark:text-zinc-400"
            htmlFor="style-preset"
          >
            Style preset id (optional)
          </label>
          <input
            id="style-preset"
            value={stylePresetId}
            onChange={(event) => setStylePresetId(event.target.value)}
            placeholder="e.g. cinematic-photoreal"
            className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 placeholder:text-zinc-400 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-50"
          />
        </div>

        <div>
          <span className="mb-1 block text-xs font-medium text-zinc-600 dark:text-zinc-400">
            Reference images (optional)
          </span>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            onChange={handleFileChange}
            disabled={uploading}
            className="block w-full text-sm text-zinc-600 file:mr-3 file:rounded-md file:border-0 file:bg-zinc-100 file:px-3 file:py-1.5 file:text-sm file:text-zinc-700 dark:text-zinc-400 dark:file:bg-zinc-800 dark:file:text-zinc-200"
          />
          {references.length > 0 && (
            <ul className="mt-2 space-y-1">
              {references.map((ref) => (
                <li key={ref.assetId} className="flex items-center justify-between text-xs text-zinc-500">
                  <span>{ref.filename}</span>
                  <button
                    type="button"
                    onClick={() => removeReference(ref.assetId)}
                    className="text-red-600 hover:underline dark:text-red-400"
                  >
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}

        <Button type="submit" loading={submitting} disabled={uploading || prompt.trim().length === 0}>
          Create project
        </Button>
      </form>
    </Card>
  );
}
