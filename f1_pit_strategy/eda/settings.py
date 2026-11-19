"""Settings for the EDA and data-quality audit.

Cleaning thresholds stay in f1_pit_strategy/config.py. This file holds what the audit and
the EDA add: quality thresholds, business rules for value ranges, and the scoring rule.
The thresholds follow the programmatic-eda and data-quality-audit workflows of the
data-analytics-skills repository (see the README).
"""

# --- quality thresholds ---
NULL_WARN = 0.05            # 5% nulls or more: investigate
NULL_FAIL = 0.30            # 30% nulls or more: too sparse without a justification
DUP_FAIL = 0.01             # full-row duplicates above 1%: fail
Z_LIMIT = 3.0               # |z| above this is flagged
IQR_K = 1.5                 # outside Q1 - 1.5 IQR or Q3 + 1.5 IQR is flagged
SKEW_MODERATE, SKEW_HIGH, SKEW_EXTREME = 0.5, 1.0, 2.0
CORR_STRONG = 0.8           # pairs at or above this are checked for redundancy
DOMINANT_CATEGORY = 0.90    # one category above 90% of rows is flagged

# --- business rules for the value-range check (domain knowledge) ---
VALUE_RULES = {
    "LapTime": (60, 300),     # seconds; no F1 circuit lap is outside this
    "LapNumber": (1, 80),
    "Stint": (1, 10),
    "TyreLife": (1, 80),      # laps on the set; used sets can exceed the race lap
    "TrackTemp": (5, 70),     # degrees C; 0.0 is a sensor sentinel
    "AirTemp": (0, 50),
    "Humidity": (0, 100),
    "Pressure": (700, 1100),  # mbar; Mexico City sits at 2,240 m and reads about 783
    "WindSpeed": (0, 30),
    "Position": (1, 22),
    "TotalLaps": (40, 80),
}
ALLOWED_COMPOUNDS = {"SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET"}
SECTOR_SUM_TOLERANCE = 0.1        # seconds between LapTime and the sum of its sectors
INACCURATE_LAP_TOLERANCE = 0.01   # share of NORMAL green laps flagged not accurate

# Columns that are legitimately empty on many rows, with the reason.
EXPECTED_NULLS = {
    "PitInTime": "only set on in-laps",
    "PitOutTime": "only set on out-laps",
    "Deleted": "FastF1 field that this feed never fills",
    "Sector1Time": "missing on laps without a full timing trace",
    "Sector2Time": "missing on laps without a full timing trace",
    "Sector3Time": "missing on laps without a full timing trace",
    "LapTime": "unfinished laps (retirements, red flags)",
    "TyreLife": "tyre age not reported on some laps",
    "Position": "missing on a few laps",
}

# --- audit scoring ---
DIMENSION_WEIGHTS = {"Completeness": 0.20, "Accuracy": 0.20, "Consistency": 0.20,
                     "Timeliness": 0.15, "Uniqueness": 0.15, "Validity": 0.10}
# Each dimension starts at 10 and loses points per FAILED check, by severity.
SEVERITY_PENALTY = {"CRITICAL": 5.0, "HIGH": 2.0, "MEDIUM": 1.0, "LOW": 0.5}
VERDICT_PASS, VERDICT_CONDITIONAL = 7.0, 5.0   # 7 or more PASS, 5 to 6.9 CONDITIONAL, below FAIL

# Illustrative pit-lane loss values for the impact estimate (the scope example is 22 s).
PIT_LOSS_LOW, PIT_LOSS_BASE, PIT_LOSS_HIGH = 18.0, 22.0, 26.0
