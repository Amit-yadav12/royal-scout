import Link from "next/link";
import { loadDashboardDataset } from "@/lib/server-dataset";
import { notFound } from "next/navigation";
import { ArrowLeft, Fingerprint, Gauge, ShieldAlert, TrendingUp } from "lucide-react";
import { hasBundle } from "@/lib/bundle";
import { dec, num, pct, scoreTone, shortDate } from "@/lib/format";
import { PageHeader } from "@/components/shell";
import { Card, CardBody, CardHeader, KeyValue, Stat } from "@/components/ui/card";
import { Badge, GradeBadge } from "@/components/ui/badge";
import { EmptyState, Notice } from "@/components/ui/empty";
import { DataTable, TBody, TD, TH, THead } from "@/components/ui/table";
import { MiniBar } from "@/components/charts/bars";
import { TrendChart } from "@/components/charts/line";
import { PlayerRadar } from "@/components/charts/radar";

export const dynamicParams = true;

/** Percentile of a value inside a peer population (mid-rank, matching the engine). */
function percentile(values: number[], value: number | null): number | null {
  if (value === null || !values.length) return null;
  const below = values.filter((v) => v < value).length;
  const equal = values.filter((v) => v === value).length;
  return ((below + equal / 2) / values.length) * 100;
}

function Finding({ label, value, pct: p, unit, note }: { label: string; value: string; pct: number | null; unit?: string; note: string }) {
  const tone = p === null ? "text-ink-faint" : p >= 75 ? "text-emerald-700" : p >= 40 ? "text-sky-700" : "text-rose-700";
  return (
    <li className="rounded border border-surface-line bg-surface-muted/50 px-2.5 py-2">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-xs font-medium text-ink">{label}</span>
        <span className={`font-mono text-xs tabular-nums ${tone}`}>
          {value}{unit ? <span className="text-2xs text-ink-faint"> {unit}</span> : null}
          {p !== null ? <span className="ml-1 text-2xs text-ink-faint">· p{Math.round(p)}</span> : null}
        </span>
      </div>
      <p className="mt-0.5 text-2xs leading-relaxed text-ink-soft">{note}</p>
    </li>
  );
}

export default async function PlayerPage({ params }: { params: Promise<{ name: string }> }) {
  const bundle = (await loadDashboardDataset()).bundle;
  const { name: rawName } = await params;
  const name = decodeURIComponent(rawName);
  if (!hasBundle(bundle)) return <EmptyState tone="warning" title="No dataset" description="No bundle has been generated yet." />;

  const batting = bundle.batting.players[name] ?? null;
  const bowling = bundle.bowling.players[name] ?? null;
  const role = bundle.roles[name] ?? null;
  const attrs = bundle.schema.player_attributes[name] ?? {};
  if (!batting && !bowling && !role) notFound();

  const batPeers = Object.values(bundle.batting.players).filter((r) => (r.exposure_balls ?? 0) > 0);
  const bowlPeers = Object.values(bundle.bowling.players).filter((r) => (r.exposure_balls ?? 0) > 0);
  const numList = (rows: typeof batPeers, key: keyof (typeof batPeers)[number]) =>
    rows.map((r) => r[key]).filter((v): v is number => typeof v === "number");

  const pressureDetail = (bundle.pressure.batting[name] ?? bundle.pressure.bowling[name]) ?? null;
  const phasesBat = bundle.pressure.phases?.batting?.[name] ?? null;
  const phasesBowl = bundle.pressure.phases?.bowling?.[name] ?? null;

  const seasonKeys = ["by_season"] as const;
  const seasonRows = Object.entries(bundle.batting.splits.by_season ?? {})
    .filter(([k]) => k.startsWith(`${name}|`))
    .map(([k, v]) => ({ season: k.split("|")[1], strike_rate: v.strike_rate, runs: v.runs, innings: v.innings }))
    .sort((a, b) => String(a.season).localeCompare(String(b.season)));
  const seasonBowlRows = Object.entries(bundle.bowling.splits.by_season ?? {})
    .filter(([k]) => k.startsWith(`${name}|`))
    .map(([k, v]) => ({ season: k.split("|")[1], economy: v.economy, wickets: v.wickets }))
    .sort((a, b) => String(a.season).localeCompare(String(b.season)));

  const components = [
    { label: "Performance", value: batting?.performance_score ?? bowling?.performance_score ?? null },
    { label: "Consistency", value: batting?.consistency ?? bowling?.consistency ?? null },
    { label: "Reliability", value: batting?.reliability ?? bowling?.reliability ?? null },
    { label: "Pressure", value: batting?.pressure_score ?? bowling?.pressure_score ?? null },
    { label: "Role-adjusted", value: batting?.role_adjusted_score ?? null },
    { label: "Confidence", value: batting?.confidence_score ?? bowling?.confidence_score ?? null },
    { label: "Wicket-taking", value: bowling?.wicket_taking_score ?? null },
    { label: "Containment", value: bowling?.economy_containment_score ?? null },
  ];

  return (
    <div className="space-y-4">
      <Link href="/players" className="inline-flex items-center gap-1 text-2xs text-ink-soft hover:text-royal-pink">
        <ArrowLeft className="h-3 w-3" /> Back to Player Explorer
      </Link>

      <PageHeader
        title={name}
        description={`${(batting?.teams ?? bowling?.teams ?? []).join(", ") || "Team not stated"} · ${
          role?.primary_role ?? "role not established"
        }${role?.secondary_role ? ` / ${role.secondary_role}` : ""} · role basis: ${
          role?.role_basis ?? "unknown"
        } · competitions: ${(batting?.competitions ?? bowling?.competitions ?? []).join(", ") || "—"}`}
        actions={
          <div className="flex items-center gap-2">
            <Link href={`/compare?players=${encodeURIComponent(name)}`} className="btn">Add to comparison</Link>
            <GradeBadge grade={batting?.grade ?? bowling?.grade} />
          </div>
        }
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Stat label="Balls faced" value={num(batting?.balls_faced ?? null)} hint={`${num(batting?.innings ?? 0)} innings`} />
        <Stat label="Runs" value={num(batting?.runs ?? null)} hint={batting?.highest_score ? `HS ${batting.highest_score}` : undefined} />
        <Stat label="Average" value={dec(batting?.average ?? null)} hint={`${num(batting?.dismissals ?? null)} dismissals`} />
        <Stat label="Strike rate" value={dec(batting?.strike_rate ?? null, 1)} hint={`boundary ${pct(batting?.boundary_pct ?? null, 1)}`} />
        <Stat label="Legal balls bowled" value={num(bowling?.legal_balls ?? null)} hint={bowling?.overs ? `${bowling.overs} overs` : undefined} />
        <Stat label="Wickets / economy" value={`${num(bowling?.wickets ?? null)} / ${dec(bowling?.economy ?? null)}`} hint={bowling?.best_bowling ? `best ${bowling.best_bowling}` : undefined} />
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Card>
          <CardHeader title="Score decomposition" subtitle="Every component on the 0–100 population scale. An absent bar means the data cannot support it." />
          <CardBody className="space-y-2">
            {components.map((c) => (
              <div key={c.label}>
                <div className="flex items-baseline justify-between text-2xs">
                  <span className="text-ink-soft">{c.label}</span>
                  <span className={`font-mono tabular-nums ${scoreTone(c.value)}`}>{c.value === null ? "unavailable" : c.value.toFixed(1)}</span>
                </div>
                <MiniBar value={c.value} showValue={false} colour={(c.value ?? 0) >= 70 ? "#0F766E" : (c.value ?? 0) >= 45 ? "#1B4B8F" : "#C9A227"} />
              </div>
            ))}
            <div className="mt-2 space-y-0.5 border-t border-surface-line pt-2">
              <KeyValue label="Batting index (RABI)" value={dec(batting?.rabi ?? null, 1)} mono />
              <KeyValue label="Bowling index" value={dec(bowling?.rabi_bowl ?? null, 1)} mono />
              <KeyValue label="Composite coverage" value={batting ? pct((batting.score_coverage ?? 0) * 100, 0) : bowling ? pct((bowling.score_coverage ?? 0) * 100, 0) : "—"} mono />
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Component profile" subtitle="Normalised 0–100 scores; only available components are plotted." />
          <CardBody>
            <PlayerRadar
              metrics={components.filter((c) => c.value !== null).map((c) => c.label)}
              series={[{ name, values: components.filter((c) => c.value !== null).map((c) => c.value) }]}
              height={300}
            />
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Confidence & sample" subtitle="Why this grade, in the engine's own words." />
          <CardBody className="space-y-1.5">
            <div className="flex items-center gap-2">
              <GradeBadge grade={batting?.grade ?? bowling?.grade} />
              <span className="text-xs text-ink-soft">
                confidence score {dec((batting?.confidence_score ?? bowling?.confidence_score) ?? null, 1)}
              </span>
            </div>
            {(batting?.confidence?.reasons ?? bowling?.confidence?.reasons ?? []).map((r, i) => (
              <p key={i} className="border-l-2 border-surface-line pl-2 text-2xs leading-relaxed text-ink-soft">{r}</p>
            ))}
            <div className="mt-1 space-y-0.5 border-t border-surface-line pt-1.5">
              <KeyValue label="Batting granularity" value={batting?.granularity ?? "—"} mono />
              <KeyValue label="Bowling granularity" value={bowling?.granularity ?? "—"} mono />
              <KeyValue label="Derived exposure rows" value={num((batting as any)?.derived_exposure_records ?? 0)} mono />
            </div>
          </CardBody>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Strengths" subtitle="Each line is a measured value with its percentile in this dataset — no narrative invented beyond the numbers." />
          <CardBody>
            <ul className="space-y-1.5">
              <Finding
                label="Strike rate"
                value={dec(batting?.strike_rate ?? null, 1)}
                pct={percentile(numList(batPeers, "strike_rate"), batting?.strike_rate ?? null)}
                note={`Against ${batPeers.length} batters with a batting record in this dataset.`}
              />
              <Finding
                label="Batting average"
                value={dec(batting?.average ?? null)}
                pct={percentile(numList(batPeers, "average"), batting?.average ?? null)}
                note="Runs per completed dismissal; not-outs are excluded from the denominator, never counted as dismissals."
              />
              {bowling ? (
                <Finding
                  label="Economy (lower is better)"
                  value={dec(bowling.economy ?? null, 2)}
                  pct={percentile(numList(bowlPeers, "economy").map((v) => -v), bowling.economy === null || bowling.economy === undefined ? null : -bowling.economy)}
                  note={`Against ${bowlPeers.length} bowlers. Percentile is inverted so a high number always means better.`}
                />
              ) : null}
              {bowling ? (
                <Finding
                  label="Wickets per innings"
                  value={dec(bowling.wickets_per_innings, 3)}
                  pct={percentile(numList(bowlPeers, "wickets_per_innings"), bowling.wickets_per_innings ?? null)}
                  note="Wicket-taking is scored separately from economy so a containing bowler is never mistaken for a strike bowler."
                />
              ) : null}
              <Finding
                label="Consistency"
                value={dec(batting?.consistency ?? bowling?.consistency ?? null, 1)}
                pct={percentile(numList(batPeers, "consistency"), batting?.consistency ?? bowling?.consistency ?? null)}
                note={(batting?.consistency_detail?.basis as string) === "aggregate_dispersion"
                  ? "Computed across season aggregates — this is NOT match-level consistency."
                  : "Innings-to-innings dispersion, converted from the coefficient of variation and percentile-ranked."}
              />
            </ul>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Weaknesses & caveats" subtitle="Stated plainly, including what could not be measured." />
          <CardBody>
            <ul className="space-y-1.5 text-2xs leading-relaxed text-ink-soft">
              {batting?.dot_pct !== null && batting?.dot_pct !== undefined ? (
                <li>· Dot-ball share {pct(batting.dot_pct, 1)} — {batting.dot_pct > 45 ? "high; scoring depends on a small number of big hits" : "controlled; keeps the innings moving"}.</li>
              ) : null}
              {batting && batting.scores_50 !== null && batting.scores_50 !== undefined ? (
                <li>· {batting.scores_50} fifty-plus score(s) from {batting.innings} innings ({pct(((batting.scores_50 ?? 0) / Math.max(1, batting.innings)) * 100, 1)} conversion).</li>
              ) : null}
              {batting?.pressure_score === null || batting?.pressure_score === undefined ? (
                <li>· Pressure performance is <strong className="text-ink">unavailable</strong>: this player is not covered by the delivery-level stream, so the pressure component is excluded from the composite and the coverage figure drops rather than being estimated.</li>
              ) : null}
              {Object.entries(batting?.unavailable ?? {}).map(([k, v]) => (
                <li key={k}>· {k.replace(/_/g, " ")}: {v as string}</li>
              ))}
              {Object.entries(bowling?.unavailable ?? {}).map(([k, v]) => (
                <li key={`b-${k}`}>· {k.replace(/_/g, " ")}: {v as string}</li>
              ))}
              {role?.keeper_confidence === "unverified" ? (
                <li>· Wicketkeeping record is <strong className="text-ink">unverified</strong> — no declared role or dismissal type supports it.</li>
              ) : null}
              {(batting?.exposure_balls ?? 0) < 150 ? (
                <li>· Sample is below the ranked threshold of 150 balls; treat every rate metric as provisional.</li>
              ) : null}
            </ul>
          </CardBody>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Season progression" subtitle="Strike rate and runs by season, from record-level splits." />
          <CardBody>
            {seasonRows.length > 1 ? (
              <TrendChart data={seasonRows} xKey="season" series={[{ key: "strike_rate", label: "Strike rate" }, { key: "runs", label: "Runs" }]} height={260} />
            ) : (
              <Notice>Only {seasonRows.length} season(s) of batting data exist for this player, so a trend cannot be drawn.</Notice>
            )}
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Bowling by season" subtitle="Economy and wickets; lower economy is better." />
          <CardBody>
            {seasonBowlRows.length > 1 ? (
              <TrendChart data={seasonBowlRows} xKey="season" series={[{ key: "economy", label: "Economy" }, { key: "wickets", label: "Wickets" }]} height={260} />
            ) : (
              <Notice>Not enough bowling seasons to plot a progression.</Notice>
            )}
          </CardBody>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Phase profile" subtitle="Derived from delivery-level data only. A phase split is not a pressure measure." />
          <CardBody>
            {phasesBat || phasesBowl ? (
              <DataTable>
                <THead>
                  <TH>Phase</TH>
                  <TH align="right">Balls</TH>
                  <TH align="right">Runs</TH>
                  <TH align="right">SR / Econ</TH>
                  <TH align="right">Boundary % / Dot %</TH>
                </THead>
                <TBody>
                  {(["powerplay", "middle", "death"] as const).map((phase) => {
                    const b1 = phasesBat?.[phase];
                    const b2 = phasesBowl?.[phase];
                    if (!b1 && !b2) return null;
                    return (
                      <tr key={phase}>
                        <TD className="font-medium capitalize">{phase === "middle" ? "Middle (7–15)" : phase === "death" ? "Death (16–20)" : "Powerplay (1–6)"}</TD>
                        <TD align="right" mono>{num(b1?.balls ?? b2?.balls)}</TD>
                        <TD align="right" mono>{num(b1?.runs ?? b2?.runs_conceded)}</TD>
                        <TD align="right" mono>{dec(b1?.strike_rate ?? b2?.economy, 2)}</TD>
                        <TD align="right" mono>{pct(b1?.boundary_pct ?? b2?.dot_pct, 1)}</TD>
                      </tr>
                    );
                  })}
                </TBody>
              </DataTable>
            ) : (
              <Notice tone="warning">No delivery-level data covers this player, so phase performance cannot be computed.</Notice>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Pressure performance" subtitle="Only shown when the situation-level record supports it." />
          <CardBody>
            {pressureDetail && pressureDetail.score !== null ? (
              <div className="space-y-1">
                <div className="flex items-baseline justify-between">
                  <span className="text-xs text-ink-soft">Pressure score</span>
                  <span className={`font-mono text-lg font-semibold ${scoreTone(pressureDetail.score)}`}>{dec(pressureDetail.score, 1)}</span>
                </div>
                <div className="space-y-0.5">
                  {Object.entries(pressureDetail.detail ?? {})
                    .filter(([k]) => !["scenario_counts", "explanation"].includes(k))
                    .map(([k, v]) => (
                      <KeyValue key={k} label={k.replace(/_/g, " ")} value={typeof v === "number" ? String(v) : typeof v === "string" ? v : JSON.stringify(v)} mono={typeof v === "number"} />
                    ))}
                </div>
                {pressureDetail.detail?.explanation ? (
                  <p className="mt-1 text-2xs leading-relaxed text-ink-soft">{pressureDetail.detail.explanation as string}</p>
                ) : null}
                {pressureDetail.detail?.scenario_counts ? (
                  <div className="mt-1 flex flex-wrap gap-1">
                    {Object.entries(pressureDetail.detail.scenario_counts as Record<string, number>).map(([k, v]) => (
                      <Badge key={k} tone="info">{k.replace(/_/g, " ")} · {v}</Badge>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : (
              <Notice tone="warning">
                Pressure performance is unavailable for this player. The engine will not substitute an aggregate proxy for a
                match-pressure claim.
              </Notice>
            )}
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader title="Evidence trail" subtitle="Everything needed to reproduce this dossier." action={<Fingerprint className="h-4 w-4 text-ink-faint" />} />
        <CardBody className="grid gap-x-6 gap-y-1 sm:grid-cols-2 lg:grid-cols-3">
          <KeyValue label="Dataset" value={bundle.meta.name} />
          <KeyValue label="Dataset ID" value={<span className="font-mono text-2xs">{bundle.meta.dataset_id}</span>} />
          <KeyValue label="Analysed" value={shortDate(bundle.meta.created_at)} />
          <KeyValue label="Model version" value={bundle.meta.model_version} mono />
          <KeyValue label="Config fingerprint" value={<span className="font-mono text-2xs">{bundle.meta.config_fingerprint}</span>} />
          <KeyValue label="Records contributing" value={num((batting?.records ?? 0) + (bowling?.records ?? 0))} mono />
          <KeyValue label="Competitions" value={(batting?.competitions ?? bowling?.competitions ?? []).join(", ") || "—"} />
          <KeyValue label="Seasons" value={(batting?.seasons ?? bowling?.seasons ?? []).join(", ") || "—"} />
          <KeyValue label="Batting hand" value={attrs.batting_hand ?? "not declared"} />
          <KeyValue label="Bowling style" value={attrs.bowling_style ?? "not declared"} />
          <KeyValue label="Fixture data" value={bundle.meta.is_fixture ? "yes — synthetic" : "no"} />
        </CardBody>
      </Card>

      <div className="flex flex-wrap gap-2">
        <a className="btn" href={`/api/export?discipline=batting&limit=500`}>Download batting dataset CSV</a>
        <Link className="btn" href="/exports">Export centre</Link>
        <Link className="btn" href="/methodology">How the score is built</Link>
      </div>
    </div>
  );
}
