# F1 Tyre Degradation & Pit Strategy — Project Scope

**Status:** Scope locked 2026-11-18. Ingestion and cleaning v1 done 2026-11-19
**Season under analysis:** 2026 (all completed rounds)

> Source of truth is this file. A copy lives in the claude.ai Project "Personal Portfolio"
> (`claude/f1_tire_degradation_scope.md`); see `docs/PROJECT_LOG.md` for how they are synced.

---

## 1. Business question

> **At a given circuit, under dry green-flag conditions, when does a two-stop strategy beat a one-stop?**

The deliverable is a per-circuit decision rule with a threshold attached, not a set of charts.

**Decision it informs:** the pre-race strategy call on stop count — the single largest
strategic choice a team makes before lights out.

**Conclusion format:** *"At circuit X, with the allocated compounds and an estimated
pit-lane loss of P seconds, a two-stop is faster whenever the degradation rate exceeds
β* s/lap. Observed degradation was β̂ ± CI, therefore [one/two] stops."*

---

## 2. The core mechanism

Degradation cost grows **quadratically** with stint length; pit-stop cost grows
**linearly** with stop count. A stint of `L` laps on a tyre losing `β` s/lap of
tyre age costs `β · L(L+1)/2` in cumulative lap time.

Total race time under a candidate strategy:

```
T = N · base_pace
  + Σ_stints [ δ_compound · L + β_compound · L(L+1)/2 ]
  + n_stops · P
```

| Term | Meaning |
|---|---|
| `N` | race distance in laps |
| `base_pace` | driver/car reference lap time at that circuit |
| `δ_compound` | intrinsic pace offset of the compound when new |
| `β_compound` | degradation rate, s/lap per lap of tyre age |
| `P` | pit-lane time loss |

**Closed form for equal stint splits:**

> Two stops beat one when **β > 12P / N²**

Worked example: a 57-lap race with a 22s pit loss gives a threshold of
`12 × 22 / 57² ≈ 0.081 s/lap`.

This closed form is the headline. The production estimate uses a grid search over legal
compound sequences and stint-length splits, because real strategies mix compounds and
the regulations require at least two compounds in a dry race.

---

## 3. Scope — locked decisions

**In scope:**
- 2026 season only, all completed rounds (~19 as of scope date; the pipeline derives the
  completed set from the schedule rather than hardcoding it).
- Race sessions only.
- Dry, green-flag running.
- Linear degradation slope as the baseline model.

**Explicitly out of scope** (recorded so they don't creep back in):
- Cross-season comparison. 2026 introduced narrower tyres and dropped the C6, so earlier
  seasons are a different tyre population. Pooling would be invalid.
- Non-linear degradation / cliff modelling. Documented as a limitation; curvature is
  *tested for* but not modelled in the baseline.
- Simulating traffic or overtaking mechanics inside the optimiser.
- Safety-car and VSC strategy. The model is a green-race pre-race plan.
- Qualifying, sprint, and practice sessions.
- Undercut/overcut analysis — candidate for a future project.

**Rationale for the single-season choice:** one regulation era means one tyre
construction and one compound mapping, giving clean identification. The accepted cost is
N=1 race per circuit, which widens per-circuit confidence intervals and removes the
possibility of year-over-year replication as a validation check.

---

## 4. Hypotheses

| ID | Hypothesis | Role |
|---|---|---|
| **H1** | Within a stint, lap time increases with tyre age, and the slope is steepest for the softest compound: `β_SOFT > β_MEDIUM > β_HARD > 0`. | Sanity check. Failure means the data or filters are wrong, not that F1 tyres don't wear. |
| **H2** | The degradation slope for a given compound varies significantly across circuits (non-zero circuit × compound interaction). | **Make-or-break.** If this fails there is no per-circuit recommendation and the project reduces to one global threshold. |
| **H3** | Degradation slope increases with track temperature, controlling for compound and circuit. | Secondary finding; also a covariate the optimiser needs. |
| **H4** | The stop count implied by `β̂` vs `12P/N²` differs from the modal observed strategy at at least some circuits. | The payoff. Agreement is corroboration; disagreement is the finding to investigate. |
| **H5** | Where the model over-predicts stop count, the discrepancy is associated with low circuit-level overtaking rates. | Explains H4's residuals via track-position value. |

H2 is pre-registered as the decisive test. If the circuit × compound interaction is not
significant, the conclusion is a single global threshold plus an honest write-up of why
per-circuit estimation failed — not a pivot to a different question.

---

## 5. The identification problem

**Within a single stint, tyre age and race lap are perfectly collinear.** Fuel burn makes
the car faster as the race progresses (roughly 0.03 s/lap per kg); tyre wear makes it
slower. Inside one stint these cannot be separated — the design matrix is rank-deficient.

Identification comes **only** from the fact that different drivers start stints at
different race laps. The model must therefore be fit across pooled stints with a shared
`LapNumber` term. Per-stint regressions alone cannot recover degradation in absolute terms.

**Second caveat, stated rather than solved:** `LapNumber` absorbs fuel burn *and* track
evolution together. Race data alone cannot separate them. The coefficient is reported as a
combined race-lap effect. This is a limitation in the README, not a claim of having
decomposed it.

---

## 6. Variables

| Role | Variable | Source |
|---|---|---|
| Response | `LapTime` (seconds) | `session.laps` |
| Primary predictor | `TyreLife` (laps on this set) | `session.laps` |
| | `Compound` (SOFT/MEDIUM/HARD — **relative to each race's allocation**) | `session.laps` |
| | `CompoundAbsolute` (C1–C5) | **manual** allocation table |
| Confounder | `LapNumber` (fuel burn + track evolution, combined) | `session.laps` |
| | `TrackTemp`, `AirTemp`, `Rainfall` | `session.weather_data` |
| | gap to car ahead (dirty-air proxy) | derived from cumulative lap times |
| Grouping | `Driver`, `Team`, `Stint`, `Round`, `Circuit` | `session.laps`, event schedule |
| Filter fields | `TrackStatus`, `IsAccurate`, `PitInTime`, `PitOutTime`, `FreshTyre` | `session.laps` |
| Derived | `LapTimeDelta` (s) | lap time minus the median clean lap time of the same circuit; compares laps across circuits |
| Derived | pit-lane loss per circuit | `(in-lap + out-lap) − 2 × reference lap` |
| Derived | overtakes per race (circuit-level) | reference table, see §9 |

**Where the pit-loss definition comes from.** "Pit loss" is the time a stop costs compared with staying on track. There is no official
FIA or Formula 1 definition. Measuring it from lap times is a community convention: in-lap + out-lap - 2 x a normal lap, with the
normal lap taken from laps before the stop (a RaceFans forum thread gives this form, and a variant that averages the three laps before
the in-lap: [I need a stats guru](https://www.racefans.net/groups/f1/forum/topic/i-need-a-stats-guru/)). The same thread separates this
"track time lost" from the total time a stop takes from pit entry to pit exit; we measure the first. Pit loss is largely fixed per circuit
by pit-lane length and speed limit ([Flow Racers](https://flowracers.com/?p=10084)). In this project the formula was set in `docs/scope.md`
section 6 and refined in `f1_pit_strategy/pit_loss.py` (baseline = the driver's median clean lap within 5 race laps of the stop). These
sources are forums and explainers, not official or peer-reviewed. Limits: in-laps and out-laps also contain tyre warm-up and tyre-condition
effects, so P partly reflects them; and a clean baseline needs laps free of traffic and errors (traffic is not filtered in v1).

### Reference tables built by hand

1. **`pirelli_allocation.csv`** — maps each round's SOFT/MEDIUM/HARD to absolute C1–C5.
   Required because FastF1's compound labels are *relative to each race's allocation*:
   without this, "SOFT" denotes different rubber at different races and H2 is
   unidentifiable. Sourced from Pirelli's per-race allocation announcements.
2. **`circuit_overtaking.csv`** — circuit-level overtaking difficulty metric for H5.

---

## 7. Cleaning and filter decisions

Every exclusion is written to an audit table with a `reason` column rather than silently
dropped. The retention funnel becomes a figure in the README.

| Filter | Rationale |
|---|---|
| Drop lap 1 | Standing start, no representative tyre age or pace. |
| Drop in-laps and out-laps | Pit entry/exit dominates the lap time. |
| Drop laps where `TrackStatus` ≠ green | SC/VSC/yellow pace is unrelated to tyre state. |
| Wet races: drop the whole race if over 25% of its laps are wet (rain flag or wet-weather tyres); otherwise drop the wet laps and the next 3 | Different tyre population; a damp track lingers after rain. Only São Paulo is dropped whole. |
| ~~Drop laps within ~1.5s of the car ahead~~ | **Deferred to v2** (section 13). Dirty-air laps stay in v1; listed as a limitation. |
| Drop the lap after a non-green lap | Restart laps: cold tyres, bunched field. |
| Drop laps missing lap time, compound or tyre age | The model cannot use them; nothing is imputed. |
| Drop laps slower than 1.07 × their stint median | Spins, off-track laps; median taken over laps that passed the other rules. |
| Drop `IsAccurate == False` | FastF1's own timing-integrity flag. |
| Drop stints with fewer than 5 laps left after filtering | Too few points to estimate a slope; usually damage or an aborted strategy. |

**Wet rule, explained.** A lap is wet if the rain flag is on or the car is on intermediate or wet
tyres. A race with more than 25% wet laps is a different tyre population and is dropped whole
(São Paulo, 36.3%). A race with less is kept: its wet laps and the 3 laps after them are removed,
because a damp track slows slick-tyre laps too. Kuala Lumpur (10.7%), Zandvoort (11.5%) and Montréal (1.2%)
fall in this second group. The 25% cutoff is a default chosen by the author's assistant, not
derived from data; its effect is reported by a sensitivity run (see section 14).

Thresholds are parameterised, not hardcoded, so sensitivity to each can be reported.

---

## 8. Modelling approach

**Two-stage, chosen deliberately over a single crossed mixed model.**

- **Stage 1** — estimate a degradation slope per stint, controlling for the shared
  race-lap effect.
- **Stage 2** — regress the stint slopes on compound, circuit, and track temperature,
  weighted by stage-1 precision.

**Why two-stage:** it is transparent, every coefficient is defensible line by line, and it
avoids `statsmodels` MixedLM's known unreliability with crossed random effects. The
textbook answer is a hierarchical model; the README states why this project did not use
one and what would change if it did.

**Curvature check:** add a quadratic tyre-age term and test significance. If curvature is
material, the closed-form threshold is invalid but the grid-search optimiser still works —
report both.

---

### Why a multiple regression, weighted in stage 2

The decision rule needs one number per circuit: how many seconds the car loses per extra lap of tyre age (beta). That is a coefficient, so the tool has to return a
coefficient with an interval.

**Why multiple regression, not simpler comparisons.** Lap time depends on several things at once and tyre age is tangled up with them: race lap (fuel burn and
track evolution; correlation with tyre age 0.46), car and driver pace (team explains 48% of the variance left after removing the circuit), and compound. A univariate
comparison of lap time against tyre age is biased by those omitted variables: the raw curves in `docs/eda.md` (charts 2 and 3) slope *down* with tyre age and the raw
correlation is -0.08, the wrong sign for wear. A regression holds the other variables fixed, so the tyre-age coefficient is the effect of age with race lap, driver and compound
held constant. It also pools stints that start on different race laps, which is the only way to separate wear from fuel burn (section 5).

**Why not a machine-learning model.** (1) The goal is an effect estimate with an interval, not a lap-time prediction; random forests and boosted trees predict well but give no
degradation rate, and feature importance is not seconds per lap. (2) The data are small for ML: 15,206 laps and 30 to 65 stints per circuit, with 4 to 40 stints in a
circuit-compound cell, so flexible models overfit. (3) The rule needs the effect at tyre ages that are thinly observed (beyond about 30 laps); a linear model extrapolates
explicitly, and we state that as an assumption, while trees stay flat outside the data without saying so. (4) The rule 12P/N^2 is itself derived from a linear wear rate, so a
linear slope is the matching quantity. A tree model is a possible robustness check, not the primary tool.

**Why weighted by precision in stage 2.** Stage 1 gives slopes of very different precision (standard errors from 0.004 to 0.03 s per lap; the spread of per-stint slopes falls
6-fold between 5-9 lap and 30+ lap stints, `docs/eda.md` chart 4). An unweighted regression lets a noisy cell count as much as a precise one. Inverse-variance weights (1 / SE squared)
give the minimum-variance combination when the errors are independent with known variances (Gauss-Markov / weighted least squares). Standard WLS also estimates a scale (the residual variance
after weighting); a value above 1 means the cells scatter more than their stage-1 standard errors imply, and the standard errors and F-test widen to match (in stage 2 the scale is 3 to 17).
Stage 2 is built (`f1_pit_strategy/stage2.py`); a few precise cells carry much of the weight (the top five carry 35%), which is a stated limit.

**Why two stages, not one mixed model.** Each stage-1 coefficient is a defensible number on its own, and statsmodels' crossed random effects are unreliable (section 8). The cost, stated rather than hidden: stage-1 error is carried into stage 2 only through the weights.

**Limits.** Linear wear is a baseline assumption (curvature is tested later), the race-lap effect is assumed linear and shared within a circuit, and standard errors clustered over 30 to 65 stints are approximate.

## 9. Validation plan

Designed so that **the project cannot fail to produce a conclusion.**

1. **Residual check.** For each driver's actual strategy, does the model's predicted total
   race time match the observed total (excluding SC and traffic laps)? Systematic bias here
   invalidates everything downstream.
2. **Held-out races.** Predict the optimal stop count; compare against what the
   front-runners actually did.
   - *Agreement at most circuits* → the model is calibrated. Write-up: a two-parameter
     model reproduces professional strategy calls.
   - *Disagreement at specific circuits* → that is the finding, and it feeds step 3.
3. **Overtaking residual analysis (H5).** The optimiser is a **pure pace-optimal
   clean-air baseline**; overtaking difficulty is used to *explain its residuals* rather
   than being modelled inside it. Cross-reference circuits where the model over-predicts
   stop count against a circuit-level overtaking metric, to test whether track-position
   value explains why teams run one-stops at low-overtaking circuits despite high
   degradation.

   **Known weakness:** n ≈ 19 circuits. This is a descriptive correlation with wide
   intervals, not a hypothesis test, and is reported as such.

---

## 10. Limitations (written up front, not discovered late)

- The model minimises **race time, not finishing position**. At low-overtaking circuits
  these diverge sharply. This is the central limitation and belongs in the README body.
- `LapNumber` conflates fuel burn with track evolution.
- Linear degradation is a baseline assumption; cliffs are tested for but not modelled.
- N=1 race per circuit → wide per-circuit intervals, no year-over-year replication.
- Dirty-air laps are not filtered in v1; traffic can inflate degradation slopes.
- Mexico City data stops at lap 56 of 71 and tyre ages stop at about 43 laps, so its slope is
  extrapolated for a full-distance strategy.
- Safety cars make a stop nearly free; the model assumes a green race.
- Tyre allocation limits (finite sets per weekend) are not enforced in the optimiser.
- Circuit resurfacing and compound-allocation choices are circuit-season specific and
  cannot be separated from the circuit effect with one season of data.

---

## 11. Architecture

```
FastF1 library + cache   →  raw parquet          →  clean parquet        →  pandas        →  statsmodels
(F1 live-timing API,        data/raw/season=2026/   data/processed/         joins +          two-stage
 Jolpica-F1; gitignored)    round=NN.parquet        clean_laps.parquet      aggregation      model
                                                    exclusions.parquet
```

- FastF1's on-disk cache **is** the raw layer; it is not rebuilt.
- One parquet per session. Ingest is idempotent and resumable — it skips rounds already
  written.
- Processed parquet is committed to the repo so the analysis is reproducible without
  re-downloading. The cache is gitignored.
- **Data access is the FastF1 Python library**, a client for the Formula 1 live-timing API
  and the Jolpica-F1 API (see the README tooling note). **DuckDB was planned as a SQL layer
  over the parquet files but is not used**: pandas does the joins and aggregation, which is
  enough for about 23,000 laps. (Amended 2026-11-22; the partitioned layout still allows it.)

**Execution note:** FastF1 requires network access to `livetiming.formula1.com` and
`api.jolpi.ca`. The pipeline runs locally on the author's machine, not in a sandboxed
environment.

---

## 12. Deliverables

- [x] Ingestion script → raw parquet per round
- [x] Cleaning script → clean laps + exclusions audit table (v1, no traffic filter)
- [x] Data-quality audit and EDA (`python -m f1_pit_strategy.eda`; `docs/eda.md`, `reports/analysis/`)
- [x] Pit-loss estimation per circuit, derived from data
- [x] Two-stage degradation model with intervals (stage 1: per-circuit regression with intervals; stage 2: tests H1 to H3, `docs/stage2.md`)
- [ ] Strategy optimiser (grid search over compound sequences and stint splits)
- [ ] Validation: residual check (done, `docs/model_metrics.md`), stop-count comparison (done, `docs/validation.md`), overtaking residuals (to do)
- [ ] Recruiter-facing README: question, approach, findings, limitations
- [x] **Headline visual** (built differently: threshold 12P/N² on x, degradation d on y, dashed y = x line, 13 Tier 1 circuits, `reports/figures/09_decision_chart.png`; planned as:) degradation rate vs pit-lane loss scatter, every circuit as a
      point, with the `β = 12P/N²` threshold curve drawn. Above the line, one-stop
      circuits; below, two-stop.
- [ ] LinkedIn post with 2–3 visuals

---

## 13. Future work (parked, not scope)

- Undercut vs overcut: when does pitting first gain the position? Requires handling the
  selection bias that teams undercut when they already expect it to work.
- Cost of strategy error: seconds left on the table per race.
- 2027 follow-up: do the 2026 thresholds still hold as teams learn the new tyres?
- Non-linear degradation and cliff detection.
- Deriving overtakes from FastF1 position data rather than a reference table.
- Traffic (dirty-air) filter: drop laps within 1.5 s of the car ahead. Needs a gap built from
  cumulative lap times and `Position`.
- Retry the Mexico City download (laps 57-71 missing) or use OpenF1 for that round.

---

## 14. Amendments after scope lock

- **2026-11-18 — FastF1 now needs an F1TV login.** FastF1 3.9+ requires an F1TV
  Access/Pro/Premium account because Formula 1 added authentication to its data APIs.
  Version 3.8.3 does not bypass it (every request returned "Failed to load"). The author
  has a paid F1TV account and logged in successfully. The login token is stored locally by
  FastF1 and expires after about four days. Credentials must never be written to files in
  this repo.
- **2026-11-18 — Fallback data source verified.** OpenF1 (`api.openf1.org/v1`) answered
  for 2026 with laps, stints (compound, `tyre_age_at_start`), weather and race_control
  endpoints, free and without authentication. If FastF1 access fails, switching means:
  tyre age per lap = `tyre_age_at_start` + laps into the stint; green-flag laps derived from
  `race_control` messages instead of `TrackStatus`; no `IsAccurate` flag. Open question: the
  API reported 25 "Race" sessions for 2026 against a 22-round calendar; check before use.
- **2026-11-18 — Full-season ingest done via FastF1.** The F1TV login worked, so the
  OpenF1 fallback was not needed. 20 rounds were completed by this date (not ~19), and the
  calendar includes both Barcelona (round 7) and Madrid (round 14).
  All 20 loaded with 0 failures; 23,323 raw laps. Wet running exists in rounds 5, 16 and 20
  (intermediate tyres), so wet-race exclusion in section 7 must use compounds as well as
  the Rainfall flag.
- **2026-11-19 — Wet-race rule refined (amends section 7).** Drop a whole race only if more
  than 25% of its laps are wet; otherwise drop the wet laps and the next 3. Only São Paulo
  (36.3%) is dropped; Montréal (1.2%), Kuala Lumpur (10.7%) and Zandvoort (11.5%) are kept. A sensitivity
  run (cells = circuit x compound with SOFT/MEDIUM/HARD): wet cutoff 10% gives 40 cells with 8+
  stints and 7 with fewer than 4; 40% gives 46 and 9; post-rain buffer 0-5 laps and outlier ratio
  1.05-1.10 leave 45 and 7.
- **2026-11-19 — Zandvoort GP kept:** 485 clean laps in 50 stints without rain.
- **2026-11-19 — Mexico City GP uses partial data.** The API returned laps 1-56 of a 71-lap dry
  race; the author chose to analyse them as retrieved. N = 71 for the threshold.
- **2026-11-19 — Traffic filter deferred to v2** (author decision, to keep v1 simple). Moved
  to section 13; the setting was removed from `config.py`.
- **2026-11-19 — Allocation table complete.** All 19 kept rounds have a C1-C5 ladder. Round 16 is
  named "Bahrain Grand Prix" by FastF1 but held in Kuala Lumpur (Sepang), which fits its rain; it is labelled Kuala Lumpur.
- **2026-11-19 — EDA and data-quality workflow.** The audit and the EDA follow the workflows of the data-analytics-skills repository
  (https://github.com/nimrodfisher/data-analytics-skills), a collection of 31 reusable data-analyst workflows (EDA, data-quality audit, chart design, insight writing, documentation, QA), written as step-by-step instructions for AI assistants. Rules adopted: the raw laps are audited on six dimensions (completeness, accuracy, consistency, timeliness,
  uniqueness, validity) and need 7 of 10 to pass; the cleaned laps must pass every guarantee; the EDA runs a 43-item checklist; thresholds are in
  `f1_pit_strategy/eda/settings.py`. Laps are compared inside their circuit with `LapTimeDelta` (section 6). Race lap stays in the model because fuel
  burn and track evolution (about 0.037 s per lap) hide tyre wear in raw lap times. A circuit-compound cell with fewer than 4 stints is not estimable.
  Outputs: `docs/eda.md` (eight charts, each with a business and a statistical conclusion) and `reports/analysis/`.
- **2026-11-19 — Decision layer in two tiers (author decision).** Degradation is estimated for all 19
  circuits; the earlier steps (ingestion, cleaning, EDA) are not changed. The strategy call (threshold
  12P/N^2 against the circuit's degradation rate d) is made only at the 13 circuits with at least 10
  usable green-flag, dry stops (**Tier 1**: Suzuka, Miami, Monaco, Barcelona, Spielberg, Silverstone,
  Budapest, Zandvoort, Madrid, Kuala Lumpur, Singapore, Austin, Mexico City). The other 6 (**Tier 2**:
  Monza, Baku, Shanghai, Montréal, Melbourne, Spa) show d and the lap count, and P, threshold and
  recommendation read "N/A (Insufficient green-flag stops: n < 10)". Why: safety cars, yellow flags
  and rain removed most of their green-flag stops (833 stops found, 317 usable overall), and a P from
  fewer than 10 stops is too noisy; it is excluded from strategy calls and never imputed. Outputs:
  a summary table of all 19 circuits and a decision chart for the 13 (x = threshold, y = d, dashed
  y = x, 2-Stop above the line). The cutoff is `MIN_STOPS_FOR_P` in `config.py`.
- **2026-11-19 — Stage 1 implemented as a pooled per-circuit regression (refines section 8).** Per circuit:
  LapTime ~ driver intercepts + LapNumber + compound intercepts + a TyreLife slope per compound, standard errors clustered by stint. This
  replaces "a slope per stint" because one stint cannot separate wear from fuel burn (section 5). The circuit-level rate d is the
  lap-weighted mean of the estimable compound slopes (cells with at least 4 stints), as chosen by the author. Stage 2 (H2, H3) is still to do.
- **2026-11-19 — Validation done (section 9, steps 1-2).** Tier 1 calls were compared with the stops made by finishers: 10 of 13 agree; the 3
  disagreements are all 1-Stop calls where most stops were under SC, VSC or red flags (see `docs/validation.md`). Overtaking (step 3, H5) is not tested yet.
- **2026-11-19 — Method justification recorded.** Section 8 now explains why a multiple regression (weighted by precision in stage 2) is used instead of univariate comparisons or machine-learning models, and `docs/decision.md` explains the choice of the decision scatter plot.
- **2026-11-19 — EDA findings that shape the model (charts 1 to 4 of `docs/eda.md`).** Team explains 48% of the
  variance of `LapTimeDelta`, so the model must use within-stint slopes or team/stint intercepts. Per-stint naive slopes are heavy-tailed because their spread depends on stint length
  (std 0.233 for 5-9 laps against 0.039 for 30+), so stage 2 weights by precision or uses a robust fit. Late-race points (after lap 40) rest on about half as many laps and on fewer circuits.
- **2026-11-19 — Pit-lane loss method fixed.** P per stop = in-lap + out-lap - 2 x the driver's
  median clean lap within 5 race laps of the stop (replaces the looser "reference lap" in
  section 6); P per circuit = median over green-flag, dry stops (317 usable of 833). Six circuits
  have fewer than 10 usable stops and are flagged thin. Output: `data/processed/pit_loss.csv`.
- **2026-11-22 — DuckDB dropped; data access documented.** The pipeline never used DuckDB, so it is removed from the stack and `requirements.txt`. Data comes from the FastF1 Python library (client for the F1 live-timing API and Jolpica-F1); processing is pandas; the model is statsmodels. See the README tooling note.
- **2026-11-22 — Stage 2 done (H1 to H3), with standard WLS.** Plain weighted least squares on the circuit-compound slopes with weights 1/SE^2 (no between-cell variance estimate, no Q test). **H2 supported:** a joint F-test of the circuit terms
  (`Beta ~ Compound` against `Beta ~ Compound + Circuit`) gives F = 11.06 on 18 and 27 df, p = 3e-8, and weighted R^2 rises from 0.21 to 0.91. **H1 not supported:** `Beta ~ Circuit + Softness` gives +0.0038 s/lap per step
  (95% interval -0.006 to +0.013, p = 0.42; robust to the tyre-age window); per section 4 this is a warning about data or filters, recorded as open, and no compound ranking is claimed. **H3 not supported**, inconclusive: tested across circuits with
  compound controls (`Beta ~ Compound + Temp`), not "controlling for circuit" as written in section 4, because circuit intercepts would absorb a circuit-level temperature; errors are clustered by circuit (p = 0.25) because cells of one circuit share one temperature
  (plain WLS gives p = 0.10 and is too optimistic). H2 tests "circuits differ given compound"; an interaction cannot be separated from residual error with one slope per cell.