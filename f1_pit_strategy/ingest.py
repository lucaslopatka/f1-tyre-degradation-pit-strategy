"""Ingest F1 race sessions from FastF1 into one parquet file per round.

This is the raw layer: nothing is filtered out here. Every lap the API returns
is written, including safety-car laps, in-laps and out-laps. Cleaning happens in
a separate step so that the exclusion audit trail is reproducible and so that a
filter decision can be revised without re-downloading anything.

Run it from the repo root:

    python -m f1_pit_strategy.ingest                 # all completed rounds
    python -m f1_pit_strategy.ingest --round 1       # a single round
    python -m f1_pit_strategy.ingest --force         # re-write existing rounds
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import fastf1
import pandas as pd
from fastf1.exceptions import DataNotLoadedError

from f1_pit_strategy import config

# Columns taken from session.laps. The degradation model needs tyre age,
# compound and stint identity; the rest are grouping keys or fields that the
# cleaning step filters on.
LAP_COLUMNS = [
    "Driver", "DriverNumber", "Team",
    "LapNumber", "Stint", "Position",
    "LapTime", "LapStartTime",
    "PitInTime", "PitOutTime",
    "Sector1Time", "Sector2Time", "Sector3Time",
    "Compound", "TyreLife", "FreshTyre",
    "TrackStatus", "IsAccurate", "Deleted",
]

# FastF1 returns these as pandas timedeltas. Parquet round-trips timedeltas
# inconsistently across pyarrow versions, and every downstream model wants
# seconds anyway, so they are converted exactly once: here.
TIMEDELTA_COLUMNS = [
    "LapTime", "LapStartTime", "PitInTime", "PitOutTime",
    "Sector1Time", "Sector2Time", "Sector3Time",
]

WEATHER_COLUMNS = [
    "Time", "AirTemp", "TrackTemp", "Humidity", "Pressure", "Rainfall", "WindSpeed",
]


def enable_cache(cache_dir: Path) -> None:
    """Point FastF1 at its on-disk HTTP cache.

    FastF1 caches the raw API responses itself, which makes that cache the true
    raw layer of this pipeline. Without it, every re-run re-downloads several
    hundred megabytes; with it, the second run of a round takes a second or two.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(str(cache_dir))


def completed_rounds(season: int, today: pd.Timestamp | None = None) -> pd.DataFrame:
    """Return schedule rows for rounds whose event date has already passed.

    The completed set is derived from the schedule rather than hardcoded,
    because the 2026 calendar changed during the season and a hardcoded round
    count would silently go stale.

    EventDate is tz-naive in FastF1, so it is compared against a tz-naive local
    timestamp. The boundary is therefore accurate to within a few hours, which
    does not matter: a round that slips through is caught by the per-round error
    handling in ingest_season().
    """
    if today is None:
        today = pd.Timestamp.now().normalize()
    schedule = fastf1.get_event_schedule(season, include_testing=False)
    past = schedule.loc[schedule["EventDate"] < today]
    return past.loc[past["RoundNumber"] > 0]


def _select_available(frame: pd.DataFrame, wanted: list[str]) -> pd.DataFrame:
    """Select the wanted columns, tolerating FastF1 version differences.

    Selecting with frame[wanted] would raise KeyError if a single column were
    renamed between FastF1 versions, killing a long ingest run near the end.
    Intersecting instead degrades gracefully and says what it did not find.
    """
    available = [column for column in wanted if column in frame.columns]
    missing = sorted(set(wanted) - set(available))
    if missing:
        print(f"    note: not present in this FastF1 version: {', '.join(missing)}")
    return frame.loc[:, available].copy()


def _to_seconds(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Convert timedelta columns to float seconds. NaT becomes NaN."""
    out = frame.copy()
    for column in columns:
        if column in out.columns:
            out[column] = out[column].dt.total_seconds()
    return out


def lap_frame(session, season: int, round_number: int) -> pd.DataFrame:
    """Flatten session.laps into a plain, parquet-safe DataFrame.

    Season and round are passed in rather than read off the session object:
    explicit arguments keep this function testable and avoid depending on
    attribute names that have moved between FastF1 versions.
    """
    laps = _select_available(session.laps, LAP_COLUMNS)
    laps = _to_seconds(laps, TIMEDELTA_COLUMNS)

    laps.insert(0, "Season", season)
    laps.insert(1, "Round", round_number)
    laps.insert(2, "EventName", session.event["EventName"])
    laps.insert(3, "Location", session.event["Location"])

    # Scheduled race distance. This is the N in the 12P/N^2 crossover threshold,
    # so it is captured at ingest rather than looked up again later.
    laps["TotalLaps"] = getattr(session, "total_laps", pd.NA)
    return laps.reset_index(drop=True)


def attach_weather(laps: pd.DataFrame, session) -> pd.DataFrame:
    """Attach the weather reading nearest in time to each lap's start.

    Weather is sampled roughly once a minute, so it cannot be joined on a key —
    it has to be matched by nearest timestamp. pd.merge_asof is the idiomatic
    tool for that: a sorted nearest-key join.

    FastF1 offers laps.get_weather_data() as a one-line shortcut for this. It is
    done explicitly here for two reasons: merge_asof is a pattern worth owning,
    and having the join direction visible in the code makes the choice
    reviewable instead of hidden inside a library call.
    """
    if "LapStartTime" not in laps.columns:
        return laps

    weather = _select_available(session.weather_data, WEATHER_COLUMNS)
    if weather.empty:
        print("    note: no weather data for this session")
        return laps

    weather = _to_seconds(weather, ["Time"]).rename(columns={"Time": "WeatherTime"})
    weather = weather.dropna(subset=["WeatherTime"]).sort_values("WeatherTime")

    # merge_asof refuses missing join keys, and a handful of laps legitimately
    # have no start time. Those rows are set aside and concatenated back, so the
    # lap count out equals the lap count in.
    has_time = laps["LapStartTime"].notna()
    merged = pd.merge_asof(
        laps.loc[has_time].sort_values("LapStartTime"),
        weather,
        left_on="LapStartTime",
        right_on="WeatherTime",
        direction="nearest",
    )
    if (~has_time).any():
        merged = pd.concat([merged, laps.loc[~has_time]], ignore_index=True)

    return merged.sort_values(["Driver", "LapNumber"]).reset_index(drop=True)


class LapsNotLoadedError(RuntimeError):
    """Raised when session.load() returns without usable lap data."""


# session.load() logs its failures and returns normally, so the real cause is in
# FastF1's log output above our error. These are the usual suspects.
LIKELY_LOAD_CAUSES = (
    "expired F1TV login token (re-authenticate with FastF1), "
    "no network access to livetiming.formula1.com, "
    "or the session data is not published yet"
)


def check_laps_loaded(session, season: int, round_number: int) -> None:
    """Fail loudly if session.load() did not actually produce laps.

    FastF1 catches download errors inside load() and only logs them. The
    failure then surfaces later as a DataNotLoadedError on the first access to
    session.laps, which names neither the round nor the cause. Checking right
    after load turns that into one clear error at the point of failure.

    Two failure shapes are covered: the laps attribute was never set (the
    property raises), and it was set but holds zero rows.
    """
    label = f"{season} round {round_number}"
    try:
        n_laps = len(session.laps)
    except DataNotLoadedError as exc:
        # 'raise ... from exc' keeps the original traceback attached as
        # __cause__, so nothing is hidden by the friendlier message.
        raise LapsNotLoadedError(
            f"{label}: session.load() returned without lap data. "
            f"Likely cause: {LIKELY_LOAD_CAUSES}. See the FastF1 log above."
        ) from exc
    if n_laps == 0:
        raise LapsNotLoadedError(
            f"{label}: session loaded but contains 0 laps. "
            f"Likely cause: {LIKELY_LOAD_CAUSES}."
        )


def round_path(raw_dir: Path, season: int, round_number: int) -> Path:
    """Hive-style partition path, so DuckDB can read the tree directly.

    Laying the files out as season=.../round=... lets a later query say
    read_parquet('data/raw/**/*.parquet', hive_partitioning := true) and get
    season and round back as real columns without any glue code.
    """
    return raw_dir / f"season={season}" / f"round={round_number:02d}.parquet"


def ingest_round(season: int, round_number: int, raw_dir: Path, force: bool = False) -> str:
    """Download one race session and write it to parquet. Returns a status line."""
    path = round_path(raw_dir, season, round_number)
    if path.exists() and not force:
        return "skipped (already written)"

    session = fastf1.get_session(season, round_number, "R")
    # telemetry and messages are large and this project does not use them.
    session.load(laps=True, telemetry=False, weather=True, messages=False)
    check_laps_loaded(session, season, round_number)

    laps = lap_frame(session, season, round_number)
    laps = attach_weather(laps, session)

    path.parent.mkdir(parents=True, exist_ok=True)
    laps.to_parquet(path, index=False)
    return f"wrote {len(laps)} laps, {laps['Driver'].nunique()} drivers"


def ingest_season(
    season: int,
    raw_dir: Path,
    cache_dir: Path,
    force: bool = False,
    pause: float = 2.0,
) -> pd.DataFrame:
    """Ingest every completed round of a season. Returns a per-round report."""
    enable_cache(cache_dir)
    schedule = completed_rounds(season)
    print(f"{len(schedule)} completed rounds found for {season}\n")

    report = []
    for event in schedule.itertuples():
        round_number = int(event.RoundNumber)
        print(f"[{round_number:02d}] {event.EventName}", flush=True)
        try:
            outcome = ingest_round(season, round_number, raw_dir, force=force)
        except Exception as exc:
            # A broad except is deliberate. One unavailable or malformed session
            # must not abort a twenty-race run, so each round is isolated and
            # its failure is recorded in the report instead of raised.
            outcome = f"FAILED: {type(exc).__name__}: {exc}"
        print(f"    {outcome}", flush=True)
        report.append(
            {"Round": round_number, "EventName": event.EventName, "Outcome": outcome}
        )
        time.sleep(pause)  # be a polite client of a free API

    return pd.DataFrame(report)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest F1 race laps to parquet.")
    parser.add_argument("--season", type=int, default=config.SEASON)
    parser.add_argument("--round", type=int, default=None,
                        help="ingest a single round instead of the whole season")
    parser.add_argument("--force", action="store_true",
                        help="re-write rounds that already have a parquet file")
    args = parser.parse_args()

    if args.round is not None:
        enable_cache(config.CACHE_DIR)
        print(f"[{args.round:02d}] ingesting single round", flush=True)
        print(f"    {ingest_round(args.season, args.round, config.RAW_DIR, args.force)}")
        return

    report = ingest_season(args.season, config.RAW_DIR, config.CACHE_DIR, args.force)

    print("\n--- summary ---")
    failures = report.loc[report["Outcome"].str.startswith("FAILED")]
    print(f"rounds processed: {len(report)}   failures: {len(failures)}")
    if not failures.empty:
        print(failures.to_string(index=False))


if __name__ == "__main__":
    main()
