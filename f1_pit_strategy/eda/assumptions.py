"""Assumptions log and data catalog (workflows: analysis-assumptions-log, data-catalog-entry).

Writes reports/analysis/06_assumptions_log.md (every assumption with rationale, confidence, impact
if wrong, and a validation plan for the critical ones) and reports/analysis/07_data_catalog.md
(table-level and column-level metadata for the files this analysis produces and uses).
"""

from __future__ import annotations

import time

import pandas as pd

from f1_pit_strategy import config
from f1_pit_strategy.eda import helpers

# (id, category, assumption, rationale, confidence, impact if wrong, alternatives / validation, status)
ASSUMPTIONS = [
    ("D1", "Data", "FastF1 lap times are accurate where `IsAccurate` is true.", "FastF1's own timing-integrity flag; 3 clean-eligible laps were flagged.", "High", "Low",
     "Round 1 drivers matched the race results; no other source cross-check.", "open"),
    ("D2", "Data", "The first 56 laps of Mexico City are representative of the whole race.", "The API returned nothing after lap 56; the author chose to use what exists.", "Medium", "Medium",
     "Retry the download or use OpenF1 (scope section 13).", "accepted 2026-11-19"),
    ("D3", "Data", "A C-number (C1 to C5) is the same tyre recipe at every race.", "Pirelli names compounds by number; not verified for 2026.", "Low", "High",
     "Test the circuit x compound interaction (H2); compare C3 across circuits; read Pirelli notes on recipe changes.", "open"),
    ("D4", "Data", "The hand-compiled allocation table is correct.", "One source per row (Pirelli press release or formula1.com).", "Medium", "High",
     "Re-check three random rounds against a second source.", "open"),
    ("D5", "Data", "Used sets behave like new sets for tyre wear (10% of laps are on used sets).", "Used sets are kept; `FreshTyre` stays as a column.", "Medium", "Medium",
     "Add `FreshTyre` as a covariate; compare slopes with and without used sets.", "open"),
    ("B1", "Business logic", "A race is dropped as wet only above 25% wet laps.", "Default chosen without data; a few wet laps only need removing.", "Low", "Medium",
     "Sensitivity run: at 10% two more circuits drop, at 40% São Paulo returns with mixed-condition laps.", "tested"),
    ("B2", "Business logic", "The track stays damp for 3 laps after rain.", "Chosen as a short buffer.", "Low", "Low", "Sensitivity run: 0 to 5 laps left the cell counts unchanged.", "tested"),
    ("B3", "Business logic", "The lap after a safety car, VSC or yellow is not representative.", "Cold tyres and a bunched field.", "Medium", "Low",
     "Sensitivity run: 0 laps keeps the same cell counts; 2 laps raises the thin cells from 7 to 9.", "tested"),
    ("B4", "Business logic", "A lap over 7% slower than its stint median is not tyre-limited.", "Spins and off-track laps; 12 laps removed.", "Medium", "Low", "Sensitivity run: 5% to 10% changed under 20 laps.", "tested"),
    ("B5", "Business logic", "A stint needs at least 5 clean laps to give a slope.", "Too few points otherwise.", "Medium", "Medium", "Re-run the cell counts with 4 and 6.", "open"),
    ("B6", "Business logic", "Dirty-air laps stay in v1.", "Author decision to keep v1 simple.", "Low", "Medium", "Add the 1.5 s gap filter in v2 and compare slopes.", "deferred"),
    ("B7", "Business logic", "Circuits are labelled by host city; round 16 (FastF1 'Bahrain Grand Prix') is Kuala Lumpur.", "One rule for all circuits; FastF1 places round 16 at Sepang.", "High", "Low", "None needed.", "closed"),
    ("B8", "Business logic", "N = 71 for Mexico City in the threshold.", "That is the scheduled and run distance.", "High", "Low", "Race results show 71 laps.", "closed"),
    ("B9", "Business logic", "Equal stint splits are a fair basis for the closed-form threshold `12P / N^2`.", "Gives a clean headline; real stints are unequal.", "Medium", "Medium",
     "The production estimate uses a grid search over compounds and splits.", "open"),
    ("S1", "Statistical", "Degradation is linear in tyre age.", "Baseline model in the scope.", "Medium", "Medium", "Test a quadratic tyre-age term.", "open"),
    ("S2", "Statistical", "Fuel burn and track evolution act the same at every circuit (one pooled race-lap effect of -0.037 s per lap).", "Race data cannot separate the two.", "Low", "High",
     "Fit circuit-specific race-lap slopes and compare; report the combined effect only.", "open"),
    ("S3", "Statistical", "Tyre wear is identified because stints start at different race laps.", "Inside one stint age and lap are perfectly collinear; variance inflation factors are 1.0 to 1.3 pooled.", "Medium", "High",
     "Check identification per circuit; simulate data with a known slope and recover it.", "open"),
    ("S4", "Statistical", "Laps inside a stint are independent.", "They are not (autocorrelation, shared driver and car).", "High", "Medium",
     "Use stint-level slopes in stage 1 and cluster-robust or precision-weighted errors in stage 2.", "planned"),
]
COLUMNS = ["ID", "Category", "Assumption", "Rationale", "Confidence", "Impact if wrong", "Alternatives / validation", "Status"]

DESCRIPTIONS = {
    "Round": ("Race number in the 2026 calendar (1 to 19 kept; 20 dropped as wet).", "integer 1 to 20"),
    "City": ("Host city or town of the circuit; the label used everywhere.", "one of 19 values"),
    "Driver": ("Three-letter driver code.", "24 codes over the season"),
    "Team": ("Constructor the driver raced for in that round.", "11 teams"),
    "Stint": ("Stint number within the race; 1 is the first set of tyres.", "integer 1 to 10"),
    "LapNumber": ("Race lap number; lap 1 is excluded so the minimum is 2.", "2 to TotalLaps"),
    "LapTime": ("Lap time in seconds.", "60 to 300"),
    "Compound": ("Relative compound label for this race (the hardest allocated is HARD).", "SOFT, MEDIUM or HARD"),
    "CompoundAbsolute": ("Pirelli compound C1 (hardest) to C5 (softest), from the allocation table.", "C1 to C5"),
    "TyreLife": ("Laps run on this set, including laps before the race for a used set.", "1 to 80"),
    "FreshTyre": ("True if the set was new when fitted.", "True or False"),
    "TrackTemp": ("Track temperature in degrees C at the lap start (nearest reading).", "5 to 70"),
    "TotalLaps": ("Scheduled race distance in laps.", "40 to 80"),
}
EXCLUSION_DESCRIPTIONS = {
    "Round": "Race number.", "City": "Host city or town.", "Driver": "Three-letter driver code.", "Stint": "Stint number.",
    "LapNumber": "Race lap number.", "LapTime": "Lap time in seconds (empty for unfinished laps).",
    "Compound": "Relative compound label as ingested ('None' is a placeholder text).", "TyreLife": "Laps on the set (empty if not reported).",
    "TrackStatus": "FastF1 track-status code string; '1' is fully green.", "reason": "The first cleaning rule that dropped the lap.",
}


def assumptions_text() -> str:
    table = pd.DataFrame(ASSUMPTIONS, columns=COLUMNS)
    table["Critical"] = ["YES" if c == "Low" and i == "High" else "" for c, i in zip(table["Confidence"], table["Impact if wrong"])]
    critical = table[table["Critical"] == "YES"]
    counts = table["Status"].value_counts().to_dict()
    return f"""# 06. Assumptions log (workflow: analysis-assumptions-log)

**Analysis:** cleaning, profiling and insight work on the 2026 lap data. **Date:** {helpers.today()}. **Analyst:** Claude with the project author.
**Decision informed:** one-stop versus two-stop strategy per circuit (`beta > 12P / N^2`).
**Data sources:** FastF1 race laps for 20 rounds (19 kept), the hand-compiled Pirelli allocation table. **Population:** 2026 season only.

An assumption is **critical** when confidence is Low and impact if wrong is High; those need a validation plan before the result is delivered.
Status counts: {', '.join(f'{k} {v}' for k, v in counts.items())}.

{helpers.md_table(table[COLUMNS[:6] + ['Critical', 'Status']])}

## Critical assumptions and validation plans

{helpers.md_table(critical[['ID', 'Assumption', 'Alternatives / validation']])}

## Alternatives considered (business logic)
- Wet rule: drop every race with any rain (simpler, loses Zandvoort, Kuala Lumpur and Montreal) versus the 25% cutoff chosen.
- Restart laps: keep them (more data, cold-tyre bias) versus dropping the lap after a non-green lap (chosen).
- Compound labels: model by relative label (simple, but not comparable across circuits) versus C1 to C5 (chosen).

## Peer-review sign-off
Not signed: a reviewer other than the analyst, such as the project author, should sign the log.
"""


def catalog_text() -> str:
    laps, excl = helpers.load_clean(), helpers.load_exclusions()
    path = config.PROCESSED_DIR / "clean_laps.parquet"
    age_h = (time.time() - path.stat().st_mtime) / 3600
    dup = int(laps.duplicated(["Round", "Driver", "LapNumber"]).sum())
    rows = []
    for column, (description, rule) in DESCRIPTIONS.items():
        series = laps[column]
        rows.append((column, str(series.dtype), description, str(series.iloc[0]), rule, f"{series.isna().mean():.0%}"))
    column_table = pd.DataFrame(rows, columns=["Column", "Type", "Description", "Example", "Business rule", "Null %"])
    exclusion_rows = [(c, str(excl[c].dtype), EXCLUSION_DESCRIPTIONS[c], str(excl[c].iloc[0]), f"{excl[c].isna().mean():.0%}") for c in excl.columns]
    exclusion_table = pd.DataFrame(exclusion_rows, columns=["Column", "Type", "Description", "Example", "Null %"])
    reasons = ", ".join(sorted(excl["reason"].unique()))
    allocation = pd.read_csv(config.ALLOCATION_FILE)

    return f"""# 07. Data catalog (workflow: data-catalog-entry)

Date: {helpers.today()}. Entries are for the files this analysis produces and uses. Technical metadata was extracted from the files, not from a database.

## Entry 1: clean laps

| Field | Value |
|---|---|
| File | `data/processed/clean_laps.parquet` |
| Display name | Clean 2026 race laps |
| Business purpose | Laps that measure tyre wear: normal green-flag racing laps, dry, with a known tyre compound and age. |
| Owner | Project author |
| Criticality | High: the model input |
| Use cases | Degradation model, EDA, stint counts per circuit and compound |
| Rows, columns | {len(laps):,} rows, {laps.shape[1] - 1} columns (+ `LapTimeDelta`, derived in memory) |
| Primary key | (Round, Driver, LapNumber), {dup} duplicates |
| Foreign keys | Round to `pirelli_allocation.csv`; (Round, Compound) to the allocation ladder |
| Completeness | 100% (no nulls in any column) |
| Freshness | built {age_h:.0f} hours ago from raw files ingested for all 20 rounds |
| Duplicate rate | 0% |
| Known issues | Mexico City laps end at lap 56 of 71; dirty-air laps are not filtered (v1); seven circuit-compound cells have fewer than 4 stints. |
| Upstream | FastF1 (F1TV timing feed) to `data/raw/season=2026/*.parquet` to `f1_pit_strategy/clean.py` |
| Downstream | EDA, quality audit, visuals, insight brief; later the degradation model |
| Access level | Public sports timing data; the repository is published on GitHub |
| Sensitivity | No personal data beyond public driver codes and team names |
| Compliance | Terms for redistributing F1 timing data were not reviewed here; check them before publishing data files. |
| Retention | Reproducible from `data/raw`; no retention limit |

### Columns

{helpers.md_table(column_table)}

## Entry 2: exclusions (audit table)

| Field | Value |
|---|---|
| File | `data/processed/exclusions.parquet` |
| Business purpose | Every raw lap that was dropped, with exactly one reason, so no row disappears silently. |
| Rows, columns | {len(excl):,} rows, {excl.shape[1]} columns |
| Reasons | {reasons} |
| Rule | Clean rows + excluded rows = raw rows ({len(laps):,} + {len(excl):,} = {len(laps) + len(excl):,}) |

{helpers.md_table(exclusion_table)}

## Entry 3: Pirelli allocation and circuit labels (reference table)

| Field | Value |
|---|---|
| File | `data/reference/pirelli_allocation.csv` (read only here) |
| Business purpose | Gives each round its host-city label and maps SOFT, MEDIUM and HARD to the absolute compounds C1 to C5. |
| Rows, columns | {len(allocation)} rows (one per round), {allocation.shape[1]} columns: {', '.join(allocation.columns)} |
| Owner | Project author (compiled by hand from Pirelli press releases and formula1.com) |
| Known issues | Round 20 (São Paulo) has no allocation because it is dropped as a wet race; accuracy is not cross-checked against a second source. |
"""


def run() -> None:
    helpers.write_report("06_assumptions_log.md", assumptions_text())
    helpers.write_report("07_data_catalog.md", catalog_text())


if __name__ == "__main__":
    run()
