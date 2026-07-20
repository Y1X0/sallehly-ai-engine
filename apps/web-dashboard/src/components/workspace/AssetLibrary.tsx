import type { AssetRecord } from "@/lib/types";
import { Card } from "@/components/ui";

export function AssetLibrary({ assets }: { assets: AssetRecord[] }) {
  if (assets.length === 0) {
    return null;
  }

  return (
    <Card title="Asset library">
      <div className="space-y-3">
        {assets.map((asset) => {
          const latest = asset.versions[asset.versions.length - 1];
          const isMock = latest?.metadata?.mock === true;
          return (
            <div key={asset.asset_id} className="rounded-md border border-zinc-200 p-3 dark:border-zinc-800">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-zinc-900 dark:text-zinc-50">
                  {asset.shot_id ?? asset.asset_id} &middot; {asset.kind}
                </span>
                <span className="text-xs text-zinc-400">v{latest?.version} of {asset.versions.length}</span>
              </div>
              {isMock && (
                <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">
                  Local dev mode stub output (LocalProvider) - not a real render.
                </p>
              )}
              <p className="mt-1 truncate text-xs text-zinc-500 dark:text-zinc-400" title={latest?.uri}>
                {latest?.uri}
              </p>
            </div>
          );
        })}
      </div>
    </Card>
  );
}
