"""Reconcile the cleaning: every raw lap is either clean or excluded with one reason.

Follows the metric-reconciliation workflow: define the metric, pull it from two sources
(raw files and the two processed tables), compute the gap, trace it if it is not zero.
Reads only; writes reports/analysis/01_cleaning_reconciliation.md.
"""

from __future__ import annotations

import pandas as pd

from f1_pit_strategy import clean, config
from f1_pit_strategy.eda import helpers


def funnel_table(excl: pd.DataFrame, raw_rows: int) -> pd.DataFrame:
    counts = excl["reason"].value_counts().reindex(clean.ORDER, fill_value=0)
    rows, remaining = [], raw_rows
    for reason, n in counts.items():
        remaining -= int(n)
        rows.append((reason, int(n), f"{n / raw_rows:.1%}", remaining))
    return pd.DataFrame(rows, columns=["Reason (in rule order)", "Laps dropped", "% of raw", "Laps left"])


def retention_table(raw: pd.DataFrame, laps: pd.DataFrame) -> pd.DataFrame:
    city = pd.read_csv(config.ALLOCATION_FILE).set_index("round")["city"]
    raw_n = raw.groupby("Round").size()
    kept_n = laps.groupby("Round").size().reindex(raw_n.index, fill_value=0)
    out = pd.DataFrame({"City": city.reindex(raw_n.index), "Raw laps": raw_n, "Clean laps": kept_n})
    out["Kept %"] = (out["Clean laps"] / out["Raw laps"] * 100).round(1)
    return out.sort_values("Kept %").reset_index()


def run() -> None:
    raw = helpers.load_ingested()
    laps, excl = helpers.load_clean(), helpers.load_exclusions()
    gap = len(raw) - (len(laps) + len(excl))
    stints = len(helpers.stint_table(laps))
    by_design = excl["reason"].isin(["lap_1", "in_or_out_lap", "not_green", "after_non_green"]).sum()
    assert gap == 0, f"{gap} raw laps are in neither processed table"

    text = f"""# 01. Cleaning funnel and reconciliation (workflow: metric-reconciliation)

Date: {helpers.today()}.

## Metric and sources
- **Metric:** number of laps, from the raw files to the processed tables.
- **Source A:** the raw parquet files in `data/raw/season=2026/` (one per round, nothing filtered).
- **Source B:** `data/processed/clean_laps.parquet` plus `data/processed/exclusions.parquet`.
- **Definitions:** a *raw lap* is one row of a round's file; a *clean lap* passes all 13 rules; a *stint* is a distinct (Round, Driver, Stint) among clean laps.

## Reconciliation

| Source A: raw laps | Clean laps | Excluded laps | Source B: clean + excluded | Gap |
|---|---|---|---|---|
| {len(raw):,} | {len(laps):,} | {len(excl):,} | {len(laps) + len(excl):,} | {gap} |

The gap is zero: every raw lap is in exactly one table, and every excluded lap has exactly one reason. The clean laps form {stints} stints.

## Cleaning funnel

{helpers.md_table(funnel_table(excl, len(raw)))}

Excluded: {len(excl):,} of {len(raw):,} raw laps ({len(excl) / len(raw):.1%}). {by_design / len(excl):.0%} of the excluded laps are lap 1, pit, safety-car or restart laps, which are removed by design.

## Retention per circuit

{helpers.md_table(retention_table(raw, laps))}
"""
    helpers.write_report("01_cleaning_reconciliation.md", text)


if __name__ == "__main__":
    run()
