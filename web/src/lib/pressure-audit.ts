import selection from "@/data/final_selection.json";
import facts from "@/data/audit_facts.json";

export type FinalPick = {
  rank: number;
  player_name: string;
  pri: number;
  p_balls: number;
  pressure_innings?: number;
  consistency?: number;
  p_top10?: number;
  rank_median?: number;
  rank_p05?: number;
  rank_p95?: number;
  median_rank_across_methods?: number;
  methods_with_top10?: number;
  methods_available?: number;
  seasons_above_baseline?: number;
  seasons_evaluated?: number;
  confirmed?: boolean;
  eligibility_status?: "confirmed" | "unavailable" | "unverified" | "ineligible";
  p_sr?: number; base_sr?: number; lift_sr?: number;
  p_econ?: number; base_econ?: number; lift_econ?: number; p_wk_rate?: number;
};

export type AuditFacts = typeof facts;

export const auditFacts: AuditFacts = facts as AuditFacts;
export const finalBatters = (selection as { batters: FinalPick[] }).batters;
export const finalBowlers = (selection as { bowlers: FinalPick[] }).bowlers;
