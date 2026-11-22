# 08. Methodology (workflows: analysis-documentation, methodology-explainer)

Date: 2026-11-22. Audience: mixed (business reader and technical reviewer); each section says which.

## 1. Business context
- **Question:** at a given circuit, under dry green-flag conditions, when does a two-stop strategy beat a one-stop?
- **Decision:** the pre-race stop-count call. **Output (later):** a rule per circuit: two stops win when `beta > 12P / N^2`.
- **Success criteria for this stage:** a clean, documented lap dataset with every exclusion logged, and a clear view of what it can support.

## 2. Data sources

| Source | File | Rows | Coverage | Key columns | Known quality issues | Exclusions |
|---|---|---|---|---|---|---|
| FastF1 race laps | `data/raw/season=2026/round=NN.parquet` | 23,323 | 20 races, 2026 | Round, Driver, LapNumber, LapTime, Compound, TyreLife, TrackStatus | placeholder 'None' compounds, TrackTemp 0.0, Mexico City ends at lap 56 | none (raw layer) |
| Pirelli allocation | `data/reference/pirelli_allocation.csv` | 20 | 2026 | round, city, soft, medium, hard | hand-compiled; no second-source check | round 20 has no allocation |
| Clean laps | `data/processed/clean_laps.parquet` | 15,206 | 19 races | 13 columns | dirty-air laps remain | 8,117 raw laps dropped, each with a reason |

## 3. Methodology
**Approach (this stage).**
1. Ingestion (done earlier): FastF1 to one parquet file per race; nothing filtered.
2. Cleaning: 13 ordered rules in `f1_pit_strategy/clean.py`; each lap gets the first rule that drops it; thresholds in `f1_pit_strategy/config.py`.
3. Reconciliation: raw laps = clean laps + excluded laps, one reason per excluded lap (report 01).
4. Quality audit (six dimensions), EDA (43-item checklist), charts, insight brief, assumptions log and catalog. The audit and EDA follow the workflows of the data-analytics-skills repository (https://github.com/nimrodfisher/data-analytics-skills).

**Tools and versions**

| Tool | Version |
|---|---|
| Python | 3.13.9 |
| pandas | 2.3.3 |
| numpy | 2.5.5 |
| pyarrow | 26.0.1 |
| statsmodels | 0.15.0 |
| matplotlib | 3.11.2 |
| fastf1 | 3.9.2 |

**Key decisions and alternatives** (full list in report 06): wet races are dropped above 25% wet laps (alternative: drop any rain); the lap after
a safety car is dropped (alternative: keep it); compounds are modelled as C1 to C5 (alternative: relative labels); the traffic filter is deferred to v2.

**Assumptions:** see `06_assumptions_log.md`; two are critical under its rule of low confidence and high impact (a C-number is one recipe at every race; fuel and track effect
equal at every circuit). Two more have high impact and medium confidence (allocation table accuracy; identification from different stint start laps).

## 4. Results
- 23,323 raw laps became 15,206 clean laps (65.2%) in 854 stints over 19 circuits; 8,117 laps dropped, each with one reason.
- Audit: all cleaned-data guarantees pass; the raw data has six failed checks (placeholders, a truncated race), none critical (report 02).
- Race lap effect: -0.0366 s per lap on circuit-adjusted lap time; the circuit explains 98% of raw lap-time variance (report 03 and `docs/eda.md`).
- Coverage: 45 of 57 circuit-compound cells have 8 or more stints, 7 have fewer than 4.
- Charts: `reports/figures/01` to `08`, explained in `docs/eda.md`.

## 5. Insights and recommendations
See `05_insight_brief.md`: keep race lap in the model, make estimates within each circuit, mark thin cells not estimable, flag one-stop verdicts that rely on long tyre ages.

## 6. Reproducibility
- **Data access:** the raw layer is the existing `data/raw`. Re-downloading needs FastF1 3.9 or later and an F1TV login that FastF1 stores locally; no credentials are used or stored here.
- **Environment:** the project's `.venv` with `requirements.txt`; versions above.
- **Execution order:**

```bash
source .venv/bin/activate
python -m f1_pit_strategy.ingest      # raw laps (skips rounds already written)
python -m f1_pit_strategy.clean       # clean laps and exclusions
python -m f1_pit_strategy.eda         # audit, EDA, charts, reports
```

- **Randomness:** none; every number is deterministic.

---

## The method at three levels (methodology-explainer)

### Executive: why and what
We want to know, track by track, whether a team should stop once or twice. That depends on how fast tyres wear out. Before measuring wear, we
cleaned the race data so that only normal racing laps remain, and we checked the cleaned data from every angle. The data is good enough to go on,
with two limits: a few tyre choices were barely used at some tracks, and one race is missing its last 15 laps.

### Business analyst: what and how
Of 23,323 laps we kept 15,206. We removed pit laps, first laps, safety-car and restart laps, wet laps and a handful of faulty readings,
and we logged every removed lap with its reason. Cars get faster through a race as fuel burns, so a quick look at lap time against tyre age
points the wrong way; the model will have to correct for that. Each track is judged against its own typical lap.

### Technical peer: full detail
Thirteen ordered rules assign each lap its first failing reason (a loop of `Series.mask` calls, so one reason per lap); the two stint-level rules (outlier above 1.07 x
stint median, fewer than 5 remaining laps) run after the row rules so they see only surviving laps. `LapTimeDelta` is lap time minus the circuit median of clean laps.
The race-lap slope is an OLS fit of `LapTimeDelta` on `LapNumber`. Variance inflation factors for `TyreLife`, `LapNumber`, `TrackTemp`, `FreshTyre` are 1.0 to 1.3.
Stage 1 (built, `f1_pit_strategy/degradation.py`) fits one regression per circuit: driver intercepts, a shared race-lap term and a tyre-age slope per compound, with standard errors clustered by stint. Stage 2 (planned) regresses the compound slopes on compound, circuit and temperature, weighted by precision.

### Limitations (what they mean for the conclusions)
- Race lap carries fuel burn and track evolution together, so only their sum is estimated.
- One race per circuit and one season: per-circuit intervals will be wide and cannot be checked against another year.
- Dirty-air laps are still included, so slopes may be somewhat too steep.
- The 25% wet cutoff and the compound-recipe assumption are not tested against outside data.
