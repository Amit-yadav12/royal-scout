import { ShieldCheck, ShieldAlert } from "lucide-react";
import { auditFacts, finalBatters, finalBowlers, type FinalPick } from "@/lib/pressure-audit";
import { dec, num } from "@/lib/format";
import { PageHeader } from "@/components/shell";
import { Card, CardBody, CardHeader, KeyValue, Stat } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { DataTable, TBody, TD, TH, THead } from "@/components/ui/table";

function PickTable({ rows, role }: { rows: FinalPick[]; role: "bat" | "bowl" }) {
  return (
    <DataTable>
      <THead>
        <tr>
          <TH>#</TH>
          <TH>Player</TH>
          <TH className="text-right">PRI</TH>
          <TH className="text-right">Balls</TH>
          <TH className="text-right">{role === "bat" ? "Press SR" : "Press econ"}</TH>
          <TH className="text-right">Consistency</TH>
          <TH>Gate</TH>
        </tr>
      </THead>
      <TBody>
        {rows.map((r) => (
          <tr key={`${role}-${r.player_name}`}>
            <TD className="font-mono">{r.rank}</TD>
            <TD className="font-medium">{r.player_name}</TD>
            <TD className="text-right font-mono">{dec(r.pri, 1)}</TD>
            <TD className="text-right font-mono">{num(r.p_balls)}</TD>
            <TD className="text-right font-mono">{dec(role === "bat" ? r.p_sr : r.p_econ, 2)}</TD>
            <TD className="text-right font-mono">{dec((r.consistency ?? 0) * 100, 0)}%</TD>
            <TD>
              {r.eligibility_status === "confirmed" || r.confirmed === true ? (
                <Badge tone="positive">verified eligible</Badge>
              ) : r.eligibility_status === "ineligible" ? (
                <Badge tone="danger">not eligible</Badge>
              ) : (
                <Badge tone="warning">eligibility unverified</Badge>
              )}
            </TD>
          </tr>
        ))}
      </TBody>
    </DataTable>
  );
}

export default function PressureAuditPage() {
  const v = auditFacts.validation;
  return (
    <div className="space-y-4">
      <PageHeader
        title="Pressure Ranking — audited final twenty"
        description="Pressure-performance recommendations ranked from the supplied dataset. Auction availability and the official candidate dropdown are not verified by historical match data."
      />

      <div className="grid gap-4 md:grid-cols-4">
        <Stat label="Deliveries analysed" value={num(auditFacts.deliveries_used)} hint={`of ${num(auditFacts.deliveries)} in the pack`} />
        <Stat label="Pressure balls" value={num(auditFacts.pressure_balls)} hint={`${dec(auditFacts.pressure_share * 100, 1)}% of regulation deliveries`} />
        <Stat label="Pressure wickets / 100" value={dec(auditFacts.pressure_wickets_per_100, 2)} hint={`vs ${dec(auditFacts.nonpressure_wickets_per_100, 2)} outside`} />
        <Stat label="Validation checks" value={`${v.pass}/${v.total}`} hint={`${v.fail} failing, each documented`} />
      </div>

      <div className="grid gap-4">
        <Card>
          <CardHeader title="Top 10 batters under pressure" subtitle="PRI — pressure reliability index (0-100); statistical shortlist, not verified auction availability" />
          <CardBody>
            <PickTable rows={finalBatters} role="bat" />
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Top 10 bowlers under pressure" subtitle="PRI — pressure reliability index (0-100); statistical shortlist, not verified auction availability" />
          <CardBody>
            <PickTable rows={finalBowlers} role="bowl" />
          </CardBody>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="How the ranking is built" subtitle="auditable, reproducible, no hand-weights" />
          <CardBody>
            <KeyValue label="Pressure rules" value="same-innings chase rate, chase late, collapse, death fragility, tight finish" />
            <KeyValue label="Level block" value="runs above situation par, wickets avoided (55%)" />
            <KeyValue label="Lift block" value="pressure vs own non-pressure baseline (30%)" />
            <KeyValue label="Consistency block" value="share of pressure innings beating own baseline (15%)" />
            <KeyValue label="Statistical eligibility" value={`${auditFacts.eligible.bat} batters / ${auditFacts.eligible.bowl} bowlers`} />
            <KeyValue label="Auction availability" value="Not verified — requires the official candidate / auction register" />
            <KeyValue label="Gates" value="median rank ≤15 across 15 methods; ≥2 seasons of pressure evidence" />
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Audit status" subtitle="what passed, what did not" />
          <CardBody>
            <div className="flex items-center gap-2 pb-2">
              {v.fail === 0 ? <ShieldCheck className="h-5 w-5 text-emerald-500" /> : <ShieldAlert className="h-5 w-5 text-amber-500" />}
              <span className="text-sm">
                {v.pass} of {v.total} structural and cricket-correctness checks pass; {v.fail} fail and are documented.
              </span>
            </div>
            <KeyValue label="Identity merges" value={`${auditFacts.identity_merges.length} duplicate profile merged`} />
            <KeyValue label="Matches without deliveries" value="16, all recorded as abandoned" />
            <KeyValue label="Rain-shortened chases excluded" value={num(auditFacts.chase_target_unknown_innings)} />
            <KeyValue label="Super-over deliveries excluded" value={num(auditFacts.super_over_deliveries)} />
            <KeyValue label="Reports" value="reports/Methodology_Report.md · reports/Audit_Report.md" />
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
