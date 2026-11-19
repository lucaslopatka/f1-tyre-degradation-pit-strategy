"""Project-wide configuration: paths, season, and tunable thresholds."""

from pathlib import Path

# Paths are anchored to this file rather than the current working directory, so
# scripts behave identically whether they are run from the repo root, from a
# notebook, or from an IDE.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

CACHE_DIR = PROJECT_ROOT / "cache"
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
REFERENCE_DIR = DATA_DIR / "reference"
FIGURES_DIR = PROJECT_ROOT / "reports" / "figures"
ANALYSIS_DIR = PROJECT_ROOT / "reports" / "analysis"   # EDA, audit and insight reports
DOCS_DIR = PROJECT_ROOT / "docs"

SEASON = 2026

# Cleaning thresholds live here rather than inline in the cleaning code, so that
# sensitivity to each one can be re-run and reported in the README.
MIN_STINT_LAPS = 5          # stints shorter than this cannot support a slope estimate
GREEN_FLAG_CODE = "1"       # FastF1 TrackStatus: 1=green, 2=yellow, 4=SC, 5=red, 6/7=VSC

# --- cleaning knobs (clean.py) ---
WET_COMPOUNDS = ("INTERMEDIATE", "WET")  # any lap on these tyres is a wet lap
WET_RACE_LAP_SHARE = 0.25   # race is dropped entirely if more than this share of its laps are wet
POST_WET_BUFFER_LAPS = 3    # track stays damp after rain: also drop this many laps after a wet lap
RESTART_BUFFER_LAPS = 1     # laps dropped after a non-green lap (restart: cold tyres, bunched field)
OUTLIER_RATIO = 1.07        # drop a lap slower than this multiple of its stint's median lap time
MIN_VALID_TRACK_TEMP = 1.0  # a reading below this is a sensor glitch (the feed fills in 0.0)

ALLOCATION_FILE = REFERENCE_DIR / "pirelli_allocation.csv"  # SOFT/MEDIUM/HARD -> C1-C5 per round

# --- columns kept in the processed files (everything else stays in data/raw) ---
CLEAN_COLUMNS = [
    "Round", "City", "Driver", "Team", "Stint", "LapNumber",
    "LapTime", "Compound", "CompoundAbsolute", "TyreLife", "FreshTyre", "TrackTemp", "TotalLaps",
]
# The audit table keeps the lap identity, the values the rules looked at, and the reason.
EXCLUSION_COLUMNS = [
    "Round", "City", "Driver", "Stint", "LapNumber",
    "LapTime", "Compound", "TyreLife", "TrackStatus", "reason",
]

# --- pit-lane loss (pit_loss.py) ---
PIT_REF_WINDOW_LAPS = 5     # reference pace = driver's clean laps within this many race laps of the in-lap
PIT_REF_MIN_LAPS = 3        # a stop needs at least this many reference laps, else it is skipped
MIN_STOPS_FOR_P = 10        # a circuit with fewer usable stops gets a 'thin' flag

# --- degradation model (degradation.py) ---
MIN_CELL_STINTS = 4         # a circuit-compound cell with fewer stints is not estimable
THIN_CELL_STINTS = 8        # 4 to 7 stints: estimable but thin (wide interval)

# --- decision layer (decision.py) ---
BORDERLINE_MAX_STOPS = 15   # Tier 1 circuits with this many stops or fewer get P's spread (IQR) shown beside the median
NA_TEXT = "N/A (Insufficient green-flag stops: n < 10)"

# --- validation (validate.py) ---
FINISHER_LAP_SHARE = 0.9    # a driver finished if the last recorded lap reaches this share of the race's last lap
