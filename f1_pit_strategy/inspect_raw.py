"""Validate ingested raw parquet and print a report.

Run this straight after ingest. It answers the only question that matters at
this stage: is there enough clean, green-flag, dry running to estimate a
degradation slope per compound per circuit?

    python -m f1_pit_strategy.inspect_raw
    python -m f1_pit_strategy.inspect_raw --round 1
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from f1_pit_strategy import config

# Columns the degradation model cannot run without. Anything here that is
# largely null is a blocker, not a nuisance.
CRITICAL_COLUMNS = [
    "LapTime", "LapNumber", "TyreLife", "Compound", "Stint",
    "TrackStatus", "IsAccurate", "TrackTemp",
]


def load_raw(raw_dir: Path, round_number: int | None = None) -> pd.DataFrame:
    """Read the partitioned raw parquet tree into one DataFrame."""
    pattern = "**/*.parquet" if round_number is None else f"**/round={round_number:02d}.parquet"
    paths = sorted(raw_dir.glob(pattern))
    if not paths:
        raise FileNotFoundError(f"no parquet files under {raw_dir}. Run the ingest first.")
    print(f"reading {len(paths)} file(s) from {raw_dir}")
    return pd.concat((pd.read_parquet(path) for path in paths), ignore_index=True)


def report_columns(laps: pd.DataFrame) -> None:
    print("\n=== columns and null rates ===")
    missing = [column for column in CRITICAL_COLUMNS if column not in laps.columns]
    if missing:
        print(f"!! MISSING CRITICAL COLUMNS: {', '.join(missing)}")
    for column in CRITICAL_COLUMNS:
        if column in laps.columns:
            null_rate = laps[column].isna().mean()
            flag = "  <-- check" if null_rate > 0.2 else ""
            print(f"  {column:14s} null {null_rate:6.1%}{flag}")


def report_coverage(laps: pd.DataFrame) -> None:
    print("\n=== coverage ===")
    print(f"  rounds:  {laps['Round'].nunique()}")
    print(f"  laps:    {len(laps):,}")
    print(f"  drivers: {laps['Driver'].nunique()}")
    per_round = laps.groupby("Round").size()
    print(f"  laps per round: min {per_round.min()}, median {int(per_round.median())}, max {per_round.max()}")


def report_tyres(laps: pd.DataFrame) -> None:
    print("\n=== compounds ===")
    print(laps["Compound"].value_counts(dropna=False).to_string())

    print("\n=== tyre age by compound (sanity check) ===")
    age = laps.groupby("Compound")["TyreLife"].agg(["min", "median", "max", "count"])
    print(age.to_string())

    print("\n=== stints per driver per round ===")
    stints = laps.groupby(["Round", "Driver"])["Stint"].nunique()
    print(f"  median {stints.median():.1f}, min {stints.min()}, max {stints.max()}")


def report_track_status(laps: pd.DataFrame) -> None:
    """TrackStatus is a concatenation of codes, so '1' alone means fully green."""
    print("\n=== track status (top 8) ===")
    print(laps["TrackStatus"].astype("string").value_counts(dropna=False).head(8).to_string())


def report_sample_funnel(laps: pd.DataFrame) -> None:
    """The feasibility check: how much usable data survives a first-pass filter.

    These are the headline filters from the scope doc, applied cumulatively. The
    traffic-gap filter is not applied here because it needs a derived gap column
    that the cleaning step builds; expect a further reduction from it.
    """
    print("\n=== sample funnel (first-pass filters) ===")
    stages = {
        "all laps": laps,
    }
    step = laps.loc[laps["LapTime"].notna()]
    stages["has a lap time"] = step
    step = step.loc[step["LapNumber"] > 1]
    stages["not lap 1"] = step
    if "PitInTime" in step.columns and "PitOutTime" in step.columns:
        step = step.loc[step["PitInTime"].isna() & step["PitOutTime"].isna()]
        stages["not an in/out lap"] = step
    step = step.loc[step["TrackStatus"].astype("string") == config.GREEN_FLAG_CODE]
    stages["fully green flag"] = step
    if "IsAccurate" in step.columns:
        step = step.loc[step["IsAccurate"].fillna(False).astype(bool)]
        stages["FastF1 IsAccurate"] = step

    total = len(laps)
    for label, frame in stages.items():
        print(f"  {label:22s} {len(frame):7,}  ({len(frame) / total:5.1%} of all)")

    print("\n=== usable stints after first-pass filters ===")
    counts = step.groupby(["Round", "Driver", "Stint"]).size()
    usable = counts.loc[counts >= config.MIN_STINT_LAPS]
    print(f"  stints with >= {config.MIN_STINT_LAPS} clean laps: {len(usable)}")
    print(f"  median clean laps per usable stint: {usable.median():.0f}")
    # A boolean mask rather than .query(): query's @-reference to a module
    # attribute is not reliable across pandas evaluation engines, and the mask
    # is easier to read anyway.
    stint_summary = step.groupby(["Round", "Driver", "Stint"]).agg(
        clean_laps=("LapTime", "size"),
        compound=("Compound", "first"),
    )
    usable_stints = stint_summary.loc[stint_summary["clean_laps"] >= config.MIN_STINT_LAPS]
    print("\n  usable stints by compound:")
    print(usable_stints.groupby("compound").size().to_string())


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate ingested raw parquet.")
    parser.add_argument("--round", type=int, default=None)
    args = parser.parse_args()

    laps = load_raw(config.RAW_DIR, args.round)
    report_coverage(laps)
    report_columns(laps)
    report_tyres(laps)
    report_track_status(laps)
    report_sample_funnel(laps)
    print("\ndone. Paste this whole report back for review.")


if __name__ == "__main__":
    main()
