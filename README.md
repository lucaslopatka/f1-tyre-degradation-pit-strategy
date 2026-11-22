# F1 Tyre Degradation & Pit Strategy (2026 Season)

**Work in progress.** Scope locked; ingestion, cleaning (v1), EDA, pit-lane loss, the degradation model, the one-stop/two-stop decision and its validation are done; the stage 2 hypothesis tests (H1 to H3) are done; the optimiser, H4 and H5 and the findings write-up are next.

**Report:** [F1_pit_strategy_report.pdf](reports/presentation/F1_pit_strategy_report.pdf) is a 29-slide PDF that tells the whole project: the story and objective, data ingestion, cleaning, EDA, modelling, results, validation and conclusions.

## The question

**At a given circuit, under dry green-flag conditions, when does a two-stop strategy
beat a one-stop?**

The output is a decision rule with a number attached, not a gallery of charts.

## Why there is an answer at all

Degradation cost grows **quadratically** with stint length — a stint of `L` laps on a
tyre losing `β` seconds per lap of age costs `β · L(L+1)/2`. Pit-stop cost grows
**linearly** with stop count. Because one curve is quadratic and the other is linear,
there is always some degradation rate above which the extra stop pays for itself.

For equal stint splits over an `N`-lap race with pit-lane loss `P`:

> Two stops beat one when **β > 12P / N²**

A 57-lap race with a 22-second pit loss gives a threshold of ≈ 0.081 s/lap.

So the empirical work is three estimates per circuit: the degradation rate `β` per
compound, the pit-lane loss `P`, and the race distance `N`.

## Scope

- 2026 season only. The 2026 regulations introduced narrower tyres and dropped the C6
  compound, so earlier seasons are a different tyre population and pooling them would be
  invalid.
- Race sessions, dry and green-flag only.
- Linear degradation as the baseline; curvature is tested for and reported, not modelled.
- The optimiser is a **clean-air, pace-optimal baseline**. Overtaking difficulty is used
  to explain its residuals rather than being simulated inside it.

## Pipeline

```
FastF1 HTTP cache   →   data/raw/season=2026/round=NN.parquet   →   data/processed/   →   model
(gitignored)            one file per race, nothing filtered         clean + audit trail
```

```bash
pip install -r requirements.txt
python -m f1_pit_strategy.ingest          # all completed rounds
python -m f1_pit_strategy.inspect_raw     # validation report
python -m f1_pit_strategy.clean           # clean laps + exclusions audit table
python -m f1_pit_strategy.eda             # data-quality audit, EDA, charts and reports
python -m f1_pit_strategy.pit_loss        # pit-lane loss P per circuit and the threshold 12P/N^2
python -m f1_pit_strategy.degradation     # degradation rate per circuit and compound (stage 1)
python -m f1_pit_strategy.decision        # one-stop or two-stop call, table and chart
python -m f1_pit_strategy.validate        # compare the calls with the stops finishers actually made
python -m f1_pit_strategy.metrics         # R², residual SD and residual checks per circuit
python -m f1_pit_strategy.stage2          # hypothesis tests H1 to H3 on the circuit-compound slopes
```

Ingest is idempotent: it skips rounds already written. The first run downloads a few
hundred megabytes and takes a while; later runs are served from the cache.

Note that the raw layer keeps **every** lap, including safety-car, in- and out-laps.
Filtering happens in a separate step so that each exclusion is recorded with a reason and
the retention funnel can be published rather than assumed.

## Cleaning (v1)

Tyre wear can only be measured on normal racing laps, so every other lap is dropped and
logged with one reason (`data/processed/exclusions.parquet`):

1. Lap 1 and in/out laps: not normal pace.
2. Safety car, VSC, yellow flag, red flag and the lap after: the field is slowed.
3. Rain: drop a whole race if over 25% of its laps are wet (only São Paulo), otherwise drop the
   wet laps and the next 3.
4. Bad data: missing lap time, tyre age or compound, timing-inaccurate laps, and laps over 7%
   slower than their stint median.
5. Short stints: fewer than 5 clean laps cannot give a slope.

**Wet rule in detail.** A lap is wet if the rain flag is on or the car is on intermediate or wet
tyres. If more than 25% of a race's laps are wet, the whole race is dropped (only São Paulo, 36%).
Otherwise only the wet laps and the next 3 laps are dropped, because the track stays damp after
rain (Montréal 1.2%, Zandvoort 11.5%, Kuala Lumpur 10.7% are kept this way). The 25% cutoff and the 3-lap
buffer are settings in `config.py`.

Result: 23,323 raw laps → 15,206 clean laps (65.2%) in 854 stints. Traffic (dirty air) is not
filtered in v1.

## Data-quality audit and EDA

The audit and the EDA follow the workflows of [data-analytics-skills](https://github.com/nimrodfisher/data-analytics-skills), a collection of 31 reusable data-analyst workflows (EDA, data-quality audit, chart design, insight writing, documentation, QA), written as step-by-step instructions for AI assistants. The workflows used here are
programmatic-eda, data-quality-audit, visualization-builder, insight-synthesis, metric-reconciliation, assumptions-log, data-catalog,
analysis-documentation and analysis-qa-checklist. The repository's own scripts are not run; each workflow is implemented in
`f1_pit_strategy/eda/` with the thresholds in `f1_pit_strategy/eda/settings.py`.

Rules:
1. The raw laps are audited before use on six dimensions (completeness, accuracy, consistency, timeliness, uniqueness, validity), scored 0 to 10 per
   dimension; 7 or more overall is a PASS. The cleaned laps must pass every guarantee.
2. The EDA runs a 43-item checklist (null rate 5% warn and 30% fail, outliers by IQR 1.5 and |z| 3, skew 0.5/1/2, strong correlation from |r| 0.8).
3. Laps are compared inside their own circuit: `LapTimeDelta` is a lap's lap time minus the median clean lap time of its circuit, in seconds
   (0 is a typical lap there, +1 is one second slower).
4. Race lap (`LapNumber`) stays in the model, because fuel burn and track evolution speed cars up and would otherwise hide tyre wear.
5. A circuit-compound cell with fewer than 4 stints is reported as not estimable and never filled in.
6. Every chart title states its finding, and every chart is explained with a business and a statistical conclusion in `docs/eda.md`.

Result: the raw laps score 8.9 out of 10 (PASS; 6 of 31 checks fail, none critical). The circuit explains 97.9% of lap-time variance. Cars get 0.037 s faster
per race lap. 45 of 57 circuit-compound cells have 8 or more stints and 7 are not estimable.

## Pit-lane loss (P)

A stop costs the two laps around it: **P = in-lap + out-lap - 2 x a normal lap**, where the normal
lap is the same driver's median clean lap within 5 race laps of the stop. P per circuit is the
median over its green-flag, dry stops (a stop under a safety car is cheaper and would bias P down).
**Where the pit-loss definition comes from.** "Pit loss" is the time a stop costs compared with staying on track. There is no official
FIA or Formula 1 definition. Measuring it from lap times is a community convention: in-lap + out-lap - 2 x a normal lap, with the
normal lap taken from laps before the stop (a RaceFans forum thread gives this form, and a variant that averages the three laps before
the in-lap: [I need a stats guru](https://www.racefans.net/groups/f1/forum/topic/i-need-a-stats-guru/)). The same thread separates this
"track time lost" from the total time a stop takes from pit entry to pit exit; we measure the first. Pit loss is largely fixed per circuit
by pit-lane length and speed limit ([Flow Racers](https://flowracers.com/?p=10084)). In this project the formula was set in `docs/scope.md`
section 6 and refined in `f1_pit_strategy/pit_loss.py` (baseline = the driver's median clean lap within 5 race laps of the stop). These
sources are forums and explainers, not official or peer-reviewed. Limits: in-laps and out-laps also contain tyre warm-up and tyre-condition
effects, so P partly reflects them; and a clean baseline needs laps free of traffic and errors (traffic is not filtered in v1).

Result: 317 usable stops, median P 19 to 27 s at 13 of 19 circuits; six circuits have fewer than
10 usable stops and are flagged as thin.

## Degradation rate and the decision

**Degradation (d).** One regression per circuit: lap time on driver intercepts, race lap (fuel burn and track evolution), compound
intercepts and a tyre-age slope per compound. A single stint cannot separate wear from fuel burn, so the model pools stints that start on
different laps. A circuit's rate d is the lap-weighted mean of its compound slopes.

**Decision.** Two stops win when d is above 12P/N². The call is made at the 13 circuits with at least 10 usable green-flag stops (Tier 1);
the other six show d and lap count only, because safety cars and rain left too few green-flag stops to trust P. Result: 5 two-stop and
8 one-stop calls, 4 of them uncertain. Table, chart and limits: [docs/decision.md](docs/decision.md). Fit and residual metrics per circuit: [docs/model_metrics.md](docs/model_metrics.md).

## Hypothesis tests (stage 2)

Weighted least squares (weights 1/SE²) on the 50 circuit-compound slopes: **H2 holds** (a joint F-test shows circuit terms improve the fit, F = 11.1, p = 3e-8; weighted R² rises from 0.21 to 0.91, so a per-circuit rule is justified); **H1 does not**
(a softer compound does not wear faster inside a circuit, whatever the tyre-age window); **H3 is not supported** (p = 0.25 with errors clustered by circuit, and it cannot be tested well with 19 circuits). H1 is recorded as an open warning:
the project makes no compound ranking. Details, chart and limits: [docs/stage2.md](docs/stage2.md).

## Validation

The 13 calls are compared with the pit stops of the cars that finished each race. The model agrees at 10 of 13 circuits; the three that differ (Monaco,
Mexico City, Silverstone) are one-stop calls where most real stops were cheap ones under safety cars, virtual safety cars or red flags. Details,
naive baselines and the Montréal check: [docs/validation.md](docs/validation.md).

## Why these methods

**Regression, not simpler comparisons or ML.** Lap time depends on race lap (fuel and track evolution), car pace and compound as well as tyre age, and tyre age is correlated with race lap
(0.46). Comparing lap time with tyre age alone gives the wrong sign (the EDA shows older tyres look faster), so a multiple regression holds the other variables fixed and returns the
quantity the rule needs: seconds lost per lap of tyre age, with an interval. A machine-learning model would predict lap time better but give no such coefficient, would overfit
cells of 4 to 40 stints, and cannot extrapolate to long stints. Stage 2 weights stint slopes by their precision (inverse variance), because their precision differs several-fold.
Full reasoning and limits: [docs/scope.md](docs/scope.md), section 8.

**A scatter plot for the decision.** The call compares two numbers in the same unit (degradation d against the threshold 12P/N^2), so threshold on x, d on y and a dashed y = x line turns
the rule into geometry: above the line two stops, below one stop. Error bars show the uncertainty of each number, so a reader sees which calls could flip. Reasoning: [docs/decision.md](docs/decision.md).

## Repository layout

| Path | Contents |
|---|---|
| `f1_pit_strategy/config.py` | Paths, season, cleaning thresholds |
| `f1_pit_strategy/ingest.py` | FastF1 → parquet, one file per round |
| `f1_pit_strategy/inspect_raw.py` | Post-ingest validation report |
| `f1_pit_strategy/eda/` | Audit, EDA, charts, insight brief, assumptions log, catalog, methodology and QA gate (`python -m f1_pit_strategy.eda`) |
| `f1_pit_strategy/pit_loss.py` | Pit-lane loss P per circuit, writes `data/processed/pit_loss.csv` |
| `f1_pit_strategy/degradation.py` | Stage 1 model: degradation per circuit and compound, writes `data/processed/degradation_by_*.csv` |
| `f1_pit_strategy/decision.py` | Tier 1 / Tier 2 decision: summary table (`docs/decision.md`) and decision chart |
| `f1_pit_strategy/validate.py` | Compares the calls with real stop counts, writes `docs/validation.md` |
| `f1_pit_strategy/metrics.py` | Fit and residual metrics per circuit, writes `docs/model_metrics.md` |
| `f1_pit_strategy/stage2.py` | Stage 2: tests H1, H2, H3 on the circuit-compound slopes, writes `docs/stage2.md` |
| `f1_pit_strategy/clean.py` | Ordered cleaning rules, writes clean laps and the exclusions audit table |
| `data/processed/` | `clean_laps.parquet` (13 columns, incl. `CompoundAbsolute` C1-C5) and `exclusions.parquet` (one reason per dropped lap) |
| `data/reference/pirelli_allocation.csv` | Per round: host city (the circuit label used everywhere) and SOFT/MEDIUM/HARD mapped to C1–C5 |
| `docs/` | `scope.md` (locked scope and amendments), `PROJECT_LOG.md` (status and decisions), `eda.md` (the eight charts with their conclusions) |
| `reports/presentation/` | The project report as a PDF (29 slides) |
| `reports/figures/` | The eight EDA charts |
| `reports/analysis/` | Nine reports: reconciliation, audit, EDA, findings, insights, assumptions, catalog, methodology, QA |
| `notebooks/` | Exploration (empty so far) |

### Why the allocation table exists

FastF1 reports compounds as SOFT / MEDIUM / HARD, **relative to each race's allocation**.
Pirelli picks three compounds from C1–C5 per race, so "SOFT" denotes different rubber at
different circuits. Without mapping to absolute compounds, the circuit × compound
hypothesis is unidentifiable. That table is compiled by hand from Pirelli's per-race
allocation announcements.

## Known limitations

- The model minimises **race time, not finishing position**. At low-overtaking circuits
  these diverge sharply. This is the central limitation.
- Race lap absorbs fuel burn and track evolution together; race data alone cannot
  separate them, and no claim is made that it does.
- One race per circuit in a single season, so per-circuit estimates carry wide intervals
  and cannot be validated against a second season.
- Safety cars make a pit stop nearly free. The model assumes a green race, which is also
  what teams plan for.
- Tyre allocation limits are not enforced in the optimiser.
- The 25% wet-lap cutoff was chosen by default and tested by a sensitivity run. At 10% Zandvoort and
  Kuala Lumpur are dropped (2 circuits, 83 stints; cells with 8+ stints fall from 45 to 40). At 40%
  São Paulo returns with only the dry laps of a mostly wet race and adds one good cell and two
  empty ones (cells with fewer than 4 stints rise from 7 to 9). Changing the post-rain buffer
  (0 to 5 laps) or the outlier ratio (1.05 to 1.10) left those counts at 45 and 7.
- **Open problem (H1):** softer compounds do not show faster wear in the model (slopes rise with softness in only 6 of 19 circuits; softer is faster when fresh by a median 0.11 s only). This may mean the wear rate d is biased by an unknown amount, so the borderline calls are the most exposed; no compound ranking is claimed. Details and next checks: [docs/stage2.md](docs/stage2.md).
- Dirty-air (traffic) laps are not filtered in v1 and can inflate degradation slopes.
- Mexico City data covers laps 1-56 of a 71-lap race (the API returned no later laps), so
  its degradation estimate rests on tyre ages up to about 43 laps only.
- The Zandvoort GP had intermittent rain; it is kept, using only its dry laps (50 stints).

## Tooling note

**Data access.** Laps, weather and results come through **FastF1**, a Python library (not a database). FastF1 is a client for two web APIs: the Formula 1 live-timing
API (`livetiming.formula1.com`, which needs an F1TV login since FastF1 3.9) for lap timing, tyres, track status and weather, and the Jolpica-F1 API (`api.jolpi.ca`, the
successor of Ergast) for the schedule and race results. The calls are `fastf1.get_event_schedule()` and `fastf1.get_session(...).load(...)`, cached on disk by FastF1.
OpenF1 is the documented fallback source.

**Processing and modelling.** pandas reads and writes the data (one parquet file per race via pyarrow); the model uses `statsmodels` (OLS with cluster-robust standard errors)
and `scipy` (tests); charts use matplotlib.
