# 02. Data quality audit (skill: data-quality-audit)

Date: 2026-11-22. Assessed by: Claude with the project author.
Dataset: the ingested laps, `data/raw/season=2026/round=NN.parquet` (23,323 rows, 31 columns, 20 races).
Scope: full table, before any cleaning. A second table at the end checks the cleaned output.

## Verdict: PASS (8.9 / 10)

6 of 31 checks failed; none is CRITICAL. The failures are placeholder values, a truncated race, and unmapped compounds in the dropped wet race; the
cleaning rules handle them or the author has accepted them. The cleaned data passes all 11 guarantees: **yes**.

Scoring rule: each dimension starts at 10 and loses
CRITICAL 5, HIGH 2, MEDIUM 1, LOW 0.5 points per failed check. Bands: PASS from 7.0, CONDITIONAL 5.0 to 6.9, FAIL below 5.0.

## Scores by dimension

| Dimension | Weight | Score (0-10) | Weighted | Key issues |
|---|---|---|---|---|
| Completeness | 20% | 7.0 | 1.4 | No placeholder values hiding as data; Every race reaches its scheduled distance |
| Accuracy | 20% | 9.0 | 1.8 | No impossible sensor readings (TrackTemp 0.0) |
| Consistency | 20% | 9.5 | 1.9 | Every dry-compound lap maps to a C1 to C5 compound |
| Timeliness | 15% | 10.0 | 1.5 | none |
| Uniqueness | 15% | 10.0 | 1.5 | none |
| Validity | 10% | 8.0 | 0.8 | TrackTemp within 5 to 70; Compound is one of SOFT, MEDIUM, HARD, INTERMEDIATE, WET |

**Overall: 8.9 / 10.**

## Critical findings (fix before use)

None.

## High severity

| # | Dimension | Finding | Rows affected | Handling |
|---|---|---|---|---|
| 1 | Completeness | Every race reaches its scheduled distance: round 19 (Mexico City) ends at lap 56 of 71 | 274 | accepted by the author; N = 71 used for the threshold |

## Medium and low (document and monitor)

| Dimension | Finding | Rows affected | Handling |
|---|---|---|---|
| Completeness | No placeholder values hiding as data: 84 laps have the text 'None' as compound; 26 laps have TrackTemp 0.0 | 110 | rules missing_compound and bad_track_temp |
| Validity | TrackTemp within 5 to 70: 26 values outside | 26 | removed by the cleaning rules |
| Validity | Compound is one of SOFT, MEDIUM, HARD, INTERMEDIATE, WET: 84 laps outside the set (the text 'None') | 84 | rule missing_compound |
| Accuracy | No impossible sensor readings (TrackTemp 0.0): 26 laps have TrackTemp exactly 0.0 (a missing reading stored as zero) | 26 | rule bad_track_temp; all fall in the wet race that is dropped |
| Consistency | Every dry-compound lap maps to a C1 to C5 compound: 914 of 22,582 dry laps (4.0%) have no mapping; round(s) [20] (São Paulo, dropped as a wet race) | 914 | the race is excluded, so no clean lap is affected |

## Checks performed

| Dimension | Check | Result | Details |
|---|---|---|---|
| Completeness | Model-critical columns have under 5% nulls | PASS | worst is TyreLife at 1.3% |
| Completeness | Every column with 5% or more nulls has a known reason | PASS | none unexplained |
| Completeness | Columns at 30% or more nulls are unused or structural | PASS | PitInTime (96%), PitOutTime (96%), Deleted (100%); none is a model input |
| Completeness | No placeholder values hiding as data | FAIL (MEDIUM) | 84 laps have the text 'None' as compound; 26 laps have TrackTemp 0.0 |
| Completeness | Every race reaches its scheduled distance | FAIL (HIGH) | round 19 (Mexico City) ends at lap 56 of 71 |
| Uniqueness | No full-row duplicates (limit 1%) | PASS | 0 duplicate rows |
| Uniqueness | (Round, Driver, LapNumber) is a unique key | PASS | 0 duplicate keys |
| Validity | LapTime within 60 to 300 | PASS | 0 values outside |
| Validity | LapNumber within 1 to 80 | PASS | 0 values outside |
| Validity | Stint within 1 to 10 | PASS | 0 values outside |
| Validity | TyreLife within 1 to 80 | PASS | 0 values outside |
| Validity | TrackTemp within 5 to 70 | FAIL (MEDIUM) | 26 values outside |
| Validity | AirTemp within 0 to 50 | PASS | 0 values outside |
| Validity | Humidity within 0 to 100 | PASS | 0 values outside |
| Validity | Pressure within 700 to 1100 | PASS | 0 values outside |
| Validity | WindSpeed within 0 to 30 | PASS | 0 values outside |
| Validity | Position within 1 to 22 | PASS | 0 values outside |
| Validity | TotalLaps within 40 to 80 | PASS | 0 values outside |
| Validity | Compound is one of SOFT, MEDIUM, HARD, INTERMEDIATE, WET | FAIL (MEDIUM) | 84 laps outside the set (the text 'None') |
| Validity | LapNumber never exceeds TotalLaps | PASS | 0 laps beyond the distance |
| Consistency | A driver has one team within a race | PASS | 0 driver-race pairs with two teams |
| Consistency | Tyre age rises by the same amount as the race lap inside a stint | PASS | 0 steps disagree |
| Consistency | LapTime matches the sum of its three sectors (0.1 s) | PASS | 0 of 22,716 laps differ by more than 0.1 s (0.00%) |
| Consistency | Every raw round exists in the reference table | PASS | 0 rounds missing |
| Consistency | Every dry-compound lap maps to a C1 to C5 compound | FAIL (LOW) | 914 of 22,582 dry laps (4.0%) have no mapping; round(s) [20] (São Paulo, dropped as a wet race) |
| Consistency | TotalLaps is constant within a race | PASS | 0 races vary |
| Accuracy | FastF1 flags under 1% of normal green laps as not accurate | PASS | 3 of 18,636 normal green laps (0.02%); across all laps 15.8% are flagged, mostly pit, lap-1 and safety-car laps |
| Accuracy | No impossible sensor readings (TrackTemp 0.0) | FAIL (MEDIUM) | 26 laps have TrackTemp exactly 0.0 (a missing reading stored as zero) |
| Accuracy | Lap data matches an independent source | PASS | not re-tested here; the 20 drivers of round 1 matched FastF1's race results in an earlier session |
| Timeliness | All expected rounds are present (20 of 20) | PASS | 20 rounds ingested, 20 expected from the reference table |
| Timeliness | Raw files are newer than the last schedule change | PASS | oldest file 98 h old, newest 98 h old; no feed SLA exists for a finished season |

## Null profile (columns with any nulls; WARN from 5%, FAIL from 30%)

|  | Null % | Status | Explanation |
|---|---|---|---|
| Position | 0.2 | OK | missing on a few laps |
| LapTime | 0.8 | OK | unfinished laps (retirements, red flags) |
| PitInTime | 96.3 | FAIL | only set on in-laps |
| PitOutTime | 96.4 | FAIL | only set on out-laps |
| Sector1Time | 2.4 | OK | missing on laps without a full timing trace |
| Sector2Time | 0.2 | OK | missing on laps without a full timing trace |
| Sector3Time | 0.4 | OK | missing on laps without a full timing trace |
| TyreLife | 1.3 | OK | tyre age not reported on some laps |
| Deleted | 100.0 | FAIL | FastF1 field that this feed never fills |

## Value-range rules

| Column | Rule | Min seen | Max seen | Violations |
|---|---|---|---|---|
| LapTime | 60 to 300 | 70.4 | 217.9 | 0 |
| LapNumber | 1 to 80 | 1.0 | 78.0 | 0 |
| Stint | 1 to 10 | 1.0 | 8.0 | 0 |
| TyreLife | 1 to 80 | 1.0 | 67.0 | 0 |
| TrackTemp | 5 to 70 | 0.0 | 56.9 | 26 |
| AirTemp | 0 to 50 | 12.1 | 35.1 | 0 |
| Humidity | 0 to 100 | 20.5 | 89.7 | 0 |
| Pressure | 700 to 1100 | 783.0 | 1024.7 | 0 |
| WindSpeed | 0 to 30 | 0.0 | 5.1 | 0 |
| Position | 1 to 22 | 1.0 | 22.0 | 0 |
| TotalLaps | 40 to 80 | 44.0 | 78.0 | 0 |

## Freshness

| Files | Oldest (h) | Newest (h) |
|---|---|---|
| 20 | 97.9 | 97.8 |

The season is finished, so there is no feed SLA; the check is coverage: all 20 expected rounds are present.

## Guarantees on the cleaned laps (`data/processed/clean_laps.parquet`)

| Guarantee on clean laps | Result |
|---|---|
| No missing values in any column | PASS |
| (Round, Driver, LapNumber) is unique | PASS |
| LapTime between 60 and 300 s | PASS |
| TyreLife between 1 and 80 | PASS |
| TrackTemp between 5 and 70 | PASS |
| LapNumber is at least 2 and never above TotalLaps | PASS |
| Compound is SOFT, MEDIUM or HARD only | PASS |
| CompoundAbsolute matches the allocation table | PASS |
| Every stint has a single compound | PASS |
| Every stint has at least 5 laps | PASS |
| The wet race (São Paulo, round 20) is absent | PASS |

## Sign-off
- **Approved for:** the cleaning, modelling and reporting steps of this project, using the cleaned laps.
- **Not approved for:** use of the raw laps without the cleaning rules.

| Action | Owner | Status |
|---|---|---|
| Accept Mexico City laps 57 to 71 as missing, or retry the download | Author | accepted 2026-11-19 |
| Keep placeholder handling (`'None'`, TrackTemp 0.0) in the cleaning rules | Analyst | in place |
| Add a traffic (dirty-air) filter in v2 | Analyst | deferred |
