# 03. EDA report (workflow: programmatic-eda)

Analyst: Claude with the project author. Date: 2026-11-22.
Dataset: `data/processed/clean_laps.parquet`.
Business context: each row is one normal racing lap; the data informs the one-stop versus two-stop decision per circuit.
Thresholds: null 5%/30%, |z| 3, IQR 1.5, skew 0.5/1/2, |r| 0.8, set in `f1_pit_strategy/eda/settings.py`.

## 1. Dataset overview
- Rows 15,206; columns 13 stored + 1 derived (`LapTimeDelta`); memory 4.6 MB.
- Date range: none stored; the season is 2026, rounds 1 to 19.
- Grain: one row = one clean lap by one driver. Primary key (Round, Driver, LapNumber): 0 duplicates.
- `LapTimeDelta` = lap time minus the median clean lap time of the same circuit, in seconds (0 = a typical lap there, +1 = one second slower).

| Column | Type | Non-null % | Distinct | Example |
|---|---|---|---|---|
| Round | int8 | 100.0 | 19 | 1 |
| City | object | 100.0 | 19 | Melbourne |
| Driver | object | 100.0 | 24 | ALB |
| Team | object | 100.0 | 11 | Williams |
| Stint | int8 | 100.0 | 8 | 1 |
| LapNumber | int16 | 100.0 | 77 | 2 |
| LapTime | float64 | 100.0 | 12,148 | 87.78 |
| Compound | string | 100.0 | 3 | MEDIUM |
| CompoundAbsolute | object | 100.0 | 5 | C4 |
| TyreLife | int16 | 100.0 | 56 | 2 |
| FreshTyre | bool | 100.0 | 2 | True |
| TrackTemp | float64 | 100.0 | 286 | 36.0 |
| TotalLaps | int16 | 100.0 | 15 | 58 |
| LapTimeDelta | float64 | 100.0 | 10,495 | 2.953000000000003 |

## 2. Null and completeness profile
All 13 columns have 0% nulls: status OK everywhere. The raw data had structural nulls (pit times, sectors) and
placeholder values; those are covered in report 02.

## 3. Duplicate analysis
Full-row duplicates: 0. Duplicate keys: 0. Nothing to investigate.

## 4. Validity checks
Range, category and consistency guarantees on the cleaned laps all pass (see report 02, last table).

## 5. Distributions

| Column | mean | median | std | p5 | p95 | min | max | skew | kurtosis | skew flag |
|---|---|---|---|---|---|---|---|---|---|---|
| Stint | 1.92 | 2.0 | 0.89 | 1.0 | 3.0 | 1.0 | 8.0 | 1.28 | 3.25 | high |
| LapNumber | 30.28 | 29.0 | 17.17 | 5.0 | 60.0 | 2.0 | 78.0 | 0.29 | -0.76 | ok |
| LapTime | 90.42 | 88.31 | 10.83 | 73.61 | 109.49 | 70.37 | 122.04 | 0.14 | -0.95 | ok |
| TyreLife | 15.78 | 14.0 | 9.86 | 3.0 | 35.0 | 2.0 | 57.0 | 0.92 | 0.6 | moderate |
| TrackTemp | 41.03 | 42.2 | 9.77 | 20.1 | 54.0 | 17.1 | 56.8 | -0.59 | -0.26 | moderate |
| TotalLaps | 61.52 | 58.0 | 8.91 | 51.0 | 78.0 | 44.0 | 78.0 | 0.17 | -0.98 | ok |
| LapTimeDelta | 0.15 | 0.0 | 1.59 | -2.19 | 3.0 | -5.23 | 10.88 | 0.58 | 0.78 | moderate |

Skew flags: Stint (high), TyreLife (moderate), TrackTemp (moderate), LapTimeDelta (moderate). None is extreme (above 2), so no transformation is needed.
`Stint` is skewed because most drivers make one to three stints; `TyreLife` is right-skewed because few stints run long; pooled `LapTime` is
roughly symmetric because slow and fast circuits balance out.

Category balance (flag above 90%; `FreshTyre` is 89.8% True, just under the flag):

| Column | Distinct | Largest category | Share | Over 90%? |
|---|---|---|---|---|
| City | 19 | Budapest | 7.7% | ok |
| Driver | 24 | ANT | 5.4% | ok |
| Team | 11 | Mercedes | 10.4% | ok |
| Compound | 3 | HARD | 43.6% | ok |
| CompoundAbsolute | 5 | C4 | 29.2% | ok |
| FreshTyre | 2 | True | 89.8% | ok |

## 6. Outliers (flagged for review, never auto-removed)

| Column | IQR flags | IQR % | |z|>3 flags | z % | Class | Decision |
|---|---|---|---|---|---|---|
| Stint | 689 | 4.5% | 182 | 1.2% | real | keep: multi-stop races |
| LapNumber | 0 | 0.0% | 0 | 0.0% | real | keep: long races such as Monaco (78 laps) |
| LapTime | 0 | 0.0% | 0 | 0.0% | real (structural) | keep: circuit differences make slow circuits look extreme when pooled; judged by circuit below |
| TyreLife | 366 | 2.4% | 137 | 0.9% | real | keep: long stints are the evidence for one-stop strategies |
| TrackTemp | 0 | 0.0% | 0 | 0.0% | real | keep: hot and cool race days |
| TotalLaps | 0 | 0.0% | 0 | 0.0% | structural | keep: race distance differs by circuit |
| LapTimeDelta | 225 | 1.5% | 88 | 0.6% | real | keep: slow laps that survived the 1.07 stint-median rule (traffic, late tyre drop-off); a v2 traffic filter may remove more |

Pooled `LapTime` flags none, because the spread between circuits is wider than any single slow lap; judged within each circuit, 200 laps (1.3%) are IQR outliers.
`Stint` flags many laps because drivers who stop three or more times are rare, not because the values are wrong.

## 7. Correlations
Pairs with |r| of 0.8 or more: **0**. Largest: TyreLife vs LapNumber at +0.46.

Pearson:

|  | LapTime | LapTimeDelta | TyreLife | LapNumber | TrackTemp | FreshTyre |
|---|---|---|---|---|---|---|
| LapTime | 1.00 | 0.15 | -0.03 | -0.22 | -0.17 | 0.07 |
| LapTimeDelta | 0.15 | 1.00 | -0.08 | -0.40 | 0.03 | 0.16 |
| TyreLife | -0.03 | -0.08 | 1.00 | 0.46 | -0.08 | -0.05 |
| LapNumber | -0.22 | -0.40 | 0.46 | 1.00 | -0.08 | -0.15 |
| TrackTemp | -0.17 | 0.03 | -0.08 | -0.08 | 1.00 | 0.14 |
| FreshTyre | 0.07 | 0.16 | -0.05 | -0.15 | 0.14 | 1.00 |

Spearman (rank-based, robust to skew):

|  | LapTime | LapTimeDelta | TyreLife | LapNumber | TrackTemp | FreshTyre |
|---|---|---|---|---|---|---|
| LapTime | 1.00 | 0.17 | -0.01 | -0.20 | -0.18 | 0.08 |
| LapTimeDelta | 0.17 | 1.00 | -0.09 | -0.42 | 0.05 | 0.16 |
| TyreLife | -0.01 | -0.09 | 1.00 | 0.47 | -0.07 | -0.07 |
| LapNumber | -0.20 | -0.42 | 0.47 | 1.00 | -0.10 | -0.12 |
| TrackTemp | -0.18 | 0.05 | -0.07 | -0.10 | 1.00 | 0.14 |
| FreshTyre | 0.08 | 0.16 | -0.07 | -0.12 | 0.14 | 1.00 |

Variance inflation factors: TyreLife 1.28, LapNumber 1.30, TrackTemp 1.03, FreshTyre 1.04. All are below 5, so `TyreLife` and `LapNumber` can be in one model.
Raw `LapTime` correlations mostly measure which circuit the lap is from (97.9% of its variance is between circuits), so read the `LapTimeDelta` column for within-circuit effects.

## 8. Business logic checks

| Business rule | Result | Evidence |
|---|---|---|
| Fuel burn and track evolution make laps faster as a race goes on | PASS | slope of LapTimeDelta on LapNumber is -0.0366 s per lap; laps 2-6 average +1.14 s, laps 60+ average -0.84 s |
| Tyre age rises exactly with the race lap inside each stint | PASS | every step in tyre age equals the step in race lap, including after dropped laps |
| CompoundAbsolute equals the allocation table for every lap | PASS | 15,206 laps checked |
| Circuit median lap times are plausible for F1 (60 to 130 s) | PASS | medians run 72.9 to 111.7 s |
| Clean plus excluded laps equal raw laps | PASS | 15,206 + 8,117 = 23,323 vs 23,323 raw |

## 9. EDA checklist sign-off (43 items)

| Section | Item | Status | Evidence |
|---|---|---|---|
| 1 Structure | File loads without errors | PASS | parquet read cleanly |
| 1 Structure | Row count is plausible | PASS | 15,206 clean laps from 23,323 raw over 19 circuits |
| 1 Structure | Column count matches the schema documentation | PASS | 13 stored columns = config.CLEAN_COLUMNS (LapTimeDelta is derived here) |
| 1 Structure | Column names are clear, no unnamed or duplicates | PASS | 13 distinct readable names |
| 1 Structure | Grain identified | PASS | one row = one clean lap by one driver |
| 1 Structure | Primary key identified and unique | PASS | (Round, Driver, LapNumber): 0 duplicates |
| 1 Structure | Each column has the right type | PASS | ints for counts, floats for seconds, text for labels, bool for FreshTyre |
| 1 Structure | Joins do not inflate row counts | PASS | allocation join is many-to-one and validated; row count unchanged |
| 2 Completeness | Null counts reviewed for every column | PASS | 0 nulls in all 13 columns (raw nulls are in report 02) |
| 2 Completeness | Null rates compared with thresholds | PASS | 0% everywhere; raw columns over 30% are structural |
| 2 Completeness | Columns over 30% nulls justified | PASS | none in the clean data |
| 2 Completeness | Zeros are meaningful, not stand-ins | PASS | TrackTemp 0.0 sentinel removed; clean minimum is 17.1 |
| 2 Completeness | Expected null rate for optional columns documented | PASS | EXPECTED_NULLS in eda/settings.py and report 02 |
| 3 Uniqueness | Full-row duplicates checked | PASS | 0 duplicates |
| 3 Uniqueness | Key-level duplicates checked | PASS | 0 duplicates |
| 3 Uniqueness | Partial duplicates (same ID, different timestamp) | N/A | no timestamps in the clean data |
| 3 Uniqueness | Duplicate rate under 1% or explained | PASS | 0% |
| 4 Validity | Numeric values inside business ranges | PASS | all range guarantees pass (report 02) |
| 4 Validity | Categoricals hold only expected values | PASS | Compound is SOFT/MEDIUM/HARD; CompoundAbsolute is C1-C5 |
| 4 Validity | Dates inside the expected range | N/A | no date columns |
| 4 Validity | Referential integrity or orphan rate documented | PASS | orphans exist only for the dropped wet race (report 02) |
| 4 Validity | Booleans hold only True or False | PASS | FreshTyre has no nulls |
| 5 Distributions | Descriptive statistics reviewed | PASS | table in section 5 |
| 5 Distributions | Columns with |skew| above 2 flagged | PASS | none above 2 |
| 5 Distributions | Outliers reviewed as real or error | PASS | classified in section 6; none removed |
| 5 Distributions | No category dominates unexpectedly (over 90%) | PASS | largest share is below 90% |
| 5 Distributions | Coverage gaps checked | WARN | 219 race laps have no clean lap at all; most in Zandvoort (37), Mexico City (32), Kuala Lumpur (28); the rest are safety-car stretches |
| 6 Correlations | Pairwise correlations computed | PASS | Pearson and Spearman in section 7 |
| 6 Correlations | Pairs with |r| of 0.8 or more explained | PASS | none; largest is TyreLife vs LapNumber at +0.46 |
| 6 Correlations | Known relationships hold | PASS | race lap vs circuit-adjusted lap time is -0.40 (fuel burn) |
| 6 Correlations | Surprising zero correlations investigated | PASS | TrackTemp 0.03 with adjusted lap time: temperature varies between circuits, not within |
| 7 Time-series | Time column monotonic or gaps documented | PASS | race laps rise within each driver; gaps are exclusions |
| 7 Time-series | Latest record within expected lag | N/A | finished season, no feed |
| 7 Time-series | Volume over time reviewed for drops | PASS | fewer clean laps late in races (retirements, stops, safety cars); Mexico City stops at lap 56 |
| 7 Time-series | Weekend and holiday effects noted | N/A | not daily data |
| 8 Business logic | Directional relationships correct | PASS | fuel and track effect is negative (section 8) |
| 8 Business logic | Derived columns verified against sources | PASS | CompoundAbsolute vs allocation table; LapTimeDelta median is 0 per circuit |
| 8 Business logic | Totals reconcile with the aggregate | PASS | clean + excluded = raw (report 01) |
| 8 Business logic | Known data issues documented | PASS | Mexico City truncation, wet cutoff default, dirty air (assumptions log) |
| 9 Sign-off | FAIL-level items resolved or accepted | PASS | Mexico City truncation accepted by the author |
| 9 Sign-off | WARN-level items in the findings summary | PASS | report 04 |
| 9 Sign-off | EDA report completed | PASS | this file |
| 9 Sign-off | Next step confirmed | PASS | data ready for modelling; later steps are documented in docs/PROJECT_LOG.md |

Result: 38 pass, 1 warn, 4 not applicable, 0 fail.
**Final status: ready to proceed.** Warnings are carried into `04_findings_summary.md`.
