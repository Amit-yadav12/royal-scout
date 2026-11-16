import rawBundle from "@/data/bundle.json";
import type { Bundle, PlayerRow, ScopePayload } from "./types";

/**
 * The dashboard reads a pre-computed analytical bundle produced by the Python
 * engine (`engine/royalscout/pipeline.py`). Nothing is recalculated in the
 * browser, so what you see is exactly what the model produced.
 *
 * If the snapshot has not been generated yet the loader returns `null` and every
 * page renders an explicit empty state instead of placeholder numbers.
 */
export const bundle = (rawBundle as unknown as Bundle) ?? null;

export function hasBundle(b: Bundle | null = bundle): b is Bundle {
  return Boolean(b && b.meta && b.leaderboards && b.counts);
}

export function getScope(scopeLabel?: string | null, data: Bundle | null = bundle): ScopePayload | null {
  if (!hasBundle(data)) return null;
  const active = data;
  const scopes = active.leaderboards.scopes;
  if (!scopes?.length) return null;
  if (!scopeLabel || scopeLabel === "global") {
    const globalRow: ScopePayload = {
      scope: { type: "global", label: "All data", filter: {} },
      batters: active.leaderboards.global.batters,
      bowlers: active.leaderboards.global.bowlers,
      batters_evaluated: active.leaderboards.global.batters_evaluated,
      bowlers_evaluated: active.leaderboards.global.bowlers_evaluated,
      batters_eligible: active.leaderboards.global.batters_eligible,
      bowlers_eligible: active.leaderboards.global.bowlers_eligible,
    };
    return globalRow;
  }
  return scopes.find((s) => s.scope.label === scopeLabel) ?? scopes[0];
}

export function scopeOptions(data: Bundle | null = bundle): { label: string; type: string; count: number }[] {
  if (!hasBundle(data)) return [];
  return data.leaderboards.scopes.map((s) => ({
    label: s.scope.label,
    type: s.scope.type,
    count: Math.max(s.batters_eligible, s.bowlers_eligible),
  }));
}

export function playerMetrics(name: string): { batting: PlayerRow | null; bowling: PlayerRow | null; role: any | null } {
  if (!hasBundle()) return { batting: null, bowling: null, role: null };
  return {
    batting: bundle.batting.players[name] ?? null,
    bowling: bundle.bowling.players[name] ?? null,
    role: bundle.roles[name] ?? null,
  };
}

export function allPlayers(): string[] {
  if (!hasBundle()) return [];
  const names = new Set<string>([
    ...Object.keys(bundle.batting.players),
    ...Object.keys(bundle.bowling.players),
  ]);
  return [...names].sort();
}

export function leaderboardFor(
  discipline: "batting" | "bowling",
  scopeLabel?: string | null,
  data: Bundle | null = bundle,
): PlayerRow[] {
  const scope = getScope(scopeLabel, data);
  if (!scope) return [];
  return discipline === "batting" ? scope.batters : scope.bowlers;
}

export function datasetBadge(data: Bundle | null = bundle): string {
  if (!hasBundle(data)) return "No dataset";
  const version = data.meta.dataset_version ?? 1;
  return `${data.meta.name} · v${version}`;
}

export function limitations(data: Bundle | null = bundle): string[] {
  if (!hasBundle(data)) return ["No analytical bundle has been generated yet."];
  return data.meta.limitations ?? [];
}
