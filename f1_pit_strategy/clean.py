"""Clean the raw laps and write an audit trail.

Outputs (data/processed/):
    clean_laps.parquet   laps that survive every rule, with CompoundAbsolute (C1-C5) added
    exclusions.parquet   every dropped lap, with exactly one `reason`

Run from the repo root:  python -m f1_pit_strategy.clean

v1 does not apply the traffic (dirty-air) filter; see docs/scope.md section 13.

Design: each rule is a small function returning a boolean mask (True = drop this
lap). apply_rules() runs them in a fixed order and gives every lap the FIRST
reason that fires. One reason per lap makes the funnel add up exactly; the
alternative (one boolean column per rule) keeps overlaps but cannot be summed.
"""

from __future__ import annotations

import pandas as pd

from f1_pit_strategy import config

KEYS = ["Round", "Driver"]
STINT = ["Round", "Driver", "Stint"]


# ---------- loading and types ----------

def load_raw(raw_dir=config.RAW_DIR) -> pd.DataFrame:
    paths = sorted(raw_dir.glob("**/*.parquet"))
    return pd.concat((pd.read_parquet(p) for p in paths), ignore_index=True)


def fix_dtypes(laps: pd.DataFrame) -> pd.DataFrame:
    """Right-size the types. Nullable Int types are used where NaN is possible."""
    out = laps.copy()
    out["Compound"] = out["Compound"].replace("None", pd.NA)  # string 'None' -> real missing
    out = out.drop(columns=["Deleted"])                        # 100% null
    return out.astype({
        "Season": "int16", "Round": "int8", "LapNumber": "int16", "Stint": "int8",
        "TotalLaps": "int16", "Position": "Int8", "TyreLife": "Int16",
        "TrackStatus": "string", "Compound": "string",
    })


# ---------- helper building blocks ----------

def is_wet_lap(laps: pd.DataFrame) -> pd.Series:
    """A lap is wet if the rain flag is on or the car is on wet-weather tyres."""
    return laps["Rainfall"] | laps["Compound"].isin(config.WET_COMPOUNDS)


def wet_race_rounds(laps: pd.DataFrame) -> list[int]:
    """Rounds where more than WET_RACE_LAP_SHARE of laps are wet."""
    share = is_wet_lap(laps).groupby(laps["Round"]).mean()
    return share[share > config.WET_RACE_LAP_SHARE].index.tolist()


def near_wet_lap(laps: pd.DataFrame) -> pd.Series:
    """True for wet laps and the next POST_WET_BUFFER_LAPS race laps (whole field).

    Wetness is decided per (Round, LapNumber): if any car is wet on that race
    lap the track is wet for everyone. rolling(window).max() then carries the
    flag forward in time, which is the 'track still damp' buffer.
    """
    per_lap = is_wet_lap(laps).groupby([laps["Round"], laps["LapNumber"]]).max().astype(int)
    window = config.POST_WET_BUFFER_LAPS + 1
    spread = per_lap.groupby(level="Round").transform(lambda s: s.rolling(window, min_periods=1).max())
    keyed = pd.MultiIndex.from_frame(laps[["Round", "LapNumber"]])
    return pd.Series(spread.reindex(keyed).to_numpy() == 1, index=laps.index)


def after_non_green(laps: pd.DataFrame) -> pd.Series:
    """True for the RESTART_BUFFER_LAPS laps that follow a non-green lap, per driver."""
    ordered = laps.sort_values(KEYS + ["LapNumber"])
    not_green = (ordered["TrackStatus"] != config.GREEN_FLAG_CODE).astype(int)
    grouped = not_green.groupby([ordered["Round"], ordered["Driver"]])
    flag = pd.Series(False, index=ordered.index)
    for shift in range(1, config.RESTART_BUFFER_LAPS + 1):
        flag |= grouped.shift(shift, fill_value=0).eq(1)
    return flag.reindex(laps.index)


# ---------- reference table: city and absolute compound (C1-C5) ----------

def add_city(laps: pd.DataFrame, path=config.ALLOCATION_FILE) -> pd.DataFrame:
    """Label each lap with its host city (one uniform rule for every circuit).

    FastF1's EventName mixes countries ('Dutch'), cities ('Barcelona') and
    nicknames, so the label comes from the 'city' column of the reference table.
    validate='many_to_one' fails loudly if a round appeared twice in that table.
    """
    cities = pd.read_csv(path, usecols=["round", "city"]).rename(columns={"round": "Round", "city": "City"})
    out = laps.merge(cities, on="Round", how="left", validate="many_to_one")
    assert out["City"].notna().all(), "a round has no city in the reference table"
    return out



def load_allocation(path=config.ALLOCATION_FILE) -> pd.DataFrame:
    """Reshape the allocation table from one row per round to one row per (round, label).

    The CSV is 'wide' (columns soft, medium, hard). A merge needs the label as a
    value to match on, so melt() turns the three columns into rows:
        round=1, soft=C5, medium=C4, hard=C3  ->  (1, SOFT, C5), (1, MEDIUM, C4), (1, HARD, C3)
    Rounds with no allocation (a dropped race) become empty rows and are removed.
    """
    wide = pd.read_csv(path, usecols=["round", "soft", "medium", "hard"])
    long = wide.melt(id_vars="round", var_name="Compound", value_name="CompoundAbsolute")
    long["Compound"] = long["Compound"].str.upper().astype("string")
    return long.dropna(subset=["CompoundAbsolute"]).rename(columns={"round": "Round"})


def add_absolute_compound(laps: pd.DataFrame, allocation: pd.DataFrame) -> pd.DataFrame:
    """Left-join CompoundAbsolute onto laps by (Round, Compound), then check the join.

    how='left' keeps every lap even without a match, so a gap shows up as a missing
    value we can detect (an inner join would drop those laps silently).
    validate='many_to_one' makes pandas raise if the allocation had duplicate keys,
    which would duplicate laps.
    """
    merged = laps.merge(allocation, on=["Round", "Compound"], how="left", validate="many_to_one")
    assert len(merged) == len(laps), "join changed the number of laps"
    missing = merged.loc[merged["CompoundAbsolute"].isna(), "Round"].unique()
    if len(missing):
        raise ValueError(f"no C1-C5 allocation for rounds {sorted(missing.tolist())}")
    return merged


# ---------- the ordered rules: name -> mask(laps, reason_so_far) ----------

def build_rules(laps: pd.DataFrame) -> dict[str, pd.Series]:
    """Row-level rules. Order matters: it decides which reason a lap is credited with."""
    return {
        "wet_race":          laps["Round"].isin(wet_race_rounds(laps)),
        "missing_laptime":   laps["LapTime"].isna(),
        "lap_1":             laps["LapNumber"] == 1,
        "in_or_out_lap":     laps["PitInTime"].notna() | laps["PitOutTime"].notna(),
        "not_green":         laps["TrackStatus"] != config.GREEN_FLAG_CODE,
        "after_non_green":   after_non_green(laps),
        "wet_or_post_wet":   near_wet_lap(laps),
        "not_accurate":      ~laps["IsAccurate"],
        "missing_compound":  laps["Compound"].isna(),
        "missing_tyrelife":  laps["TyreLife"].isna(),
        "bad_track_temp":    laps["TrackTemp"] < config.MIN_VALID_TRACK_TEMP,
    }


def first_reason(laps: pd.DataFrame, rules: dict[str, pd.Series]) -> pd.Series:
    """Give each lap the first rule that fires; laps that pass everything stay <NA>."""
    reason = pd.Series(pd.NA, index=laps.index, dtype="string")
    for name, mask in rules.items():
        reason = reason.mask(reason.isna() & mask.fillna(False), name)
    return reason


def slow_outliers(laps: pd.DataFrame, reason: pd.Series) -> pd.Series:
    """Laps slower than OUTLIER_RATIO x their own stint's median.

    The median is taken over laps that already survived the other rules, so
    safety-car laps cannot inflate it. Median (not mean) because one 200 s lap
    would drag a mean up and hide itself.
    """
    alive = laps.loc[reason.isna()]
    median = alive.groupby(STINT)["LapTime"].transform("median")
    return (alive["LapTime"] > config.OUTLIER_RATIO * median).reindex(laps.index, fill_value=False)


def short_stints(laps: pd.DataFrame, reason: pd.Series) -> pd.Series:
    """Stints with fewer than MIN_STINT_LAPS laps LEFT after lap filtering."""
    alive = laps.loc[reason.isna()]
    clean_laps = alive.groupby(STINT)["LapTime"].transform("size")
    return (clean_laps < config.MIN_STINT_LAPS).reindex(laps.index, fill_value=False)


def apply_rules(laps: pd.DataFrame) -> pd.Series:
    """Return the per-lap reason, in the order: row rules, outliers, short stints."""
    reason = first_reason(laps, build_rules(laps))
    reason = reason.mask(reason.isna() & slow_outliers(laps, reason), "slow_outlier")
    reason = reason.mask(reason.isna() & short_stints(laps, reason), "short_stint")
    return reason


# ---------- reporting and output ----------

ORDER = ["wet_race", "missing_laptime", "lap_1", "in_or_out_lap", "not_green", "after_non_green",
         "wet_or_post_wet", "not_accurate", "missing_compound", "missing_tyrelife",
         "bad_track_temp", "slow_outlier", "short_stint"]


def print_funnel(laps: pd.DataFrame, reason: pd.Series) -> None:
    counts = reason.value_counts().reindex(ORDER, fill_value=0)
    remaining = len(laps)
    print(f"{'start':18s} {remaining:7,}")
    for name, n in counts.items():
        remaining -= n
        print(f"- {name:16s} {n:7,}   left {remaining:7,}")
    print(f"clean laps: {remaining:,} ({remaining / len(laps):.1%})")


def main() -> None:
    laps = add_city(fix_dtypes(load_raw()))
    reason = apply_rules(laps)
    print_funnel(laps, reason)

    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    kept = add_absolute_compound(laps.loc[reason.isna()], load_allocation())[config.CLEAN_COLUMNS]
    dropped = laps.loc[reason.notna()].assign(reason=reason.loc[reason.notna()])[config.EXCLUSION_COLUMNS]
    assert len(kept) + len(dropped) == len(laps)  # every raw lap is in exactly one table
    kept.reset_index(drop=True).to_parquet(config.PROCESSED_DIR / "clean_laps.parquet", index=False)
    dropped.reset_index(drop=True).to_parquet(config.PROCESSED_DIR / "exclusions.parquet", index=False)
    print(f"\nwrote {len(kept):,} clean and {len(dropped):,} excluded laps to {config.PROCESSED_DIR}")


if __name__ == "__main__":
    main()
