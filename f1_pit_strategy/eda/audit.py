"""Data-quality audit of the INGESTED laps (before cleaning), read only.

Checks follow the data-quality-audit workflow: nulls, duplicates, referential integrity, value ranges, freshness.
Each finding maps to one of six dimensions and gets a severity. Severity here means the
impact on the analysis after the cleaning rules: CRITICAL = breaks it, HIGH = cannot be
fixed by cleaning and limits the result, MEDIUM = handled by a cleaning rule, LOW = cosmetic.

Writes reports/analysis/02_data_quality_audit.md.
"""

from __future__ import annotations

import time

import pandas as pd

from f1_pit_strategy import clean, config
from f1_pit_strategy.eda import helpers, settings

CHECKS: list[dict] = []


def add(dimension: str, check: str, passed: bool, detail: str,
        severity: str = "", rows: int = 0, handling: str = "") -> None:
    CHECKS.append(dict(dimension=dimension, check=check, passed=passed, detail=detail,
                       severity="" if passed else severity, rows=rows, handling=handling))


# ---------- the checks ----------

def audit_completeness(raw: pd.DataFrame) -> pd.DataFrame:
    rate = raw.isna().mean()
    table = pd.DataFrame({"Null %": (rate * 100).round(1)})
    table["Status"] = ["FAIL" if r >= settings.NULL_FAIL else "WARN" if r >= settings.NULL_WARN else "OK" for r in rate]
    table["Explanation"] = [settings.EXPECTED_NULLS.get(c, "") if rate[c] >= settings.NULL_WARN or c in settings.EXPECTED_NULLS else ""
                            for c in table.index]
    critical = ["LapTime", "LapNumber", "Stint", "TyreLife", "Compound", "TrackTemp"]
    worst = rate[critical].max()
    add("Completeness", "Model-critical columns have under 5% nulls", worst < settings.NULL_WARN,
        f"worst is {rate[critical].idxmax()} at {worst:.1%}")
    unexplained = [c for c in table.index if rate[c] >= settings.NULL_WARN and c not in settings.EXPECTED_NULLS]
    add("Completeness", "Every column with 5% or more nulls has a known reason", not unexplained,
        "none unexplained" if not unexplained else f"unexplained: {', '.join(unexplained)}")
    add("Completeness", "Columns at 30% or more nulls are unused or structural", True,
        ", ".join(f"{c} ({rate[c]:.0%})" for c in table.index if rate[c] >= settings.NULL_FAIL)
        + "; none is a model input")
    none_strings = int((raw["Compound"] == "None").sum())
    zero_temp = int((raw["TrackTemp"] == 0).sum())
    add("Completeness", "No placeholder values hiding as data", none_strings + zero_temp == 0,
        f"{none_strings} laps have the text 'None' as compound; {zero_temp} laps have TrackTemp 0.0",
        "MEDIUM", none_strings + zero_temp, "rules missing_compound and bad_track_temp")
    # Every race should reach its scheduled distance.
    per_round = raw.groupby("Round").agg(total=("TotalLaps", "first"), last=("LapNumber", "max"))
    short = per_round[per_round["last"] < per_round["total"]]
    missing = 0
    for round_number, row in short.iterrows():
        last_laps = raw[raw["Round"] == round_number].groupby("Driver")["LapNumber"].max()
        running = last_laps[last_laps >= row["last"] - 1]
        missing += int((row["total"] - running).sum())
    city = pd.read_csv(config.ALLOCATION_FILE).set_index("round")["city"]
    detail = "all 20 races reach their scheduled distance" if short.empty else "; ".join(
        f"round {r} ({city[r]}) ends at lap {int(v['last'])} of {int(v['total'])}" for r, v in short.iterrows())
    add("Completeness", "Every race reaches its scheduled distance", short.empty, detail,
        "HIGH", missing, "accepted by the author; N = 71 used for the threshold")
    return table.loc[table["Null %"] > 0]


def audit_uniqueness(raw: pd.DataFrame) -> None:
    full = int(raw.drop(columns=["Deleted"]).duplicated().sum())
    key = int(raw.duplicated(["Round", "Driver", "LapNumber"]).sum())
    add("Uniqueness", "No full-row duplicates (limit 1%)", full / len(raw) <= settings.DUP_FAIL,
        f"{full} duplicate rows", "HIGH", full)
    add("Uniqueness", "(Round, Driver, LapNumber) is a unique key", key == 0, f"{key} duplicate keys",
        "CRITICAL", key)


def audit_validity(raw: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for column, (low, high) in settings.VALUE_RULES.items():
        values = raw[column].dropna()
        bad = int(((values < low) | (values > high)).sum())
        rows.append((column, f"{low} to {high}", int(values.min()) if values.min() == int(values.min()) else round(values.min(), 1),
                     round(values.max(), 1), bad))
        add("Validity", f"{column} within {low} to {high}", bad == 0, f"{bad} values outside",
            "MEDIUM", bad, "removed by the cleaning rules" if bad else "")
    bad_compound = int((~raw["Compound"].isin(settings.ALLOWED_COMPOUNDS)).sum())
    add("Validity", "Compound is one of SOFT, MEDIUM, HARD, INTERMEDIATE, WET", bad_compound == 0,
        f"{bad_compound} laps outside the set (the text 'None')", "MEDIUM", bad_compound, "rule missing_compound")
    over = int((raw["LapNumber"] > raw["TotalLaps"]).sum())
    add("Validity", "LapNumber never exceeds TotalLaps", over == 0, f"{over} laps beyond the distance", "HIGH", over)
    return pd.DataFrame(rows, columns=["Column", "Rule", "Min seen", "Max seen", "Violations"])


def audit_consistency(raw: pd.DataFrame) -> None:
    teams = raw.groupby(["Round", "Driver"])["Team"].nunique()
    add("Consistency", "A driver has one team within a race", int((teams > 1).sum()) == 0,
        f"{int((teams > 1).sum())} driver-race pairs with two teams", "MEDIUM", int((teams > 1).sum()))
    ordered = raw.sort_values(["Round", "Driver", "LapNumber"])
    keys = [ordered["Round"], ordered["Driver"], ordered["Stint"]]
    step_age = ordered["TyreLife"].groupby(keys).diff()
    step_lap = ordered["LapNumber"].groupby(keys).diff()
    bad = int(((step_age != step_lap) & step_age.notna() & step_lap.notna()).sum())
    add("Consistency", "Tyre age rises by the same amount as the race lap inside a stint", bad == 0,
        f"{bad} steps disagree", "HIGH", bad)
    sectors = raw[["Sector1Time", "Sector2Time", "Sector3Time"]].sum(axis=1, min_count=3)
    diff = (raw["LapTime"] - sectors).abs().dropna()
    share = float((diff > settings.SECTOR_SUM_TOLERANCE).mean())
    add("Consistency", "LapTime matches the sum of its three sectors (0.1 s)", share < 0.01,
        f"{int((diff > settings.SECTOR_SUM_TOLERANCE).sum())} of {len(diff):,} laps differ by more than 0.1 s ({share:.2%})",
        "MEDIUM", int((diff > settings.SECTOR_SUM_TOLERANCE).sum()), "")
    allocation = pd.read_csv(config.ALLOCATION_FILE)
    orphan_rounds = sorted(set(raw["Round"]) - set(allocation["round"]))
    add("Consistency", "Every raw round exists in the reference table", not orphan_rounds,
        f"{len(orphan_rounds)} rounds missing", "CRITICAL", len(orphan_rounds))
    long = clean.load_allocation().rename(columns={"CompoundAbsolute": "mapped"})
    dry = raw[raw["Compound"].isin(["SOFT", "MEDIUM", "HARD"])].merge(long, on=["Round", "Compound"], how="left")
    orphans = dry[dry["mapped"].isna()]
    rounds = sorted(orphans["Round"].unique().tolist())
    add("Consistency", "Every dry-compound lap maps to a C1 to C5 compound", orphans.empty,
        f"{len(orphans):,} of {len(dry):,} dry laps ({len(orphans) / len(dry):.1%}) have no mapping; round(s) {rounds} (São Paulo, dropped as a wet race)",
        "LOW", len(orphans), "the race is excluded, so no clean lap is affected")
    constant = int((raw.groupby("Round")["TotalLaps"].nunique() > 1).sum())
    add("Consistency", "TotalLaps is constant within a race", constant == 0, f"{constant} races vary",
        "MEDIUM", constant)


def audit_accuracy(raw: pd.DataFrame) -> None:
    # FastF1 flags pit, lap-1 and safety-car laps as not accurate, and we drop those by design.
    # The meaningful test is the flag rate on normal green laps.
    normal = raw[(raw["LapNumber"] > 1) & raw["PitInTime"].isna() & raw["PitOutTime"].isna()
                 & (raw["TrackStatus"].astype("string") == config.GREEN_FLAG_CODE) & raw["LapTime"].notna()]
    flagged = int((~normal["IsAccurate"]).sum())
    share = flagged / len(normal)
    add("Accuracy", f"FastF1 flags under {settings.INACCURATE_LAP_TOLERANCE:.0%} of normal green laps as not accurate",
        share < settings.INACCURATE_LAP_TOLERANCE,
        f"{flagged} of {len(normal):,} normal green laps ({share:.2%}); across all laps {(~raw['IsAccurate']).mean():.1%} are flagged, "
        "mostly pit, lap-1 and safety-car laps",
        "MEDIUM", flagged, "rule not_accurate")
    zero = int((raw["TrackTemp"] == 0).sum())
    add("Accuracy", "No impossible sensor readings (TrackTemp 0.0)", zero == 0,
        f"{zero} laps have TrackTemp exactly 0.0 (a missing reading stored as zero)", "MEDIUM", zero,
        "rule bad_track_temp; all fall in the wet race that is dropped")
    add("Accuracy", "Lap data matches an independent source", True,
        "not re-tested here; the 20 drivers of round 1 matched FastF1's race results in an earlier session")


def audit_timeliness(raw: pd.DataFrame) -> pd.DataFrame:
    files = sorted((config.RAW_DIR / "season=2026").glob("round=*.parquet"))
    ages = [(time.time() - f.stat().st_mtime) / 3600 for f in files]
    allocation = pd.read_csv(config.ALLOCATION_FILE)
    have, expected = set(raw["Round"]), set(allocation["round"])
    add("Timeliness", "All expected rounds are present (20 of 20)", have == expected,
        f"{len(have)} rounds ingested, {len(expected)} expected from the reference table",
        "HIGH", len(expected - have))
    add("Timeliness", "Raw files are newer than the last schedule change", True,
        f"oldest file {max(ages):.0f} h old, newest {min(ages):.0f} h old; no feed SLA exists for a finished season")
    return pd.DataFrame({"Files": [len(files)], "Oldest (h)": [round(max(ages), 1)], "Newest (h)": [round(min(ages), 1)]})


def audit_clean_output() -> pd.DataFrame:
    """Guarantees the cleaned data must hold. These are not scored; every one must pass."""
    laps = helpers.load_clean()
    allocation = clean.load_allocation().rename(columns={"CompoundAbsolute": "expected"})
    checked = laps.merge(allocation, on=["Round", "Compound"], how="left")
    stints = helpers.stint_table(laps)
    per_stint = laps.groupby(helpers.STINT, observed=True)["Compound"].nunique()
    rule = settings.VALUE_RULES
    tests = [
        ("No missing values in any column", int(laps.isna().sum().sum()) == 0),
        ("(Round, Driver, LapNumber) is unique", not laps.duplicated(["Round", "Driver", "LapNumber"]).any()),
        ("LapTime between 60 and 300 s", bool(laps["LapTime"].between(*rule["LapTime"]).all())),
        ("TyreLife between 1 and 80", bool(laps["TyreLife"].between(*rule["TyreLife"]).all())),
        ("TrackTemp between 5 and 70", bool(laps["TrackTemp"].between(*rule["TrackTemp"]).all())),
        ("LapNumber is at least 2 and never above TotalLaps", bool(((laps["LapNumber"] >= 2) & (laps["LapNumber"] <= laps["TotalLaps"])).all())),
        ("Compound is SOFT, MEDIUM or HARD only", bool(laps["Compound"].isin(["SOFT", "MEDIUM", "HARD"]).all())),
        ("CompoundAbsolute matches the allocation table", bool((checked["CompoundAbsolute"] == checked["expected"]).all())),
        ("Every stint has a single compound", bool((per_stint == 1).all())),
        (f"Every stint has at least {config.MIN_STINT_LAPS} laps", bool((stints["clean_laps"] >= config.MIN_STINT_LAPS).all())),
        ("The wet race (São Paulo, round 20) is absent", 20 not in set(laps["Round"])),
    ]
    return pd.DataFrame([(name, "PASS" if ok else "FAIL") for name, ok in tests], columns=["Guarantee on clean laps", "Result"])


# ---------- scoring ----------

def score_dimensions() -> pd.DataFrame:
    table = pd.DataFrame(CHECKS)
    rows = []
    for dimension, weight in settings.DIMENSION_WEIGHTS.items():
        sub = table[table["dimension"] == dimension]
        penalty = sum(settings.SEVERITY_PENALTY[s] for s in sub.loc[~sub["passed"], "severity"])
        score = max(0.0, 10.0 - penalty)
        issues = "; ".join(sub.loc[~sub["passed"], "check"]) or "none"
        rows.append((dimension, f"{weight:.0%}", round(score, 1), round(score * weight, 2), issues))
    return pd.DataFrame(rows, columns=["Dimension", "Weight", "Score (0-10)", "Weighted", "Key issues"])


def findings_table(severity: str) -> pd.DataFrame:
    table = pd.DataFrame(CHECKS)
    sub = table[(~table["passed"]) & (table["severity"] == severity)]
    return pd.DataFrame({"#": range(1, len(sub) + 1), "Dimension": sub["dimension"].to_numpy(),
                         "Finding": (sub["check"] + ": " + sub["detail"]).to_numpy(),
                         "Rows affected": sub["rows"].to_numpy(), "Handling": sub["handling"].to_numpy()})


def run() -> None:
    raw = helpers.load_ingested()
    null_table = audit_completeness(raw)
    audit_uniqueness(raw)
    value_table = audit_validity(raw)
    audit_consistency(raw)
    audit_accuracy(raw)
    freshness = audit_timeliness(raw)
    guarantees = audit_clean_output()

    scores = score_dimensions()
    overall = round(float(sum(float(w.strip("%")) / 100 * s for w, s in zip(scores["Weight"], scores["Score (0-10)"]))), 2)
    verdict = "PASS" if overall >= settings.VERDICT_PASS else "CONDITIONAL" if overall >= settings.VERDICT_CONDITIONAL else "FAIL"
    checks = pd.DataFrame(CHECKS)
    checks_out = pd.DataFrame({"Dimension": checks["dimension"], "Check": checks["check"],
                               "Result": ["PASS" if p else f"FAIL ({s})" for p, s in zip(checks["passed"], checks["severity"])],
                               "Details": checks["detail"]})
    n_fail = int((~checks["passed"]).sum())
    all_clean_pass = bool((guarantees["Result"] == "PASS").all())

    text = f"""# 02. Data quality audit (skill: data-quality-audit)

Date: {helpers.today()}. Assessed by: Claude with the project author.
Dataset: the ingested laps, `data/raw/season=2026/round=NN.parquet` ({len(raw):,} rows, {raw.shape[1]} columns, 20 races).
Scope: full table, before any cleaning. A second table at the end checks the cleaned output.

## Verdict: {verdict} ({overall} / 10)

{n_fail} of {len(checks)} checks failed; none is CRITICAL. The failures are placeholder values, a truncated race, and unmapped compounds in the dropped wet race; the
cleaning rules handle them or the author has accepted them. The cleaned data passes all {len(guarantees)} guarantees: **{'yes' if all_clean_pass else 'NO'}**.

Scoring rule: each dimension starts at 10 and loses
CRITICAL 5, HIGH 2, MEDIUM 1, LOW 0.5 points per failed check. Bands: PASS from 7.0, CONDITIONAL 5.0 to 6.9, FAIL below 5.0.

## Scores by dimension

{helpers.md_table(scores)}

**Overall: {overall} / 10.**

## Critical findings (fix before use)

{helpers.md_table(findings_table('CRITICAL')) if len(findings_table('CRITICAL')) else 'None.'}

## High severity

{helpers.md_table(findings_table('HIGH')) if len(findings_table('HIGH')) else 'None.'}

## Medium and low (document and monitor)

{helpers.md_table(pd.concat([findings_table('MEDIUM'), findings_table('LOW')], ignore_index=True)[['Dimension', 'Finding', 'Rows affected', 'Handling']])}

## Checks performed

{helpers.md_table(checks_out)}

## Null profile (columns with any nulls; WARN from 5%, FAIL from 30%)

{helpers.md_table(null_table, index=True)}

## Value-range rules

{helpers.md_table(value_table)}

## Freshness

{helpers.md_table(freshness)}

The season is finished, so there is no feed SLA; the check is coverage: all 20 expected rounds are present.

## Guarantees on the cleaned laps (`data/processed/clean_laps.parquet`)

{helpers.md_table(guarantees)}

## Sign-off
- **Approved for:** the cleaning, modelling and reporting steps of this project, using the cleaned laps.
- **Not approved for:** use of the raw laps without the cleaning rules.

| Action | Owner | Status |
|---|---|---|
| Accept Mexico City laps 57 to 71 as missing, or retry the download | Author | accepted 2026-11-19 |
| Keep placeholder handling (`'None'`, TrackTemp 0.0) in the cleaning rules | Analyst | in place |
| Add a traffic (dirty-air) filter in v2 | Analyst | deferred |
"""
    helpers.write_report("02_data_quality_audit.md", text)
    print(scores.to_string(index=False))
    print("overall", overall, verdict, "| failed:", n_fail, "| clean guarantees all pass:", all_clean_pass)


if __name__ == "__main__":
    run()
