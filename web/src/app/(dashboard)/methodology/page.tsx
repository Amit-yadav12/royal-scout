import { Sliders } from "lucide-react";
import { loadDashboardDataset } from "@/lib/server-dataset";
import { hasBundle, limitations } from "@/lib/bundle";
import { dec } from "@/lib/format";
import { PageHeader } from "@/components/shell";
import { Card, CardBody, CardHeader, KeyValue } from "@/components/ui/card";
import { EmptyState, Notice } from "@/components/ui/empty";
import { DataTable, TBody, TD, TH, THead } from "@/components/ui/table";

const DEFINITIONS: { metric: string; definition: string; type: string }[] = [
  { metric: "Runs", definition: "Runs credited to the batter by the source scorecard. Extras are never attributed to the batter.", type: "A · direct" },
  { metric: "Balls faced", definition: "Deliveries faced, including illegal deliveries where the source counts them. If absent, back-calculated from runs and stated strike rate and flagged.", type: "A/B" },
  { metric: "Dismissals", definition: "Completed dismissals only. Not-outs are subtracted, never treated as dismissals; retired hurt is recorded as not-out with a flag.", type: "A/B" },
  { metric: "Batting average", definition: "runs ÷ dismissals. Left unavailable when dismissals cannot be established — never imputed as innings.", type: "B · derived" },
  { metric: "Strike rate", definition: "100 × runs ÷ balls faced. Recomputed from components in preference to a stated value.", type: "B · derived" },
  { metric: "Boundary %", definition: "(4×fours + 6×sixes) ÷ runs × 100 — share of runs coming from boundaries.", type: "B · derived" },
  { metric: "Dot-ball %", definition: "Dot deliveries ÷ balls. Requires an explicit dot count or ball-by-ball data.", type: "A / D" },
  { metric: "Legal balls bowled", definition: "Overs read in cricket notation: 3.4 overs = 22 balls. Illegal notation (e.g. 4.7) is rejected and flagged, never guessed.", type: "A · direct" },
  { metric: "Economy", definition: "runs conceded × 6 ÷ legal balls. Uses legal deliveries, not decimal overs.", type: "B · derived" },
  { metric: "Bowling average / strike rate", definition: "runs ÷ wickets and legal balls ÷ wickets respectively. Different denominators from batting — deliberately.", type: "B · derived" },
  { metric: "Consistency", definition: "1/(1+CV) of the player's innings (or match) scores × 100, percentile-ranked. Where only aggregates exist, dispersion is measured across aggregates and labelled as such.", type: "B / caveated" },
  { metric: "Pressure score", definition: "Percentile of the player's own pressure-vs-non-pressure differential on deliveries tagged by documented match-situation rules, shrunk toward zero on limited tagged exposure.", type: "A · needs ball-by-ball" },
  { metric: "Confidence grade", definition: "Exposure (balls / legal balls) crossed with composite coverage, then demoted if the bootstrap interval is wide relative to the score.", type: "B · derived" },
  { metric: "Coverage", definition: "Share of the composite's nominal weight the dataset actually supports. Published beside every score.", type: "A · accounting" },
  { metric: "Reliability-Adjusted Index", definition: "Weighted mean over available components after shrinkage, with weights renormalised over what is available. Not comparable across scopes.", type: "B · derived" },
];

export default async function MethodologyPage() {
  const bundle = (await loadDashboardDataset()).bundle;
  if (!hasBundle(bundle)) return <EmptyState tone="warning" title="No dataset" description="No bundle has been generated yet." />;
  const b = bundle;
  const cfg = b.meta.config;

  return (
    <div className="space-y-4">
      <PageHeader
        title="Methodology & Settings"
        icon={Sliders}
        description="The exact definitions, weights and thresholds in force for this dataset. Every value is also embedded in the export provenance block and pinned by the config fingerprint."
      />

      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader title="Model identity" />
          <CardBody className="space-y-1">
            <KeyValue label="Model version" value={b.meta.model_version} mono />
            <KeyValue label="Metric semantics version" value={b.meta.config.metric_semantics_version} mono />
            <KeyValue label="Config fingerprint" value={<span className="font-mono text-2xs">{b.meta.config_fingerprint}</span>} />
            <KeyValue label="Dataset" value={b.meta.name} />
            <KeyValue label="Version" value={`v${b.meta.dataset_version}`} mono />
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Eligibility & sample rules" />
          <CardBody className="space-y-1">
            <KeyValue label="Batting: min balls" value={cfg.eligibility.bat_min_balls_ranked} mono />
            <KeyValue label="Batting: min innings" value={cfg.eligibility.bat_min_innings_ranked} mono />
            <KeyValue label="Bowling: min legal balls" value={cfg.eligibility.bowl_min_balls_ranked} mono />
            <KeyValue label="Bowling: min innings" value={cfg.eligibility.bowl_min_innings_ranked} mono />
            <KeyValue label="Leaderboard size" value={cfg.eligibility.leaderboard_size} mono />
            <KeyValue label="Shrinkage k (balls)" value={cfg.stats.prior_strength_balls_bat} mono />
            <KeyValue label="Shrinkage k (dismissals / wickets)" value={`${cfg.stats.prior_strength_dismissals_bat} / ${cfg.stats.prior_strength_wickets_bowl}`} mono />
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Confidence grading" />
          <CardBody className="space-y-1">
            <KeyValue label="Grade A exposure" value={`≥ ${cfg.stats.grade_a_min_exposure} balls`} mono />
            <KeyValue label="Grade A coverage" value={`≥ ${Math.round(cfg.stats.grade_a_min_coverage * 100)}%`} mono />
            <KeyValue label="Grade B exposure" value={`≥ ${cfg.stats.grade_b_min_exposure} balls`} mono />
            <KeyValue label="Grade B coverage" value={`≥ ${Math.round(cfg.stats.grade_b_min_coverage * 100)}%`} mono />
            <KeyValue label="Grade C exposure" value={`≥ ${cfg.stats.grade_c_min_exposure} balls`} mono />
            <KeyValue label="Volatility penalty" value={cfg.stats.grade_volatility_penalty} mono />
          </CardBody>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Composite weights — batting" subtitle="Renormalised over available components; coverage is reported." />
          <CardBody>
            <DataTable>
              <THead><TH>Component</TH><TH align="right">Weight</TH><TH>What it measures</TH></THead>
              <TBody>
                {Object.entries(cfg.batting_weights).map(([k, v]) => (
                  <tr key={k}>
                    <TD className="font-medium capitalize">{k.replace(/_/g, " ")}</TD>
                    <TD align="right" mono>{dec(Number(v) * 100, 0)}%</TD>
                    <TD className="text-2xs text-ink-soft">{
                      k === "performance" ? "percentile blend of shrunk strike rate, average, boundary % and runs per innings"
                      : k === "consistency" ? "innings-to-innings stability"
                      : k === "reliability" ? "consistency + confidence + cross-season stability"
                      : k === "pressure" ? "situation-tagged performance differential (ball-by-ball only)"
                      : k === "role_adjusted" ? "performance percentile inside the player's role group"
                      : "exposure × coverage × interval width"
                    }</TD>
                  </tr>
                ))}
              </TBody>
            </DataTable>
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Composite weights — bowling" />
          <CardBody>
            <DataTable>
              <THead><TH>Component</TH><TH align="right">Weight</TH><TH>What it measures</TH></THead>
              <TBody>
                {Object.entries(cfg.bowling_weights).map(([k, v]) => (
                  <tr key={k}>
                    <TD className="font-medium capitalize">{k.replace(/_/g, " ")}</TD>
                    <TD align="right" mono>{dec(Number(v) * 100, 0)}%</TD>
                    <TD className="text-2xs text-ink-soft">{
                      k === "performance" ? "blend of containment and wicket-taking scores"
                      : k === "wicket_taking" ? "bowling strike rate + wickets per innings"
                      : k === "economy" ? "economy + dot-ball % + bowling average"
                      : k === "consistency" ? "innings economy dispersion and multi-wicket rate"
                      : k === "pressure" ? "situation-tagged economy differential (ball-by-ball only)"
                      : "exposure × coverage × interval width"
                    }</TD>
                  </tr>
                ))}
              </TBody>
            </DataTable>
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader title="Metric definitions" subtitle="How every headline number is defined, and whether it is direct, derived or requires data this dataset may not have." />
        <DataTable>
          <THead><TH>Metric</TH><TH>Definition</TH><TH>Classification</TH></THead>
          <TBody>
            {DEFINITIONS.map((d) => (
              <tr key={d.metric}>
                <TD className="font-medium whitespace-nowrap">{d.metric}</TD>
                <TD className="whitespace-normal text-ink-soft">{d.definition}</TD>
                <TD className="text-2xs whitespace-nowrap text-ink-faint">{d.type}</TD>
              </tr>
            ))}
          </TBody>
        </DataTable>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Pressure scenario rules" subtitle="Configurable thresholds; changing them changes the tags." />
          <CardBody>
            <DataTable>
              <THead><TH>Rule</TH><TH align="right">Value</TH></THead>
              <TBody>
                {Object.entries(cfg.scenarios).map(([k, v]) => (
                  <tr key={k}><TD className="capitalize">{k.replace(/_/g, " ")}</TD><TD align="right" mono>{String(v)}</TD></tr>
                ))}
              </TBody>
            </DataTable>
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Limitations of this dataset" subtitle="Read before acting on any ranking." />
          <CardBody>
            <ul className="space-y-1.5 text-2xs leading-relaxed text-ink-soft">
              {limitations(bundle).map((l) => <li key={l}>· {l}</li>)}
            </ul>
            <Notice tone="warning">
              Alternative weightings can be tested: the Ranking Stability page re-runs the entire pipeline for perturbed
              priors, weights and eligibility floors and reports how far each player moves.
            </Notice>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
