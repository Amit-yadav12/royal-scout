# Royal Scout — Audit Report on the Real SupeRR Data Pack

**Scope.** A full analytical audit of the Royal Scout pressure-ranking application against the actual delivered dataset (six CSVs, 41 MB ball-by-ball), with every error found corrected and every ranking defended against at least one alternative method.

**Verdict up front.** 24 of 27 structural and cricket-correctness checks pass, plus 6 of 6 independent recomputations. 3 checks fail; each is listed below with its cause and either a correction or an explicit statement that it cannot be corrected from the supplied data.

## 1. What was tested

| Area | Test | Result |
|---|---|---|
| matches_without_ball_data | Every match without deliveries is an abandoned match (no coverage gap) | PASS |
| duplicate_deliveries | Delivery key uniqueness (match, innings, over, ball) | PASS |
| duplicate_innings_ball | innings_ball_num is unique inside an innings | PASS |
| super_overs | Super overs identified and separable | PASS |
| run_margin_matches_result | Innings totals reproduce the 'won by N runs' margin in the result text | PASS |
| wicket_margin_matches_result | Wickets lost in the chase reproduce 'won by N wickets' | **FAIL** |
| legal_balls_within_innings_length | Legal deliveries per innings never exceed the innings length (120, or revised overs) | PASS |
| wide_has_no_bat_runs | A wide never records bat runs or a boundary | PASS |
| boundary_flags_consistent | is_four/is_six agree with bat runs (4/6) | PASS |
| non_negative_runs | No negative run values | PASS |
| implausible_ball_runs | No delivery awards more than 7 runs | PASS |
| wickets_within_ten | No innings loses more than 10 wickets | PASS |
| completed_chases_reach_target | A completed chase has runs >= target | PASS |
| id_to_name_conflicts | Each player_id maps to exactly one spelling | PASS |
| name_to_id_conflicts | Each player name maps to exactly one player_id (duplicate-player probe) | **FAIL** |
| roster_name_mismatch | Ball-by-ball names agree with the competition roster file | PASS |
| competition_mix | Competition mix resolved (IPL / T20I / other T20) | PASS |
| unmapped_competitions | Every match maps to a known competition | PASS |
| match_date_within_season | Match dates fall inside the stated competition season | PASS |
| players_appear_in_xi | Every batter/bowler appearing in a match is in that match's playing XI | **FAIL** |
| no_future_matches | No match is dated after the analysis date | PASS |
| row_count | Loaded row count equals the raw file's data rows | PASS |
| run_total | Total runs recomputed row-by-row equals the pipeline's total | PASS |
| run_conservation | Bat runs + extras equal total runs (no run is double counted or lost) | PASS |
| legal_ball_count | Legal deliveries recomputed row-by-row match | PASS |
| dismissal_conservation | Dismissals credited to bowlers plus non-bowler dismissals equal all wickets | PASS |
| player_aggregate_agreement | Per-player bat runs and balls reproduce for the sampled players | PASS |

Independent recomputation re-derives totals with a row-by-row loop over the raw CSV and compares them with the vectorised pipeline: row count, total runs, run conservation (bat + extras = total), legal-ball count, dismissal conservation and per-player aggregates for 25 sampled batters. All six agree.

## 2. Failures found, and what was done about them

**1. wicket_margin_matches_result** — 408 wicket-margin matches verified, 1 mismatch(es)
  Evidence: `[{"match_id": 20190, "wickets": 5, "result": "Lucknow Super Giants Won by 6 wickets", "expected": 4}]`
  Resolution: Source inconsistency in one match (20190): the result string says "won by 6 wickets" while the ball data records 5 dismissals. Runs are unaffected; the match is kept and the discrepancy reported.

**2. name_to_id_conflicts** — 2 name(s) map to multiple ids
  Evidence: `[{"name": "Abdul Samad", "n": 2, "ids": [7446, 6922]}, {"name": "Haider Ali", "n": 2, "ids": [7338, 28756]}]`
  Resolution: Three name collisions investigated: two are genuinely different people (Haider Ali PAK/UAE, Abdul Samad IND/PAK); one is a true duplicate profile (Basil Hameed, ids 8638 and 39444) and is now merged, plus one roster-only duplicate with no deliveries (Habibur Rahman, 5872/16284).

**3. players_appear_in_xi** — 3 player-match appearances missing from playing_eleven
  Evidence: `[{"match_id": 37095, "player_id": 36153, "in_xi": null}, {"match_id": 37092, "player_id": 36153, "in_xi": null}]`
  Resolution: Three matches in the 2024 Emerging Teams Asia Cup list the duplicate Basil Hameed id in the XI while the ball data uses the other id (fixed by the merge); Syed Haider (36153) is genuinely missing from the XI file in those matches and is handled by never requiring XI membership for eligibility.

**Data discrepancies that cannot be fixed from the pack** (reported, not papered over):

- Match 20190 result string disagrees with the wicket count in the ball data.
- 8 rain-shortened chase innings carry no revised target, so required-rate features are switched off for them.
- Syed Haider (id 36153) appears in three matches that do not list him in the XI file.
- Two roster-only duplicate profiles with zero deliveries exist (no statistical effect).

## 3. Methodological audit

### 3.1 Does the ranking depend on the method?

**Batters** — 15 alternatives: weights, shrinkage, thresholds, baseline definition, single-competition universes, two alternative pressure definitions.

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

**Bowlers** — 15 alternatives: weights, shrinkage, thresholds, baseline definition, single-competition universes, two alternative pressure definitions.

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

### 3.2 Does the ranking depend on the sample rule?

**Batters** (pressure-ball floor × baseline-ball floor):

| Pressure balls ≥ | Baseline balls ≥ | Eligible | Top-10 overlap | Spearman ρ |
|---|---|---|---|---|
| 60 | 30 | 106 | 9 | 1.00 |
| 60 | 60 | 101 | 10 | 1.00 |
| 60 | 120 | 91 | 8 | 1.00 |
| 90 | 30 | 106 | 9 | 1.00 |
| 90 | 60 | 101 | 10 | 1.00 |
| 90 | 120 | 91 | 8 | 1.00 |
| 120 | 30 | 94 | 9 | 1.00 |
| 120 | 60 | 91 | 10 | 1.00 |
| 120 | 120 | 82 | 8 | 1.00 |
| 160 | 30 | 78 | 9 | 1.00 |
| 160 | 60 | 75 | 9 | 1.00 |
| 160 | 120 | 70 | 7 | 1.00 |
| 200 | 30 | 61 | 6 | 1.00 |
| 200 | 60 | 59 | 6 | 1.00 |
| 200 | 120 | 56 | 5 | 1.00 |
| 260 | 30 | 42 | 4 | 1.00 |
| 260 | 60 | 41 | 4 | 1.00 |
| 260 | 120 | 38 | 3 | 1.00 |

**Bowlers** (pressure-ball floor × baseline-ball floor):

| Pressure balls ≥ | Baseline balls ≥ | Eligible | Top-10 overlap | Spearman ρ |
|---|---|---|---|---|
| 60 | 30 | 172 | 9 | 1.00 |
| 60 | 60 | 172 | 9 | 1.00 |
| 60 | 120 | 171 | 9 | 1.00 |
| 90 | 30 | 155 | 9 | 1.00 |
| 90 | 60 | 155 | 9 | 1.00 |
| 90 | 120 | 154 | 9 | 1.00 |
| 120 | 30 | 132 | 10 | 1.00 |
| 120 | 60 | 132 | 10 | 1.00 |
| 120 | 120 | 131 | 9 | 1.00 |
| 160 | 30 | 101 | 8 | 1.00 |
| 160 | 60 | 101 | 8 | 1.00 |
| 160 | 120 | 101 | 8 | 1.00 |
| 200 | 30 | 78 | 5 | 1.00 |
| 200 | 60 | 78 | 5 | 1.00 |
| 200 | 120 | 78 | 5 | 1.00 |
| 260 | 30 | 57 | 3 | 1.00 |
| 260 | 60 | 57 | 3 | 1.00 |
| 260 | 120 | 57 | 3 | 1.00 |

### 3.3 Does the ranking depend on one match or one season?

- Batters: removing each leading player's most influential match moves ranks by 0.00 on average; 0 of 15 move more than two places. 10 of 15 stay in the ten.
- Bowlers: removing each leading player's most influential match moves ranks by 0.33 on average; 0 of 15 move more than two places. 10 of 15 stay in the ten.

### 3.4 Adversarial review of the final twenty

Each recommendation is attacked with the strongest evidence available against it.

**Top 10 batters**

| # | Player | PRI | Strongest case against | Verdict |
|---|---|---|---|---|
| 1 | Shashank Singh | 67.03 | 380 pressure balls; 4 season(s) of pressure evidence; outside the top 10 in 1/14 methods (worst: raw_pressure_level #13); worst season lift 36.23; rank moves 0 when their best match is removed | holds |
| 2 | Babar Azam | 66.69 | 147 pressure balls; 2 season(s) of pressure evidence; outside the top 10 in 0/13 methods (worst: lift_only #7); worst season lift 47.16; rank moves 0 when their best match is removed | holds, thin sample |
| 3 | Romario Shepherd | 65.20 | 575 pressure balls; 5 season(s) of pressure evidence; outside the top 10 in 2/13 methods (worst: raw_pressure_level #52); worst season lift 35.77; rank moves 0 when their best match is removed | holds |
| 4 | Glenn Maxwell | 64.28 | 224 pressure balls; 4 season(s) of pressure evidence; outside the top 10 in 3/15 methods (worst: pressure_v3_rate_gap #27); worst season lift -5.38; rank moves 0 when their best match is removed | holds |
| 5 | Naman Dhir | 64.19 | 225 pressure balls; 3 season(s) of pressure evidence; outside the top 10 in 2/14 methods (worst: lift_only #13); worst season lift 52.25; rank moves 0 when their best match is removed | holds |
| 6 | Donovan Ferreira | 63.93 | 176 pressure balls; 3 season(s) of pressure evidence; outside the top 10 in 0/13 methods (worst: loose_thresholds #9); worst season lift 48.0; rank moves 0 when their best match is removed | holds, thin sample |
| 7 | Reeza Hendricks | 63.31 | 192 pressure balls; 3 season(s) of pressure evidence; outside the top 10 in 4/13 methods (worst: lift_only #32); worst season lift 26.28; rank moves 0 when their best match is removed | holds, thin sample |
| 8 | Shreyas Iyer | 62.62 | 316 pressure balls; 4 season(s) of pressure evidence; outside the top 10 in 5/15 methods (worst: pressure_v3_rate_gap #58); worst season lift 15.9; rank moves 0 when their best match is removed | holds |
| 9 | Gareth Delany | 61.91 | 180 pressure balls; 4 season(s) of pressure evidence; outside the top 10 in 5/13 methods (worst: raw_pressure_level #63); worst season lift 11.34; rank moves 0 when their best match is removed | holds, method-sensitive |
| 10 | Namboori Tilak Varma | 61.25 | 684 pressure balls; 5 season(s) of pressure evidence; outside the top 10 in 9/15 methods (worst: pressure_v2_wide #20); worst season lift 10.2; rank moves 0 when their best match is removed | holds, method-sensitive |

**Top 10 bowlers**

| # | Player | PRI | Strongest case against | Verdict |
|---|---|---|---|---|
| 1 | Mohammad Nawaz | 75.02 | 181 pressure balls; 3 season(s) of pressure evidence; outside the top 10 in 0/13 methods (worst: raw_pressure_level #2); worst season lift 1.39; rank moves 0 when their best match is removed | holds, thin sample |
| 2 | Abrar Ahmed | 69.49 | 256 pressure balls; 3 season(s) of pressure evidence; outside the top 10 in 0/14 methods (worst: lift_only #8); worst season lift 1.43; rank moves 0 when their best match is removed | holds |
| 3 | Gerald Coetzee | 69.37 | 170 pressure balls; 4 season(s) of pressure evidence; outside the top 10 in 2/14 methods (worst: raw_pressure_level #32); worst season lift -1.03; rank moves 0 when their best match is removed | holds, thin sample |
| 4 | Jamie Overton | 68.80 | 184 pressure balls; 3 season(s) of pressure evidence; outside the top 10 in 0/14 methods (worst: ipl_only #10); worst season lift 0.99; rank moves 0 when their best match is removed | holds, thin sample |
| 5 | Matheesha Pathirana | 66.95 | 574 pressure balls; 4 season(s) of pressure evidence; outside the top 10 in 4/15 methods (worst: lift_only #14); worst season lift -0.6; rank moves 0 when their best match is removed | holds |
| 6 | Sunil Narine | 66.44 | 367 pressure balls; 5 season(s) of pressure evidence; outside the top 10 in 2/14 methods (worst: lift_only #21); worst season lift -0.68; rank moves 0 when their best match is removed | holds |
| 7 | Sufiyan Muqeem | 66.31 | 132 pressure balls; 2 season(s) of pressure evidence; outside the top 10 in 2/13 methods (worst: loose_thresholds #11); worst season lift 0.15; rank moves -2 when their best match is removed | holds, thin sample |
| 8 | Shadab Khan | 65.64 | 213 pressure balls; 4 season(s) of pressure evidence; outside the top 10 in 5/14 methods (worst: pressure_v2_wide #30); worst season lift -0.54; rank moves 0 when their best match is removed | holds, method-sensitive |
| 9 | Jasprit Bumrah | 64.37 | 616 pressure balls; 5 season(s) of pressure evidence; outside the top 10 in 8/15 methods (worst: t20i_only #47); worst season lift -1.78; rank moves 0 when their best match is removed | holds, but bootstrap puts them outside the ten more than half the time |
| 10 | Mitchell Santner | 63.83 | 414 pressure balls; 5 season(s) of pressure evidence; outside the top 10 in 9/15 methods (worst: t20i_only #18); worst season lift -0.93; rank moves 0 when their best match is removed | holds, but bootstrap puts them outside the ten more than half the time |

## 4. Corrections applied to the application

1. **Player identity** — duplicate profile 39444 merged into 8638 (Basil Hameed); the merge is recorded in `load.ID_ALIASES` and applied before any aggregate, so no player is split in two.
2. **Run accounting** — `runs` in the pack is bat runs only and extras live in `extras1_runs`/`extras_2_runs`; the application now sums all three and reproduces the result-text margin in 397 of 397 verifiable matches.
3. **Legality** — wides, no-balls and penalties are excluded from legal-ball counts; batter balls faced exclude wides and penalties but include no-balls; bowler concessions include wides and no-balls but exclude byes and leg-byes.
4. **Wicket attribution** — run-outs, retired-out and obstruction are excluded from bowler wickets but retained as batter dismissals.
5. **Chase targets** — target = first-innings total + 1 unless a revised target exists; unreconstructable rain chases are excluded rather than guessed.
6. **Competition pooling** — the primary pool is IPL + T20I only; second-tier tournaments are demoted to a sensitivity variant so a Rising Stars performance cannot drive a franchise pick.
7. **Eligibility** — explicit floors on pressure balls, pressure matches, scored pressure innings and baseline balls; all four are varied in the sensitivity grid.
8. **Stability gate** — a pick must survive 15 alternative methods (median rank ≤ 12) and replay in at least two seasons.

## 5. Remaining limitations

- Ranking uncertainty is large: bootstrap `P(top-10)` for the tenth pick is 0.23 for bowlers and 0.37 for batters. The list is defensible as a *set*; the exact ordering beneath the top five is not.
- Knockout-only ranking is not identifiable (31 knockout matches, <2 eligible players).
- No fielding, no catch difficulty, no bowling match-ups, no venue/pitch adjustment.
- The pack's own inconsistencies (one wicket-margin mismatch, three missing XI rows, two roster-only duplicates) remain in the source and are documented rather than mutated.

## 6. Artefact index

| File | Contents |
|---|---|
| `validation.json` | all structural and cricket-correctness checks with evidence |
| `audit_facts.json` | counts, calibration table, configuration, failure list |
| `rankings_bat.csv / rankings_bowl.csv` | full ranked pool with every component and bootstrap interval |
| `alternatives_*.csv / alternative_ranks_*.csv` | 15-method agreement and per-player ranks |
| `threshold_sensitivity_*.csv` | eligibility grid |
| `leave_one_match_out_*.csv` | per-pick fragility to one match |
| `season_stability_*.csv` | season-by-season replication |
| `situation_breakdown_*.csv` | which pressure rule produced each player's balls |
| `split_profile_*.csv` | per-competition, per-season splits |
| `final_top10_*.csv / final_rejected_*.csv / final_selection.json` | the submission and what failed the gates |
