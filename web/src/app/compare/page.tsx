import { Suspense } from "react";
import { GitCompareArrows } from "lucide-react";
import { bundle, hasBundle } from "@/lib/bundle";
import { PageHeader } from "@/components/shell";
import { Card, CardHeader } from "@/components/ui/card";
import { EmptyState, Notice } from "@/components/ui/empty";
import { ComparisonLab } from "@/components/comparison-lab";

export default function ComparePage() {
  if (!hasBundle()) return <EmptyState tone="warning" title="No dataset" description="No bundle has been generated yet." />;
  return (
    <div className="space-y-4">
      <PageHeader
        title="Player Comparison Lab"
        icon={GitCompareArrows}
        description="Compare up to four players on a like-for-like basis. Every axis is normalised to a 0–100 population scale before plotting — batting average, economy and strike rate are never placed on a shared unscaled axis."
      />
      <Notice>
        Comparisons are role-aware and scope-aware: percentile components are computed inside the active dataset, so a batter
        is compared with batters and a bowler with bowlers.
      </Notice>
      <Card>
        <CardHeader title="Comparison workspace" subtitle="Pick up to four players. Series and bars update against the full dataset population." />
        <Suspense fallback={<div className="px-5 py-8 text-xs text-ink-faint">Loading comparison workspace…</div>}>
          <ComparisonLab data={{
            names: [...new Set([...Object.keys(bundle.batting.players), ...Object.keys(bundle.bowling.players)])].sort(),
            batting: bundle.batting.players,
            bowling: bundle.bowling.players,
            roles: bundle.roles,
          }} />
        </Suspense>
      </Card>
    </div>
  );
}
