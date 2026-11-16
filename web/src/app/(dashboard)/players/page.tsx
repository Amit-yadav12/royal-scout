import { Users } from "lucide-react";
import { loadDashboardDataset } from "@/lib/server-dataset";
import { hasBundle } from "@/lib/bundle";
import { num } from "@/lib/format";
import { PageHeader } from "@/components/shell";
import { Card, CardHeader, Stat } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty";
import { PlayerExplorer } from "@/components/player-explorer";

export default async function PlayersPage() {
  const bundle = (await loadDashboardDataset()).bundle;
  if (!hasBundle(bundle)) return <EmptyState tone="warning" title="No dataset" description="No bundle has been generated yet." />;
  const b = bundle;
  const names = [...new Set([...Object.keys(b.batting.players), ...Object.keys(b.bowling.players)])].sort();
  const rows = names.map((player) => {
    const batting = b.batting.players[player] ?? null;
    const bowling = b.bowling.players[player] ?? null;
    const role = b.roles[player] ?? null;
    const grade = batting?.grade ?? bowling?.grade ?? null;
    return {
      player,
      teams: (batting?.teams ?? bowling?.teams ?? []) as string[],
      role: role?.primary_role ?? batting?.primary_role ?? bowling?.primary_role ?? null,
      roleBasis: role?.role_basis ?? null,
      batting,
      bowling,
      exposure: (batting?.exposure_balls ?? 0) + (bowling?.exposure_balls ?? 0 as number),
      grade,
    };
  });

  return (
    <div className="space-y-4">
      <PageHeader
        title="Player Explorer"
        icon={Users}
        description="Every player record the engine resolved, including those below the ranked thresholds. Exposure is the combined balls faced and legal balls bowled — the honest denominator for sample size."
      />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Players resolved" value={num(rows.length)} />
        <Stat label="With batting records" value={num(rows.filter((r) => r.batting).length)} />
        <Stat label="With bowling records" value={num(rows.filter((r) => r.bowling).length)} />
        <Stat label="Both disciplines" value={num(rows.filter((r) => r.batting && r.bowling).length)} hint="potential all-rounders" />
      </div>
      <Card>
        <CardHeader title="All players" subtitle="Search, filter, sort and paginate. Click a name for the full intelligence dossier." />
        <PlayerExplorer rows={rows} />
      </Card>
    </div>
  );
}
