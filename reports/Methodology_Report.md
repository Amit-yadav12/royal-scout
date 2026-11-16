# SupeRR Selector Season 2 — Methodology Report

**Objective.** Rank the ten most reliable batters and the ten most reliable bowlers under pressure across IPL and T20I cricket from 2022, using only the supplied ball-by-ball data.

**Data actually analysed.** 200,999 deliveries (193,988 in regulation innings of the 141 competitions, 837 matches with ball-by-ball coverage out of 883 scheduled). 1,217 distinct players identified across the ball-by-ball, roster and XI files.

## 1. Pressure: definition and why

A delivery is classified as a **pressure ball** when the batting side's position is materially at stake. Six situational rules are used; a ball is pressure if any one fires, and the firing rule is recorded on every ball so the classification is auditable:

- **CHASE_RATE** — chasing, from over 5 onwards, required rate ≥ 11.0 runs per over.
- **CHASE_LATE** — chasing, from over 15 onwards, required rate ≥ 9.5.
- **COLLAPSE** — 6+ wickets down with at least 12 balls remaining.
- **DEATH_FRAGILE** — over 17 or later with 4+ wickets down.
- **TIGHT_FINISH** — chasing, ≤ 18 balls left, ≤ 30 needed, required rate ≥ 8.0.
- A chase that can no longer be completed inside the available balls (required rate above 18) is **excluded**: a lost match is a formality, not pressure.
- **Stakes** (knockout matches, closing overs) are used as an intensity multiplier, not as a trigger, so the pressure/no-pressure split stays verifiable.

This tags **27.1%** of regulation deliveries (52,510 balls: 19,300 in first innings, 33,210 in chases).

### Proof that the definition captures harder cricket

| Situation | Balls | Share | Runs / over | Wickets / 100 balls | Boundary % |
|---|---|---|---|---|---|
| NONE | 141478 | 0.729 | 8.67 | 4.56 | 12.03 |
| CHASE_RATE | 27321 | 0.141 | 9.39 | 7.25 | 10.56 |
| DEATH_FRAGILE | 15021 | 0.077 | 10.77 | 9.43 | 12.46 |
| COLLAPSE | 7821 | 0.040 | 7.43 | 5.82 | 7.81 |
| CHASE_LATE | 1828 | 0.009 | 9.83 | 7.17 | 11.93 |
| TIGHT_FINISH | 519 | 0.003 | 10.23 | 7.32 | 11.56 |

Outside the tags: 8.67 runs per over and 4.56 wickets per 100 balls. Inside: 9.51 and 7.66. Every rule except COLLAPSE also raises scoring rate; collapse states suppress scoring while raising risk, which is exactly the rebuild-under-threat situation it is meant to capture.

## 2. Performance measurement

**Situation-adjusted par.** For every delivery the dataset's own average is computed for the exact state it was bowled in — competition (IPL / T20I), innings, over bucket (1-6, 7-10, 11-15, 16-18, 19-20) and wickets-lost bucket (0, 1-2, 3-4, 5-6, 7-9). A finisher batting in the 19th over is therefore measured against 19th-over par, not against an opener's par.

Each player gets three blocks:

- **LEVEL** — runs above par and wickets avoided relative to par, per 100 pressure balls (bowlers: runs conceded below par and wickets above par).
- **LIFT** — the same player's pressure rate against their own non-pressure rate (strike rate and dismissal rate for batters, economy and strike rate for bowlers).
- **CONSISTENCY** — the share of pressure innings (≥6 pressure balls) in which the player beat their own baseline, Laplace-smoothed.

**Shrinkage.** Rates are shrunk toward the pool mean by sample size (λ = n / (n + 120) for lift, n / (n + 60) for level), so a 120-ball cameo cannot outrank a 600-ball body of work on noise.

**Rating.** PRI = 50 + 12.5 × (0.55·z(LEVEL) + 0.30·z(LIFT) + 0.15·z(CONSISTENCY)), clipped to 0-100. Weights were stress-tested (section 6).

## 3. Fair comparisons

- **Eligibility.** ≥120 pressure balls, ≥6 pressure matches, ≥8 scored pressure innings, and ≥60 non-pressure balls (a "usual level" must exist to compare against). Result: 91 eligible batters and 132 eligible bowlers out of the full population.
- **Competitions.** Primary pool is IPL and T20I, the two competitions named in the brief. Adding the second-tier T20 tournaments present in the pack is a sensitivity variant, not part of the primary ranking.
- **Rain-affected chases.** Where a chase was shortened and no revised target is supplied, the target cannot be reconstructed, so chase-based rules are switched off for those innings (8 innings) rather than guessed.
- **Super overs** are excluded from regulation analysis (38 deliveries) but reported.
- **Player identity.** One duplicate profile found and merged — see the audit report.

## 4. Results: the final twenty

### Top 10 batters

| # | Player | PRI | Pressure balls | Pressure SR | Baseline SR | Consistency | Seasons above baseline | Seasons | P(top-10) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Shashank Singh | 67.03 | 380 | 183.16 | 116.11 | 0.75 | 4 | 4 | 0.68 |
| 2 | Babar Azam | 66.69 | 147 | 190.48 | 125.05 | 0.80 | 2 | 2 | 0.68 |
| 3 | Romario Shepherd | 65.20 | 575 | 162.96 | 108.93 | 0.82 | 5 | 5 | 0.61 |
| 4 | Glenn Maxwell | 64.28 | 224 | 193.30 | 151.09 | 0.71 | 3 | 4 | 0.54 |
| 5 | Naman Dhir | 64.19 | 225 | 206.67 | 145.17 | 0.85 | 3 | 3 | 0.48 |
| 6 | Donovan Ferreira | 63.93 | 176 | 197.73 | 128.14 | 0.75 | 3 | 3 | 0.52 |
| 7 | Reeza Hendricks | 63.31 | 192 | 185.94 | 134.84 | 0.64 | 3 | 3 | 0.45 |
| 8 | Shreyas Iyer | 62.62 | 316 | 193.99 | 144.80 | 0.85 | 4 | 4 | 0.39 |
| 9 | Gareth Delany | 61.91 | 180 | 157.22 | 85.34 | 0.87 | 4 | 4 | 0.41 |
| 10 | Namboori Tilak Varma | 61.25 | 684 | 179.53 | 129.82 | 0.82 | 5 | 5 | 0.37 |
### Top 10 bowlers

| # | Player | PRI | Pressure balls | Pressure econ | Baseline econ | Wickets / 100 | Consistency | Seasons above baseline | P(top-10) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Mohammad Nawaz | 73.98 | 181 | 5.50 | 7.48 | 10.50 | 0.76 | 3 | 3 | 0.76 |
| 2 | Gerald Coetzee | 71.38 | 170 | 8.33 | 10.18 | 10.59 | 0.74 | 3 | 4 | 0.71 |
| 3 | Abrar Ahmed | 68.99 | 256 | 5.09 | 7.49 | 7.03 | 0.72 | 3 | 3 | 0.63 |
| 4 | Jasprit Bumrah | 67.49 | 616 | 7.17 | 7.32 | 7.63 | 0.61 | 3 | 5 | 0.52 |
| 5 | Jamie Overton | 67.36 | 184 | 7.79 | 9.18 | 10.33 | 0.72 | 3 | 3 | 0.49 |
| 6 | Sunil Narine | 66.22 | 367 | 6.23 | 7.08 | 5.45 | 0.69 | 4 | 5 | 0.41 |
| 7 | Sufiyan Muqeem | 65.69 | 132 | 6.27 | 6.62 | 9.85 | 0.75 | 2 | 2 | 0.45 |
| 8 | Matheesha Pathirana | 65.58 | 574 | 8.86 | 8.84 | 9.23 | 0.55 | 3 | 4 | 0.37 |
| 9 | Shadab Khan | 64.76 | 213 | 6.85 | 8.28 | 7.98 | 0.71 | 3 | 4 | 0.39 |
| 10 | Kuldeep Yadav | 62.15 | 564 | 7.99 | 8.03 | 8.33 | 0.58 | 3 | 5 | 0.23 |

**Statistical shortlist gates.** A player passes the robustness gate if (a) their median rank across the available alternative methods is 15 or better, and (b) their pressure record replicates in at least two seasons. Both gates are applied before the final statistical shortlist is cut. Passing these analytical gates does **not** confirm inclusion in the official competition dropdown or IPL 2027 auction availability; those require separate verification.

- Bowlers passed over by the gates: Sakib Hussain (#9).
## 5. Reliability

Each player is re-scored on 200 match-level bootstrap resamples (whole matches resampled with replacement, eligibility fixed). `P(top-10)` is the share of resamples in which the player stays inside the ten; `rank_p05`/`rank_p95` bracket the rank. Individual ordering below the top few is noisy — this is a property of 120-600-ball samples, not of the model, and it is reported rather than hidden.

Season-by-season replication, leave-one-match-out stability, alternative weightings, alternative thresholds, alternative pressure definitions and single-competition rankings are all in the audit report and in `reports/*.csv`.

## 6. Robustness of the ranking as a whole

**Batters** — agreement with the primary method:

| Method | Eligible | Top-10 overlap | Spearman ρ | Note |
|---|---|---|---|---|
| primary | 91 | 10 | 1.00 |  |
| loose_thresholds | 147 | 7 | 1.00 |  |
| tight_thresholds | 55 | 5 | 1.00 |  |
| no_shrinkage | 91 | 9 | 1.00 |  |
| equal_weights | 91 | 9 | 0.95 |  |
| lift_heavy | 91 | 7 | 0.95 |  |
| level_heavy | 91 | 9 | 0.97 |  |
| level_only | 91 | 7 | 0.87 |  |
| lift_only | 91 | 5 | 0.87 |  |
| raw_pressure_level | 91 | 6 | 0.68 |  |
| ipl_only | 77 | 3 | 0.82 |  |
| t20i_only | 88 | 6 | 0.73 |  |
| knockouts_only | 1 | 0 | nan | only 1 eligible players |
| include_other_t20 | 91 | 9 | 1.00 |  |
| pressure_v2_wide | 116 | 8 | 0.92 |  |
| pressure_v3_rate_gap | 99 | 7 | 0.86 |  |
| knockouts_only | 0 | 0 | nan | only 1 eligible players |

**Bowlers** — agreement with the primary method:

| Method | Eligible | Top-10 overlap | Spearman ρ | Note |
|---|---|---|---|---|
| primary | 132 | 10 | 1.00 |  |
| loose_thresholds | 194 | 6 | 1.00 |  |
| tight_thresholds | 78 | 5 | 1.00 |  |
| no_shrinkage | 132 | 9 | 1.00 |  |
| equal_weights | 132 | 8 | 0.97 |  |
| lift_heavy | 132 | 7 | 0.97 |  |
| level_heavy | 132 | 10 | 0.99 |  |
| level_only | 132 | 9 | 0.95 |  |
| lift_only | 132 | 5 | 0.93 |  |
| raw_pressure_level | 132 | 7 | 0.74 |  |
| ipl_only | 106 | 5 | 0.84 |  |
| t20i_only | 135 | 5 | 0.76 |  |
| knockouts_only | 1 | 0 | nan | only 1 eligible players |
| include_other_t20 | 133 | 9 | 1.00 |  |
| pressure_v2_wide | 146 | 7 | 0.93 |  |
| pressure_v3_rate_gap | 133 | 8 | 0.89 |  |
| knockouts_only | 0 | 0 | nan | only 1 eligible players |

## 7. Limitations

- Pressure is a *situational* construct. It cannot see a player's internal state, only the match state; a batter who feels pressure in an easy chase is invisible to this method.
- Fielding is not modelled (no fielding data), so a dropped catch under pressure leaves no trace.
- Bowling workload and spell context (over number within a spell, match-ups, batter handedness) are not used beyond what the state variables capture.
- Toss/pitch/venue effects are not modelled; par is pooled across venues.
- Knockout-only analysis is not identifiable: the pack contains 31 knockout matches and, after eligibility, fewer than 2 qualifying players, so it is reported as a failure rather than a result.
- The last two seasons are incomplete for some players, which widens their intervals.

## 8. Reproducibility

```
cd engine
python scripts/superr_audit.py --data ../data/real --out ../reports --bootstrap 400
python scripts/superr_report.py --reports ../reports
```

Code: `engine/royalscout/superr/{load,validate,verify,pressure,metrics,rank}.py`. Artefacts: `reports/`. Every figure in this document is regenerated by those two commands from the six delivered CSVs.
