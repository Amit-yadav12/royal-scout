import { ShieldCheck, ShieldAlert } from "lucide-react";
import { dec, num } from "@/lib/format";
import { PageHeader } from "@/components/shell";
import { Card, CardBody, CardHeader, KeyValue, Stat } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty";
import { loadDashboardDataset } from "@/lib/server-dataset";
import { DataTable, TBody, TD, TH, THead } from "@/components/ui/table";
import type { PressureRankRow } from "@/lib/types";

function PickTable({ rows, role }: { rows: PressureRankRow[]; role: "bat" | "bowl" }) {
  return (
    <DataTable>
      <THead>
        <tr>
          <TH>#</TH><TH>Player</TH><TH className="text-right">PRI</TH>
          <TH className="text-right">Pressure balls</TH>
          <TH className="text-right">{role === "bat" ? "Press SR" : "Press econ"}</TH>
          <TH className="text-right">Bootstrap rank 90% interval</TH>
          <TH className="text-right">Top 10 probability</TH>
          <TH className="text-right">IPL / T20I rank</TH>
          <TH className="text-right">Methods top 10</TH>
          <TH className="text-right">Seasons above baseline</TH>
          <TH>Robustness gate</TH>
        </tr>
      </THead>
      <TBody>
        {rows.map((r) => (
          <tr key={`${role}-${r.player_id}`}>
            <TD className="font-mono">{r.rank}</TD>
            <TD className="font-medium">{r.player_name ?? `ID ${r.player_id}`}</TD>
            <TD className="text-right font-mono">{dec(r.pri, 1)}</TD>
            <TD className="text-right font-mono">{num(r.p_balls)}</TD>
            <TD className="text-right font-mono">{dec(role === "bat" ? r.p_sr : r.p_econ, role === "bat" ? 1 : 2)}</TD>
            <TD className="text-right font-mono">{r.rank_p05 == null || r.rank_p95 == null ? "—" : `${dec(r.rank_p05, 0)}–${dec(r.rank_p95, 0)}`}</TD>
            <TD className="text-right font-mono">{r.p_top10 == null ? "—" : `${dec(r.p_top10 * 100, 0)}%`}</TD>
            <TD className="text-right font-mono">{r.ipl_rank ?? "—"} / {r.t20i_rank ?? "—"}</TD>
            <TD className="text-right font-mono">{num(r.methods_with_top10)} / {num(r.methods_available)}</TD>
            <TD className="text-right font-mono">{num(r.seasons_above_baseline)} / {num(r.seasons_evaluated)}</TD>
            <TD><Badge tone={r.confirmed ? "positive" : "warning"}>{r.confirmed ? "confirmed" : "provisional"}</Badge></TD>
          </tr>
        ))}
      </TBody>
    </DataTable>
  );
}

export default async function PressureAuditPage() {
  const { bundle } = await loadDashboardDataset();
  const rankings = bundle?.pressure_rankings;
  if (!bundle || !rankings?.facts) {
    return <EmptyState tone="warning" title="No provider-specific pressure ranking is available" description="This active dataset does not contain a supported SupeRR Selector ball-by-ball pack. Overall rankings remain separate; no pressure shortlist is inferred from aggregate data." />;
  }
  const f = rankings.facts;
  const eligible = f.eligible_primary;
  const batting = rankings.final.batters ?? [];
  const bowling = rankings.final.bowlers ?? [];
  const otherBatting = rankings.other_t20_sensitivity.batters ?? [];
  const pressureShare = f.pressure_share_primary == null ? "—" : `${dec(f.pressure_share_primary * 100, 1)}%`;
  const anyRanked = batting.length + bowling.length > 0;
  return (
    <div className="space-y-4">
      <PageHeader
        title="Pressure Ranking — active dataset"
        description={`SupeRR PRI pressure rankings for ${bundle.meta.name}. This shortlist is separate from the overall RABI/RABBI leaderboards; only regulation IPL + T20I deliveries enter the primary pool.`}
      />
      <div className="grid gap-4 md:grid-cols-4">
        <Stat label="Primary deliveries" value={num(f.primary_deliveries)} hint={`${num(f.matches_primary)} matches · IPL + T20I`} />
        <Stat label="Pressure balls" value={num(f.pressure_deliveries_primary)} hint={`${pressureShare} of primary deliveries`} />
        <Stat label="Pressure wickets / 100" value={dec(f.pressure_wickets_per_100, 2)} hint={`vs ${dec(f.nonpressure_wickets_per_100, 2)} outside pressure`} />
        <Stat label="Eligible candidates" value={`${num(eligible.batters)} / ${num(eligible.bowlers)}`} hint="batters / bowlers meeting the published exposure floors" />
      </div>
      {!anyRanked ? (
        <EmptyState tone="warning" title="No candidates meet pressure eligibility" description="The engine computed the provider-specific pressure analysis, but no players met the minimum pressure-ball, match, innings, and baseline-exposure thresholds. It does not pad either Top 10." />
      ) : (
        <div className="grid gap-4">
          <Card><CardHeader title="Top 10 batters under pressure" subtitle="PRI — pressure reliability index; eligible candidates only" /><CardBody><PickTable rows={batting.slice(0, 10)} role="bat" /></CardBody></Card>
          <Card><CardHeader title="Top 10 bowlers under pressure" subtitle="PRI — pressure reliability index; eligible candidates only" /><CardBody><PickTable rows={bowling.slice(0, 10)} role="bowl" /></CardBody></Card>
        </div>
      )}
      {otherBatting.length > 0 && (
        <Card>
          <CardHeader title="Other T20 — sensitivity only" subtitle="Excluded from the primary IPL + T20I ranking; shown separately, not pooled into the selection list." />
          <CardBody>
            <DataTable>
              <THead><tr><TH>#</TH><TH>Player</TH><TH className="text-right">PRI</TH><TH className="text-right">Pressure balls</TH><TH className="text-right">Pressure SR</TH></tr></THead>
              <TBody>{otherBatting.slice(0, 10).map((r) => <tr key={`other-${r.player_id}`}>
                <TD className="font-mono">{r.rank}</TD><TD>{r.player_name ?? `ID ${r.player_id}`}</TD>
                <TD className="text-right font-mono">{dec(r.pri, 1)}</TD><TD className="text-right font-mono">{num(r.p_balls)}</TD>
                <TD className="text-right font-mono">{dec(r.p_sr, 1)}</TD>
              </tr>)}</TBody>
            </DataTable>
          </CardBody>
        </Card>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Method and evidence" subtitle="Existing SupeRR pressure methodology; no proxy substitution" />
          <CardBody>
            <KeyValue label="Pool" value="Regulation innings only; IPL + T20I primary" />
            <KeyValue label="Eligibility floors" value="≥120 pressure balls, ≥6 pressure matches, ≥8 pressure innings, ≥60 baseline balls" />
            <KeyValue label="PRI blocks" value="Situation-par level (55%), own-baseline lift (30%), innings consistency (15%)" />
            <KeyValue label="Confidence evidence" value={`${num(f.bootstrap_resamples)} match-bootstrap resamples; median and 5th–95th percentile ranks; probability of a top-10 rank`} />
            <KeyValue label="Competition robustness" value="Separate IPL and T20I ranks are shown; they are diagnostic, not hidden selection gates" />
            <KeyValue label="Eligible player counts" value={`${num(eligible.batters)} batters / ${num(eligible.bowlers)} bowlers`} />
            <KeyValue label="Alternative-method checks" value={`${num(f.robustness?.bat?.alternative_methods)} batting / ${num(f.robustness?.bowl?.alternative_methods)} bowling`} />
            <KeyValue label="Gate-confirmed finalists" value={`${num(f.robustness?.bat?.confirmed_candidates)} batters / ${num(f.robustness?.bowl?.confirmed_candidates)} bowlers`} />
            <KeyValue label="Other T20" value={`${num(f.other_t20_sensitivity_deliveries)} deliveries; sensitivity only, excluded from primary ranks`} />
            <KeyValue label="Overall rankings" value="See Top Batters / Top Bowlers; those all-data leaderboards are not the pressure shortlist." />
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Processing and validation boundaries" subtitle="Dataset-specific counts from the active bundle" />
          <CardBody>
            <div className="flex items-center gap-2 pb-2">
              {f.super_over_deliveries_excluded > 0 ? <ShieldCheck className="h-5 w-5 text-emerald-500" /> : <ShieldAlert className="h-5 w-5 text-amber-500" />}
              <span className="text-sm">{num(f.super_over_deliveries_excluded)} super-over deliveries were excluded from ratings.</span>
            </div>
            <KeyValue label="Source deliveries" value={num(f.deliveries_source)} />
            <KeyValue label="Regulation deliveries" value={num(f.regulation_deliveries)} />
            <KeyValue label="Pressure runs / over" value={dec(f.pressure_runs_per_over, 2)} />
            <KeyValue label="Non-pressure runs / over" value={dec(f.nonpressure_runs_per_over, 2)} />
            <KeyValue label="Bootstrap resamples" value={num(f.bootstrap_resamples)} />
            <KeyValue label="Unknown dismissal attribution" value={num(f.unknown_dismissal_attribution_rows)} />
            <KeyValue label="Data identity merges" value={`${num(f.identity_merges?.length ?? 0)} audited provider alias merge(s)`} />
            <div className="pt-2"><Badge tone="warning">Historical data does not verify current auction availability.</Badge></div>
          </CardBody>
        </Card>
      </div>
      <p className="text-xs text-ink-soft">Dataset {bundle.meta.dataset_id} · version {bundle.meta.dataset_version} · config {bundle.meta.config_fingerprint}</p>
    </div>
  );
}
