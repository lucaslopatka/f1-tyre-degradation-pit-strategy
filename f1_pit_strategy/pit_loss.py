"""Step 6: pit-lane time loss P per circuit.

    python -m f1_pit_strategy.pit_loss

For one stop, P = (in-lap time + out-lap time) - 2 x reference lap. In words: the
two laps around a stop take longer than two normal laps, and the difference is
what the stop cost. The reference lap is the same driver's median clean lap within
PIT_REF_WINDOW_LAPS race laps of the stop, so fuel burn and track evolution are
roughly balanced (laps before the stop are older-tyre, laps after are fresh-tyre).

P for a circuit is the MEDIAN over its usable stops: a slow stop (a stuck wheel, a
penalty) is a handful of laps out of dozens and would drag a mean upward.

Source of the definition: there is no official one; it is a community convention (see the
README section 'Pit-lane loss' for the references) and was set in docs/scope.md section 6.

Only green-flag, dry stops count: under a safety car or VSC the field is slow, so a
stop costs much less and would make P look too small.

Writes data/processed/pit_loss.csv (one row per circuit, with the threshold 12P/N^2).
"""

from __future__ import annotations

import pandas as pd

from f1_pit_strategy import clean, config


def stop_pairs(raw: pd.DataFrame) -> pd.DataFrame:
    """One row per stop: the in-lap (PitInTime set) joined to the next lap, the out-lap.

    merge() on (Round, Driver, out-lap number) pairs each in-lap with the lap that
    follows it. An inner join drops in-laps with no out-lap (a retirement in the pits).
    """
    cols = ["Round", "Driver", "LapNumber", "LapTime", "TrackStatus", "near_wet"]
    ins = raw.loc[raw["PitInTime"].notna(), cols].rename(columns={"LapNumber": "InLap", "LapTime": "InTime", "TrackStatus": "InStatus", "near_wet": "InWet"})
    outs = raw.loc[raw["PitOutTime"].notna(), cols].rename(columns={"LapNumber": "OutLap", "LapTime": "OutTime", "TrackStatus": "OutStatus", "near_wet": "OutWet"})
    ins["OutLap"] = ins["InLap"] + 1
    return ins.merge(outs, on=["Round", "Driver", "OutLap"], how="inner", validate="one_to_one")


def usable_stops(stops: pd.DataFrame, wet_rounds: list[int]) -> pd.DataFrame:
    """Keep green, dry stops with both lap times, not on lap 1, in a race we keep."""
    green = config.GREEN_FLAG_CODE
    keep = (
        stops["InTime"].notna() & stops["OutTime"].notna()
        & (stops["InStatus"] == green) & (stops["OutStatus"] == green)
        & ~stops["InWet"] & ~stops["OutWet"]
        & (stops["InLap"] > 1)
        & ~stops["Round"].isin(wet_rounds)
    )
    return stops.loc[keep].reset_index(drop=True)


def add_reference_lap(stops: pd.DataFrame, clean_laps: pd.DataFrame) -> pd.DataFrame:
    """Reference lap = median clean lap of the same driver near the stop.

    Merge every stop with all clean laps of that driver in that race, then keep the
    laps within the window. A stop with too few reference laps is dropped.
    """
    stops = stops.rename_axis("StopId").reset_index()
    near = stops[["StopId", "Round", "Driver", "InLap"]].merge(
        clean_laps[["Round", "Driver", "LapNumber", "LapTime"]], on=["Round", "Driver"])
    near = near.loc[(near["LapNumber"] - near["InLap"]).abs() <= config.PIT_REF_WINDOW_LAPS]
    ref = near.groupby("StopId")["LapTime"].agg(RefLap="median", RefLaps="size")
    out = stops.merge(ref, on="StopId")
    return out.loc[out["RefLaps"] >= config.PIT_REF_MIN_LAPS].copy()


def circuit_summary(stops: pd.DataFrame, totals: pd.DataFrame) -> pd.DataFrame:
    """Median P per circuit, spread, stop count, and the threshold 12 P / N^2."""
    stops = stops.assign(P=stops["InTime"] + stops["OutTime"] - 2 * stops["RefLap"])
    table = stops.groupby("Round")["P"].agg(
        stops="size", P=("median"), p25=lambda s: s.quantile(0.25), p75=lambda s: s.quantile(0.75))
    table = totals.join(table, how="left")
    table["thin"] = table["stops"].fillna(0) < config.MIN_STOPS_FOR_P
    table["threshold_beta"] = 12 * table["P"] / table["N"] ** 2
    return table.reset_index()


def main() -> None:
    raw = clean.add_city(clean.fix_dtypes(clean.load_raw()))
    raw["near_wet"] = clean.near_wet_lap(raw)
    clean_laps = pd.read_parquet(config.PROCESSED_DIR / "clean_laps.parquet")

    stops = stop_pairs(raw)
    usable = add_reference_lap(usable_stops(stops, clean.wet_race_rounds(raw)), clean_laps)
    print(f"stops: {len(stops)} found, {len(usable)} usable (green, dry, with a reference lap)")

    totals = clean_laps.groupby("Round").agg(City=("City", "first"), N=("TotalLaps", "first"))
    table = circuit_summary(usable, totals)
    print(table.round(3).to_string(index=False))

    out = config.PROCESSED_DIR / "pit_loss.csv"
    table.to_csv(out, index=False)
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
