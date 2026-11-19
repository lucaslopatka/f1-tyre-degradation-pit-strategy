# 01. Cleaning funnel and reconciliation (workflow: metric-reconciliation)

Date: 2026-11-19.

## Metric and sources
- **Metric:** number of laps, from the raw files to the processed tables.
- **Source A:** the raw parquet files in `data/raw/season=2026/` (one per round, nothing filtered).
- **Source B:** `data/processed/clean_laps.parquet` plus `data/processed/exclusions.parquet`.
- **Definitions:** a *raw lap* is one row of a round's file; a *clean lap* passes all 13 rules; a *stint* is a distinct (Round, Driver, Stint) among clean laps.

## Reconciliation

| Source A: raw laps | Clean laps | Excluded laps | Source B: clean + excluded | Gap |
|---|---|---|---|---|
| 23,323 | 15,206 | 8,117 | 23,323 | 0 |

The gap is zero: every raw lap is in exactly one table, and every excluded lap has exactly one reason. The clean laps form 854 stints.

## Cleaning funnel

| Reason (in rule order) | Laps dropped | % of raw | Laps left |
|---|---|---|---|
| wet_race | 1,435 | 6.2% | 21,888 |
| missing_laptime | 175 | 0.8% | 21,713 |
| lap_1 | 408 | 1.7% | 21,305 |
| in_or_out_lap | 1,452 | 6.2% | 19,853 |
| not_green | 2,463 | 10.6% | 17,390 |
| after_non_green | 1,114 | 4.8% | 16,276 |
| wet_or_post_wet | 656 | 2.8% | 15,620 |
| not_accurate | 3 | 0.0% | 15,617 |
| missing_compound | 58 | 0.2% | 15,559 |
| missing_tyrelife | 152 | 0.7% | 15,407 |
| bad_track_temp | 0 | 0.0% | 15,407 |
| slow_outlier | 12 | 0.1% | 15,395 |
| short_stint | 189 | 0.8% | 15,206 |

Excluded: 8,117 of 23,323 raw laps (34.8%). 67% of the excluded laps are lap 1, pit, safety-car or restart laps, which are removed by design.

## Retention per circuit

| Round | City | Raw laps | Clean laps | Kept % |
|---|---|---|---|---|
| 20 | São Paulo | 1,435 | 0 | 0.0 |
| 16 | Kuala Lumpur | 1,145 | 385 | 33.6 |
| 12 | Zandvoort | 1,368 | 485 | 35.5 |
| 5 | Montréal | 1,211 | 714 | 59.0 |
| 19 | Mexico City | 1,103 | 682 | 61.8 |
| 15 | Baku | 981 | 648 | 66.1 |
| 9 | Silverstone | 1,113 | 758 | 68.1 |
| 10 | Spa | 872 | 597 | 68.5 |
| 4 | Miami | 1,040 | 712 | 68.5 |
| 2 | Shanghai | 920 | 639 | 69.5 |
| 18 | Austin | 1,164 | 844 | 72.5 |
| 17 | Singapore | 1,240 | 951 | 76.7 |
| 1 | Melbourne | 1,006 | 774 | 76.9 |
| 6 | Monaco | 1,452 | 1,119 | 77.1 |
| 7 | Barcelona | 1,236 | 966 | 78.2 |
| 13 | Monza | 1,054 | 833 | 79.0 |
| 3 | Suzuka | 1,107 | 891 | 80.5 |
| 11 | Budapest | 1,431 | 1,175 | 82.1 |
| 14 | Madrid | 1,106 | 915 | 82.7 |
| 8 | Spielberg | 1,339 | 1,118 | 83.5 |
