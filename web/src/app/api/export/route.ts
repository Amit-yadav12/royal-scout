import { NextResponse } from "next/server";
import { getScope, hasBundle } from "@/lib/bundle";
import { loadDashboardDataset } from "@/lib/server-dataset";
import type { PlayerRow, PressureRankRow } from "@/lib/types";
import { buildCsv } from "@/lib/csv-provenance";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const BAT_COLS = [
  ["rank", "Rank"], ["player", "Player"], ["teams", "State Team"], ["primary_role", "Role"],
  ["innings", "Innings"], ["runs", "Runs"], ["balls_faced", "Balls"], ["average", "Average"],
  ["strike_rate", "Strike Rate"], ["fours", "4s"], ["sixes", "6s"], ["boundary_pct", "Boundary %"],
  ["consistency", "Consistency"], ["pressure_score", "Pressure"], ["grade", "Confidence"],
  ["score_coverage", "Score Coverage"], ["rabi", "Final Score"],
] as const;

const BOWL_COLS = [
  ["rank", "Rank"], ["player", "Player"], ["teams", "State Team"], ["primary_role", "Role"],
  ["bowler_type", "Bowler Type"], ["innings", "Innings"], ["overs", "Overs"], ["wickets", "Wickets"],
  ["runs_conceded", "Runs Conceded"], ["average", "Average"], ["economy", "Economy"],
  ["bowling_strike_rate", "Strike Rate"], ["dot_pct", "Dot %"], ["consistency", "Consistency"],
  ["pressure_score", "Pressure"], ["grade", "Confidence"], ["score_coverage", "Score Coverage"],
  ["rabi_bowl", "Final Score"],
] as const;

function csvEscape(value: unknown): string {
  if (value === null || value === undefined) return "";
  const s = Array.isArray(value) ? value.join("; ") : String(value);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

/**
 * Server-side export so a downloaded file always matches the active scope and the
 * methodology in force. Provenance is prefixed as `#` comments.
 */
export async function GET(request: Request) {
  // Export mirrors the public analytics pages; it contains no private job or
  // account data and requires no session.
  const { bundle } = await loadDashboardDataset();
  if (!hasBundle(bundle)) {
    return NextResponse.json({ error: "No active dataset is available for export." }, { status: 404, headers: { "Cache-Control": "no-store" } });
  }
  const url = new URL(request.url);
  const discipline = (url.searchParams.get("discipline") ?? "batting") === "bowling" ? "bowling" : "batting";
  const scopeLabel = url.searchParams.get("scope");
  const ranking = url.searchParams.get("ranking") === "pressure" ? "pressure" : "overall";
  const pressurePool = url.searchParams.get("pool") ?? "primary";
  const limitParam = Number(url.searchParams.get("limit") ?? (ranking === "pressure" ? 10 : 30));
  const limit = Number.isFinite(limitParam) ? Math.max(1, Math.min(500, limitParam)) : (ranking === "pressure" ? 10 : 30);

  const scope = getScope(scopeLabel && scopeLabel !== "global" ? scopeLabel : null, bundle);
  const poolKey: "primary" | "ipl_robustness" | "t20i_robustness" | "other_t20_sensitivity" = pressurePool === "ipl" ? "ipl_robustness"
    : pressurePool === "t20i" ? "t20i_robustness"
      : pressurePool === "other_t20_sensitivity" ? "other_t20_sensitivity" : "primary";
  const selectedPressurePool = ranking === "pressure"
    ? (poolKey === "primary" ? bundle.pressure_rankings?.final : bundle.pressure_rankings?.[poolKey])
    : undefined;
  const rows: Array<PlayerRow | PressureRankRow> = ranking === "pressure"
    ? (discipline === "batting" ? selectedPressurePool?.batters : selectedPressurePool?.bowlers) ?? []
    : (discipline === "batting" ? scope?.batters : scope?.bowlers) ?? [];
  const pressureCols = [
    ["rank", "Rank"], ["player_id", "Player ID"], ["player_name", "Player"], ["pri", "Pressure Reliability Index"],
    ["p_balls", "Pressure balls"], ["pressure_matches", "Pressure matches"], ["pressure_innings", "Pressure innings"],
    [discipline === "batting" ? "p_sr" : "p_econ", discipline === "batting" ? "Pressure strike rate" : "Pressure economy"],
    ["rank_median", "Bootstrap median rank"], ["rank_p05", "Bootstrap rank p05"], ["rank_p95", "Bootstrap rank p95"],
    ["p_top10", "Bootstrap top-10 probability"], ["ipl_rank", "IPL robustness rank"], ["t20i_rank", "T20I robustness rank"],
    ["median_rank_across_methods", "Median rank across methods"], ["methods_with_top10", "Methods with top-10 rank"],
    ["methods_available", "Methods available"], ["seasons_above_baseline", "Seasons above baseline"],
    ["seasons_evaluated", "Seasons evaluated"], ["confirmed", "Robustness gate confirmed"],
  ] as const;
  const cols = ranking === "pressure" ? pressureCols : discipline === "batting" ? BAT_COLS : BOWL_COLS;

  const provenance: Record<string, unknown> = {
    generated_at_utc: new Date().toISOString(),
    dataset: bundle.meta.name,
    dataset_id: bundle.meta.dataset_id,
    dataset_version: bundle.meta.dataset_version,
    model_version: bundle.meta.model_version,
    config_fingerprint: bundle.meta.config_fingerprint,
    scope: ranking === "pressure" ? poolKey : (scope?.scope.label ?? "global"),
    ranking_method: ranking === "pressure" ? "SupeRR Pressure Reliability Index (PRI)" :
      discipline === "batting" ? "Reliability-Adjusted Batting Index" : "Reliability-Adjusted Bowling Index",
    competition_pool: ranking === "pressure" ? (poolKey === "primary" ? "IPL + T20I primary" : poolKey) : undefined,
    sample_size_rules: ranking === "pressure" ? bundle.pressure_rankings?.facts?.eligibility : undefined,
    confidence_method: ranking !== "pressure" ? undefined : poolKey === "primary"
      ? `match bootstrap (${bundle.pressure_rankings?.facts.bootstrap_resamples ?? 400} resamples), rank p05/p95 and p_top10`
      : "competition-specific PRI rank only; bootstrap intervals not computed for this separate pool",
    selection_gate: ranking === "pressure" && poolKey === "primary"
      ? "median rank <=15 across available alternatives and pressure evidence in >=2 seasons; unconfirmed candidates remain labelled" : undefined,
    rows_exported: Math.min(limit, rows.length),
    is_fixture: bundle.meta.is_fixture,
    limitations: bundle.meta.limitations,
  };

  const csv = buildCsv(
    cols.map(([, label]) => label),
    rows.slice(0, limit).map((row) =>
      cols.map(([key]) => {
        const value = (row as unknown as Record<string, unknown>)[key];
        if (value === null || value === undefined) return "";
        return Array.isArray(value) ? value.join("; ") : String(value);
      }),
    ),
    provenance,
  );

  return new NextResponse(csv, {
    status: 200,
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename="royal-scout-${ranking}-${discipline}-${(ranking === "pressure" ? poolKey : scope?.scope.label ?? "global").replace(/[^a-z0-9]+/gi, "-").toLowerCase()}.csv"`,
      "Cache-Control": "no-store",
    },
  });
}
