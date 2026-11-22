# 07. Data catalog (workflow: data-catalog-entry)

Date: 2026-11-22. Entries are for the files this analysis produces and uses. Technical metadata was extracted from the files, not from a database.

## Entry 1: clean laps

| Field | Value |
|---|---|
| File | `data/processed/clean_laps.parquet` |
| Display name | Clean 2026 race laps |
| Business purpose | Laps that measure tyre wear: normal green-flag racing laps, dry, with a known tyre compound and age. |
| Owner | Project author |
| Criticality | High: the model input |
| Use cases | Degradation model, EDA, stint counts per circuit and compound |
| Rows, columns | 15,206 rows, 13 columns (+ `LapTimeDelta`, derived in memory) |
| Primary key | (Round, Driver, LapNumber), 0 duplicates |
| Foreign keys | Round to `pirelli_allocation.csv`; (Round, Compound) to the allocation ladder |
| Completeness | 100% (no nulls in any column) |
| Freshness | built 71 hours ago from raw files ingested for all 20 rounds |
| Duplicate rate | 0% |
| Known issues | Mexico City laps end at lap 56 of 71; dirty-air laps are not filtered (v1); seven circuit-compound cells have fewer than 4 stints. |
| Upstream | FastF1 (F1TV timing feed) to `data/raw/season=2026/*.parquet` to `f1_pit_strategy/clean.py` |
| Downstream | EDA, quality audit, visuals, insight brief; later the degradation model |
| Access level | Public sports timing data; the repository is published on GitHub |
| Sensitivity | No personal data beyond public driver codes and team names |
| Compliance | Terms for redistributing F1 timing data were not reviewed here; check them before publishing data files. |
| Retention | Reproducible from `data/raw`; no retention limit |

### Columns

| Column | Type | Description | Example | Business rule | Null % |
|---|---|---|---|---|---|
| Round | int8 | Race number in the 2026 calendar (1 to 19 kept; 20 dropped as wet). | 1 | integer 1 to 20 | 0% |
| City | object | Host city or town of the circuit; the label used everywhere. | Melbourne | one of 19 values | 0% |
| Driver | object | Three-letter driver code. | ALB | 24 codes over the season | 0% |
| Team | object | Constructor the driver raced for in that round. | Williams | 11 teams | 0% |
| Stint | int8 | Stint number within the race; 1 is the first set of tyres. | 1 | integer 1 to 10 | 0% |
| LapNumber | int16 | Race lap number; lap 1 is excluded so the minimum is 2. | 2 | 2 to TotalLaps | 0% |
| LapTime | float64 | Lap time in seconds. | 87.78 | 60 to 300 | 0% |
| Compound | string | Relative compound label for this race (the hardest allocated is HARD). | MEDIUM | SOFT, MEDIUM or HARD | 0% |
| CompoundAbsolute | object | Pirelli compound C1 (hardest) to C5 (softest), from the allocation table. | C4 | C1 to C5 | 0% |
| TyreLife | int16 | Laps run on this set, including laps before the race for a used set. | 2 | 1 to 80 | 0% |
| FreshTyre | bool | True if the set was new when fitted. | True | True or False | 0% |
| TrackTemp | float64 | Track temperature in degrees C at the lap start (nearest reading). | 36.0 | 5 to 70 | 0% |
| TotalLaps | int16 | Scheduled race distance in laps. | 58 | 40 to 80 | 0% |

## Entry 2: exclusions (audit table)

| Field | Value |
|---|---|
| File | `data/processed/exclusions.parquet` |
| Business purpose | Every raw lap that was dropped, with exactly one reason, so no row disappears silently. |
| Rows, columns | 8,117 rows, 10 columns |
| Reasons | after_non_green, in_or_out_lap, lap_1, missing_compound, missing_laptime, missing_tyrelife, not_accurate, not_green, short_stint, slow_outlier, wet_or_post_wet, wet_race |
| Rule | Clean rows + excluded rows = raw rows (15,206 + 8,117 = 23,323) |

| Column | Type | Description | Example | Null % |
|---|---|---|---|---|
| Round | int8 | Race number. | 1 | 0% |
| City | object | Host city or town. | Melbourne | 0% |
| Driver | object | Three-letter driver code. | ALB | 0% |
| Stint | int8 | Stint number. | 1 | 0% |
| LapNumber | int16 | Race lap number. | 1 | 0% |
| LapTime | float64 | Lap time in seconds (empty for unfinished laps). | 99.376 | 2% |
| Compound | string | Relative compound label as ingested ('None' is a placeholder text). | MEDIUM | 1% |
| TyreLife | Int16 | Laps on the set (empty if not reported). | 1 | 4% |
| TrackStatus | string | FastF1 track-status code string; '1' is fully green. | 1 | 0% |
| reason | string | The first cleaning rule that dropped the lap. | lap_1 | 0% |

## Entry 3: Pirelli allocation and circuit labels (reference table)

| Field | Value |
|---|---|
| File | `data/reference/pirelli_allocation.csv` (read only here) |
| Business purpose | Gives each round its host-city label and maps SOFT, MEDIUM and HARD to the absolute compounds C1 to C5. |
| Rows, columns | 20 rows (one per round), 8 columns: season, round, city, soft, medium, hard, source, note |
| Owner | Project author (compiled by hand from Pirelli press releases and formula1.com) |
| Known issues | Round 20 (São Paulo) has no allocation because it is dropped as a wet race; accuracy is not cross-checked against a second source. |
