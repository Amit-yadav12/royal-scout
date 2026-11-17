import { NextResponse } from "next/server";
import { getScope, hasBundle } from "@/lib/bundle";
import { loadDashboardDataset } from "@/lib/server-dataset";
import type { PlayerRow } from "@/lib/types";
import { buildCsv } from "@/lib/csv-provenance";
import { createServerSupabase } from "@/lib/supabase";

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
  const session = await createServerSupabase();
  if (!session) return NextResponse.json({ error: "Authentication is required to export scouting data." }, { status: 401 });
  const { data, error } = await session.auth.getUser();
  if (error || !data.user) return NextResponse.json({ error: "Sign in to export scouting data." }, { status: 401 });

  const { bundle } = await loadDashboardDataset();
  if (!hasBundle(bundle)) {
    return NextResponse.json({ error: "No active dataset is available for export." }, { status: 404, headers: { "Cache-Control": "no-store" } });
  }
  const url = new URL(request.url);
  const discipline = (url.searchParams.get("discipline") ?? "batting") === "bowling" ? "bowling" : "batting";
  const scopeLabel = url.searchParams.get("scope");
  const limitParam = Number(url.searchParams.get("limit") ?? 30);
  const limit = Number.isFinite(limitParam) ? Math.max(1, Math.min(500, limitParam)) : 30;

  const scope = getScope(scopeLabel && scopeLabel !== "global" ? scopeLabel : null, bundle);
  const rows: PlayerRow[] = (discipline === "batting" ? scope?.batters : scope?.bowlers) ?? [];
  const cols = discipline === "batting" ? BAT_COLS : BOWL_COLS;

  const provenance: Record<string, unknown> = {
    generated_at_utc: new Date().toISOString(),
    dataset: bundle.meta.name,
    dataset_id: bundle.meta.dataset_id,
    dataset_version: bundle.meta.dataset_version,
    model_version: bundle.meta.model_version,
    config_fingerprint: bundle.meta.config_fingerprint,
    scope: scope?.scope.label ?? "global",
    ranking_method: discipline === "batting" ? "Reliability-Adjusted Batting Index" : "Reliability-Adjusted Bowling Index",
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
      "Content-Disposition": `attachment; filename="royal-scout-${discipline}-${(scope?.scope.label ?? "global").replace(/[^a-z0-9]+/gi, "-").toLowerCase()}.csv"`,
      "Cache-Control": "no-store",
    },
  });
}
