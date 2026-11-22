# Project log

Newest entry first. One entry per working session: what was done, decisions and why,
what is next. The "Current state" block is rewritten each session; entries below it are history.

## Current state (2026-11-19)

- **Done:** scope locked; ingestion of all 20 completed 2026 rounds (23,323 raw laps); cleaning v1 (13 rules, no traffic filter) giving 15,206 clean laps
  (65.2%) in 854 stints; allocation table complete; data-quality audit and EDA; pit-lane loss P per circuit; stage 1 degradation model (rate d per circuit);
  Tier 1 / Tier 2 decision layer (5 two-stop and 8 one-stop calls at 13 circuits); validation against real stop counts (model agrees at 10 of 13).
- **Outputs:** `data/processed/` (`clean_laps`, `exclusions`, `pit_loss.csv`, `degradation_by_*.csv`, `decision_summary.csv`, `validation_stops.csv`);
  `docs/eda.md`, `docs/decision.md`, `docs/validation.md`; `reports/figures/` (nine charts); `reports/analysis/` (nine reports). Rebuild in order:
  `clean`, `eda`, `pit_loss`, `degradation`, `decision`, `validate` (each `python -m f1_pit_strategy.<name>`).
- **Not done:** stage 2 of the model (H1, H2, H3 tests), H4/H5 write-up, grid-search optimiser, README findings, LinkedIn post.
- **Open data issues:** Mexico City data stops at lap 56 of 71. Round 16 (FastF1 name "Bahrain Grand Prix") was held at Sepang, Kuala Lumpur, so it is
  labelled Kuala Lumpur. `circuit_overtaking.csv` is not compiled (needed for H5).

## Plan

- [x] Scope, repo scaffold, F1TV access
- [x] Ingest all rounds, validate raw data
- [x] Cleaning v1 with audit table
- [x] Allocation table complete for all 19 kept rounds (C5/C4/C3 at 10, C4/C3/C2 at 7, C3/C2/C1 at 2)
- [x] Join `CompoundAbsolute` (C1-C5) from the allocation table (in `clean.py`; no lap lost, no nulls)
- [x] Count stints per circuit and absolute compound: 57 cells, 45 with >= 8 stints, 5 with 4-7,
      7 with < 4 = not estimable (Shanghai C4; Montréal, Baku, Singapore, Mexico City C3 as HARD;
      Suzuka, Silverstone C3 as SOFT). All 7 are C3 (6) or C4 (1); C1 and C2 cells are all >= 8.
      (stints per compound: C1 40 at 2 circuits, C2 207 at 9, C3 200 at 15, C4 261 at 17, C5 146 at 10)
- [x] Data-quality audit and EDA (`python -m f1_pit_strategy.eda`; `docs/eda.md`, `reports/analysis/`). Findings:
      * The circuit explains 97.9% of lap-time variance, so laps are compared with `LapTimeDelta` (lap time minus the circuit's median clean lap).
      * Lap time falls 0.037 s per race lap (laps 2-6 average +1.14 s, laps 60+ average -0.84 s): fuel burn and track evolution hide tyre wear in raw lap times.
      * Correlation with `LapTimeDelta`: `LapNumber` -0.40, `TyreLife` -0.08, `FreshTyre` +0.16, `TrackTemp` +0.03; `TyreLife` vs `LapNumber` 0.46; variance inflation factors at most 1.3.
      * Naive per-stint slope (wear minus fuel): median +0.007 s/lap, std 0.127; 179 of 854 stints run 28 or more race laps; 8.8% of laps are on tyres older than 30 laps.
      * Audit of the raw laps: 8.9 of 10, 6 of 31 checks fail (placeholder values, TrackTemp 0.0, the truncated Mexico City race, unmapped compounds in the dropped
        wet race), none critical; the cleaned laps pass all 11 guarantees.
- [x] Pit-lane loss P per circuit (`python -m f1_pit_strategy.pit_loss` -> `data/processed/pit_loss.csv`).
      833 stops found, 317 usable (green flag, dry, reference lap available). Median P by circuit
      runs 19.1 s (Zandvoort) to 35.4 s (Shanghai, 4 stops); 13 of 19 circuits are between 19 and
      27 s. Six circuits have fewer than 10 usable stops and are flagged thin: Monza 2, Baku 2,
      Shanghai 4, Montréal 6, Melbourne 8, Spa 9.
- [x] Stage 1 of the degradation model (`python -m f1_pit_strategy.degradation`): one pooled regression per circuit
      (driver intercepts, shared race lap, tyre-age slope per compound, stint-clustered SEs); d per circuit = lap-weighted mean
      of the estimable compound slopes. d runs from 0.000 (Montréal) to 0.152 s/lap (Barcelona); race-lap effect -0.007 to -0.073.
- [ ] Stage 2: slopes on compound, circuit, temperature (H2, H3)
- [x] Decision layer in two tiers (`python -m f1_pit_strategy.decision` -> `docs/decision.md`, `reports/figures/09_decision_chart.png`).
      Tier 1 (13 circuits): 5 two-stop (Barcelona, Spielberg, Budapest, Zandvoort, Kuala Lumpur), 8 one-stop; 4 calls uncertain
      (Zandvoort, Kuala Lumpur, Monaco, Austin). Tier 2 (6 circuits): d and lap count only.
- [ ] H1-H5 tests
- [x] Validation against real stop counts (`python -m f1_pit_strategy.validate` -> `docs/validation.md`): the model agrees with what finishers did at 10 of 13
      Tier 1 circuits; the 3 disagreements (Monaco, Mexico City, Silverstone) are all 1-Stop calls and are explained by free stops under SC/VSC/red flags.
      Naive baselines: always 1-Stop 5 of 13, always 2-Stop 8 of 13 (actual stops); on green-flag-equivalent stops model 12, always 1-Stop 9, always 2-Stop 4.
- [ ] README findings and headline chart
- [ ] v2 only: traffic (dirty-air) filter (scope section 13)

## Standing decisions

- **Wet:** drop a whole race if over 25% of its laps are wet (rain flag or wet tyres); otherwise
  drop the wet laps and the next 3. Only São Paulo is dropped. Montréal (1.2%), Kuala Lumpur (10.7%),
  Zandvoort (11.5%) are kept. Why: a mostly wet race is a different tyre population, while a few wet
  laps only need removing (plus 3 laps for the damp track). The 25% cutoff is a default, not
  derived from data; at 10% Zandvoort and Kuala Lumpur would be dropped (83 stints), at 40% São Paulo
  returns with mixed-condition laps. Setting: `WET_RACE_LAP_SHARE` in `config.py`.
- **Zandvoort:** kept; 485 clean laps in 50 stints without rain.
- **Mexico City:** analyse the 56 laps the API returned (race ran 71, dry). Use N = 71 in
  12P/N^2. Tyre ages stop at about 43 laps (42 SOFT, 37 MEDIUM among clean laps), so any
  Mexico City slope is an extrapolation for a full-distance strategy. No HARD stints there.
- **Used tyres:** kept; `FreshTyre` stays as a column.
- **Traffic filter:** deferred to v2 to keep v1 simple; listed as a limitation.
- **Compounds:** model by absolute compound (C1-C5), not by the relative SOFT/MEDIUM/HARD labels.
  C1 is observed at only two circuits (Suzuka, Silverstone). Assumes a C-number is the same recipe at
  every race; not verified.
- **Labels:** circuits are named by host city or town, one rule for all (`city` column of
  `data/reference/pirelli_allocation.csv`, copied into the data as `City`). Round 16 is Kuala Lumpur
  (FastF1 name "Bahrain Grand Prix"). Detail on every figure: `docs/eda.md`.
- **Race lap and circuit:** `LapNumber` stays in the model (fuel burn and track evolution would otherwise hide tyre wear); estimates are made inside a circuit,
  using `LapTimeDelta`. A circuit-compound cell with fewer than 4 stints is not estimable; 4 to 7 stints is thin (wide intervals).
- **Decision tiers:** Tier 1 = the 13 circuits with at least 10 usable green-flag dry stops get the
  strategy call (threshold 12P/N^2 against d); Tier 2 = Monza, Baku, Shanghai, Montréal, Melbourne,
  Spa (fewer than 10 stops) show d and lap count only, and P, threshold and recommendation are
  "N/A (Insufficient green-flag stops: n < 10)". Degradation is estimated for all 19; the filter is
  applied only at the decision stage; P is never imputed. Built in `decision.py` on the stage 1
  degradation model. Borderline inside Tier 1: Suzuka 12, Zandvoort 13, Madrid 14, Singapore 15 stops.
- **Method choices:** multiple regression (weighted by precision in stage 2) because tyre age is confounded with race lap, car pace and compound and the rule needs a
  coefficient with an interval; no ML as the primary tool (small cells, no coefficient, no extrapolation). The decision is shown as a scatter of threshold against d with a
  y = x line and error bars. Reasoning in `docs/scope.md` section 8 and `docs/decision.md`.
- **Team pace:** after removing the circuit, team still explains 48% of the variance of `LapTimeDelta`; Cadillac and Aston Martin are 14% of the clean laps
  but 81% of the slow outliers (about +2 s vs the circuit median). They stay in the data. The model uses within-stint slopes (a constant car-pace offset cancels) and
  team or stint intercepts; it never compares raw levels between cars.
- **Slope distribution:** per-stint naive slopes are heavy-tailed (excess kurtosis 16.8) because the spread falls 6-fold from 5-9 lap stints to 30+ lap stints; stage 2
  weights by precision plus between-stint variance, or uses a robust fit.
- **Quality gates:** the raw laps are audited on six dimensions (PASS from 7 of 10) and the EDA runs a 43-item checklist, following the workflows of
  [data-analytics-skills](https://github.com/nimrodfisher/data-analytics-skills), a collection of 31 reusable data-analyst workflows (EDA, data-quality audit, chart design, insight writing, documentation, QA), written as step-by-step instructions for AI assistants. Thresholds are in `f1_pit_strategy/eda/settings.py`. Every chart is explained with a business and a statistical conclusion.
- **Thresholds** live in `config.py`. A one-at-a-time sensitivity run: the post-rain buffer
  (0-5 laps) and outlier ratio (1.05-1.10) did not change the cell counts (45 of 57
  circuit-compound cells have >= 8 stints, 7 have < 4); the wet cutoff did (10%: 40 and 7;
  40%: 46 and 9). At the current settings the 7 thin cells are Suzuka, Shanghai and Silverstone SOFT and Montréal,
  Baku, Singapore and Mexico City HARD: compounds barely or never run, not a cleaning effect.

## 2026-11-22 (session 9): DuckDB dropped, model metrics

**Done**
- DuckDB removed from the docs, `requirements.txt` and `CLAUDE.md`: it was never used. Data access is documented as the FastF1 library (client for the F1 live-timing API and Jolpica-F1); processing is pandas.
- `metrics.py` writes `docs/model_metrics.md` and `data/processed/model_metrics.csv`: per circuit R², adjusted R², R² of a driver-only model, the R² added by the race-lap and tyre terms,
  residual SD, lag-1 residual correlation within stints and the share of laps beyond 3 residual SDs, next to d and its interval.
- Findings: R² 0.57 to 0.91 but a driver-only model already reaches 0.44 to 0.78 (the lap and tyre terms add 0.07 to 0.39); residual SD 0.43 to 1.12 s; residuals of consecutive laps in a stint correlate
  0.20 to 0.65, so clustered standard errors are needed; all metrics are in-sample.
- `CLAUDE.md` run list updated with the newer steps.

**Next**
1. Decide on slim stage 2 (H1, H2, H3) versus finishing with README findings and limitations.
2. README findings, LinkedIn post; commit and push.

## 2026-11-19 (session 8): validation and header clean-up

**Done**
- `validate.py`: compares each Tier 1 call with the stops made by finishers (a finisher's last lap reaches 90% of the race's last lap). A 1-Stop call
  agrees if over half the finishers made exactly one stop; a 2-Stop call if over half made two or more. Also a green-flag-equivalent count
  (max(1, stops under green or yellow)) to discount cheap stops under SC, VSC and red flags.
- Result: 10 of 13 agree. The 3 that do not (Monaco 5 stops, Mexico City 2 to 3, Silverstone 2) are 1-Stop calls where 59% to 78% of stops were under
  SC, VSC or red flags; on the green-flag equivalent count they match. Overtaking difficulty (H5) was not tested: its table is not compiled.
- Montréal d = 0.000 checked: not collinearity (partial correlation 0.56, 3rd smallest standard error), not clipped (C4 -0.003, C5 +0.004), stable across
  four model variants (-0.004 to +0.001). A precise near-zero for the compounds run (C4, C5); the hardest compound had too few stints.
- Stale headers fixed in `README.md` and in this log.

**Caveats**
- One race per circuit; "modal stops" is a proxy for the best strategy; the green-flag equivalent count is my own construct. The model beats the naive rules by
  a modest margin on actual stops (10 vs 8 of 13), more on the green-flag equivalent (12 vs 9).

**Next**
1. Stage 2 (H1, H2, H3) and the H4 write-up; compile `circuit_overtaking.csv` for H5.
2. Grid-search optimiser, README findings and headline chart.

## 2026-11-19 (session 7): degradation model and decision layer

**Done**
- `degradation.py`: per-circuit pooled regression `LapTime ~ driver + LapNumber + compound + compound:TyreLife`, standard errors clustered by
  stint. Circuit rate d = lap-weighted mean of estimable compound slopes (cells with >= 4 stints); its variance comes from the regression's
  covariance matrix. Outputs `degradation_by_cell.csv` and `degradation_by_circuit.csv`.
- `decision.py`: joins d with `pit_loss.csv`, applies the Tier 1 / Tier 2 rule (author's choices: lap-weighted d; P's IQR shown for the
  four borderline circuits), writes `decision_summary.csv`, `docs/decision.md` and the decision chart.
- Checks: swapping driver for team intercepts moves d by at most 0.014 s/lap (correlation 0.99, 0 of 13 calls flip); the within-stint naive
  slopes agree with d + race-lap effect (correlation 0.94, mean gap 0.003), so the code does what it claims.

**Decisions**
- Stage 1 is a pooled per-circuit regression, not one slope per stint, because a single stint cannot separate wear from fuel burn
  (scope section 5); stage 2 (H2, H3) is still to do.
- `Certainty of call`: clear only if the whole 95% interval of d lies on one side of the threshold range built from P's IQR.

**Caveats**
- Barcelona (d = 0.152) and Kuala Lumpur (0.110) are high; the raw within-stint slopes agree (+0.108 and +0.080), so it is in the data.
- The split between wear and the race-lap effect rests on stints that start on different laps; a wrong race-lap effect shifts every compound
  of a circuit equally. Intervals are approximate (30 to 65 stint clusters per circuit).
- Equal-split 12P/N^2 only; wear beyond about 30 laps is extrapolated; Mexico City stops at lap 56.

**Next**
1. Stage 2: regress compound slopes on compound, circuit and track temperature (H1, H2, H3).
2. Validation: compare the calls with the stop counts teams actually made (H4); then the grid-search optimiser.

## 2026-11-19 (session 6): pit-lane loss P

**Done**
- `pit_loss.py`: for each stop, P = in-lap time + out-lap time - 2 x reference lap, where the
  reference lap is the same driver's median clean lap within 5 race laps of the stop. P per
  circuit is the median over its usable stops. Also writes the threshold 12P/N^2 per circuit.
- Only green-flag, dry stops count (a stop under a safety car is much cheaper and would bias P
  down). Stop funnel: 833 found, 748 with both lap times, 389 green in and out, 352 not wet,
  351 not on lap 1, 334 in a kept race, 317 with at least 3 reference laps.
- Stop-level P: min 14.6 s, median 22.3 s, p95 32.5 s, max 50.5 s; none under 10 s, 9 over 40 s
  (the median per circuit is robust to those).
- The stops come from the raw laps, not the exclusions table, because that table records only
  the first reason per lap and has no pit-time columns.

**Definition source**
- There is no official definition of pit loss; (in-lap + out-lap) - 2 x normal lap is a community
  convention (RaceFans forum, Flow Racers; links in the README) and comes from `docs/scope.md`
  section 6. Our refinement is the local median baseline. Sources are forums, not peer-reviewed.

**Caveats**
- Six circuits have under 10 usable stops (see plan); their P is uncertain. Shanghai (35.4 s,
  4 stops) and Monza (31.5 s, 2 stops) are the least trustworthy values.
- The reference lap is an approximation: laps before the stop are older-tyre, laps after
  fresh-tyre, and the window is meant to balance them. Window size is `PIT_REF_WINDOW_LAPS`.
- Traffic is not filtered (v1), so a stop that rejoins behind a car may look slightly dearer.

**Next**
1. Stage 1 and stage 2 of the degradation model to get beta per circuit and compound.
2. Compare beta with the threshold in `pit_loss.csv`; give thin-P circuits an interval.

## 2026-11-19 (session 5): data-quality audit and EDA

**Done**
- `f1_pit_strategy/eda/` (run with `python -m f1_pit_strategy.eda`): reconciliation of raw, clean and excluded laps; audit of the raw laps; EDA profile with the 43-item
  checklist; eight charts; insight brief with an impact estimate; assumptions log; data catalog; methodology; QA gate. The workflows come from
  [data-analytics-skills](https://github.com/nimrodfisher/data-analytics-skills).
- Outputs: `docs/eda.md`, `reports/figures/` (eight charts), `reports/analysis/` (nine reports).
- `LapTimeDelta` defined and used on every chart (lap time minus the circuit's median clean lap, in seconds).

**Next**
1. Pit-lane loss `P` per circuit from the in-laps and out-laps in the audit table.
2. Stage 1 (slope per stint with shared race lap) and stage 2 (weighted regression of slopes), then the threshold per circuit.
3. Re-run `python -m f1_pit_strategy.eda` after any change to the cleaning rules.

## 2026-11-19 (session 4): simplify, v1 data, verification

**Done**
- Decisions on Zandvoort and Mexico City (above). Traffic filter moved to future work.
- `clean.py` now writes slim files: clean laps keep 12 columns, the audit table keeps the lap
  identity, the values the rules used and the reason. Counts unchanged: 15,206 clean, 8,117
  excluded.
- Removed `TRAFFIC_GAP_SECONDS` from `config.py`, `__pycache__` and `.DS_Store` files; rewrote this
  log, `scope.md` section 7 and the amendments in section 14, and the README; refreshed the
  notes column of `pirelli_allocation.csv` (no allocation values changed).
- An independent verification agent recomputed the funnel and rules from raw data (no logic
  errors) and caught a wrong Mexico City tyre-age figure (43, not 56), now fixed.

## 2026-11-18 (session 3): allocation table, diagnostics, cleaning step

**Done**
- `pirelli_allocation.csv` filled for 17 dry rounds from Pirelli press releases and
  formula1.com (one source per row). Rounds 16 and 20 were left blank because they were
  expected to be excluded; only 20 is.
- Diagnostics on the raw laps (dtypes, nulls, track status, wet signals, tyre-age steps,
  outliers). Types fixed in `clean.py`: small ints, nullable `Int16` for `TyreLife`, string
  `'None'` compound turned into a real null, the all-null `Deleted` column dropped.
- `clean.py` written: ordered rules, each lap gets its first failing reason. Funnel: lap 1 408;
  in/out laps 1,452; not green 2,463; after non-green 1,114; wet laps 656; wet race 1,435;
  missing lap time 175, compound 58, tyre age 152; inaccurate 3; slow outliers 12; short stints
  189. Retention per round: 17 rounds keep 59-83%; Kuala Lumpur 34% (safety cars plus missing data),
  Zandvoort 35% (rain laps), São Paulo 0%.

**Corrections**
- Spa: 44 scheduled laps equals the laps run; 872 rows is fewer than 22 x 44 only because
  of retirements. Not a shortened race.
- Mexico City: the race was not stopped. FastF1 results show the field finished 71 laps in the
  dry; our lap data ends at lap 56 (cause unknown).

## 2026-11-18 (session 2): laps-loaded check, full-season ingest

**Done**
- `ingest.py`: `check_laps_loaded()` right after `session.load()` raises `LapsNotLoadedError`
  naming the round and likely causes when laps are missing or empty (FastF1 logs load failures
  and returns normally). Tested offline with stub sessions.
- Round 1 re-ingested; PIA and HUL did not start, the other 20 drivers match the results.
- Full season: 20 rounds, 0 failures, 23,323 laps, 25 drivers over the season. FastF1 logged
  lap-alignment warnings for one driver each in rounds 8, 12 and 13.

## 2026-11-18: scope, scaffold, data access

**Done**
- Scope locked (`scope.md`): 2026 season, race sessions, dry green-flag laps, linear
  degradation baseline, two-stage model, overtaking used to explain residuals.
- Repo scaffolded; FastF1 3.9+ needs an F1TV login (done, token stored locally by FastF1,
  never in this repo). OpenF1 verified as a free fallback.
- Overtaking metric: hand-compile ~19 numbers into `data/reference/circuit_overtaking.csv`
  rather than derive them from position data.
- DuckDB was planned as a SQL layer over parquet; it turned out not to be needed (pandas does
  the joins), so it was dropped (see 2026-11-22). Data access is the FastF1 Python library.
