"""Shared helpers for the EDA modules: loaders, markdown tables, small analysis functions, chart style.

LapTimeDelta is the one derived variable used throughout: a lap's lap time minus the median clean
lap time of its own circuit, in seconds. 0 is a typical lap there, +1 is one second slower, -1 is
one second faster. It puts circuits that differ by 40 s on one scale.
"""

from __future__ import annotations

import datetime

import matplotlib
matplotlib.use("Agg")  # draw to files, no window
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from f1_pit_strategy import clean, config
from f1_pit_strategy.eda import settings

# Okabe-Ito colours: designed to stay distinguishable for colour-blind viewers.
BLUE, ORANGE, GREEN = "#0072B2", "#E69F00", "#009E73"
VERMILLION, SKY, PINK, GREY = "#D55E00", "#56B4E9", "#CC79A7", "#B8B8B8"
COMPOUNDS = ["C1", "C2", "C3", "C4", "C5"]  # hardest to softest
STINT = ["Round", "Driver", "Stint"]
PERCENTILES = [0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99]
DELTA = "LapTimeDelta"
DELTA_LABEL = "Lap time vs the circuit's median lap (s)\n(+ slower, - faster)"

plt.rcParams.update({"font.family": "sans-serif", "axes.titlesize": 13, "axes.titleweight": "bold",
                     "axes.labelsize": 10, "xtick.labelsize": 9, "ytick.labelsize": 9})


def today() -> str:
    return datetime.date.today().isoformat()


# ---------- output ----------

def md_table(df: pd.DataFrame, index: bool = False) -> str:
    """Render a DataFrame as a markdown table (no extra dependency needed)."""
    if index:
        df = df.rename_axis(df.index.name or "").reset_index()

    def fmt(value) -> str:
        if pd.isna(value):
            return ""
        if isinstance(value, (bool, np.bool_)):
            return str(value)
        if isinstance(value, (int, np.integer)):
            return f"{value:,}"
        return str(value)

    header = "| " + " | ".join(str(c) for c in df.columns) + " |"
    divider = "|" + "|".join("---" for _ in df.columns) + "|"
    rows = ["| " + " | ".join(fmt(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join([header, divider, *rows])


def write_report(name: str, text: str) -> None:
    config.ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    (config.ANALYSIS_DIR / name).write_text(text, encoding="utf-8")
    print(f"wrote reports/analysis/{name}")


def write_doc(name: str, text: str) -> None:
    (config.DOCS_DIR / name).write_text(text, encoding="utf-8")
    print(f"wrote docs/{name}")


def style_axes(ax) -> None:
    """Remove chart junk: no top or right border, light grid."""
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color="#E6E6E6", lw=0.6)
    ax.set_axisbelow(True)


def save_figure(fig, name: str, source: str = "") -> None:
    """Export at 150 DPI (web) with a source line under the chart."""
    config.FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    if source:
        fig.text(0.01, 0.005, source, fontsize=8, color="#666666", ha="left", va="bottom")
    fig.savefig(config.FIGURES_DIR / name, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote reports/figures/{name}")


# ---------- data loading ----------

def load_ingested() -> pd.DataFrame:
    """The raw laps exactly as ingested (no cleaning, original dtypes). Read only."""
    return clean.load_raw()


def load_clean() -> pd.DataFrame:
    """Clean laps from data/processed, plus LapTimeDelta."""
    laps = pd.read_parquet(config.PROCESSED_DIR / "clean_laps.parquet")
    laps = laps.astype({"TyreLife": "int16"})
    laps[DELTA] = laps["LapTime"] - laps.groupby("Round")["LapTime"].transform("median")
    return laps


def load_exclusions() -> pd.DataFrame:
    return pd.read_parquet(config.PROCESSED_DIR / "exclusions.parquet")


# ---------- small analysis helpers ----------

def tukey_mask(values: pd.Series) -> pd.Series:
    """True where a value is outside the boxplot whiskers (Tukey rule)."""
    q1, q3 = values.quantile(0.25), values.quantile(0.75)
    spread = settings.IQR_K * (q3 - q1)
    return (values < q1 - spread) | (values > q3 + spread)


def stint_table(laps: pd.DataFrame) -> pd.DataFrame:
    """One row per stint: circuit, compound, number of clean laps."""
    return (laps.groupby(STINT, observed=True)
            .agg(City=("City", "first"), CompoundAbsolute=("CompoundAbsolute", "first"),
                 clean_laps=("LapTime", "size"))
            .reset_index())


def cell_counts(laps: pd.DataFrame) -> pd.DataFrame:
    """Stints per circuit x allocated compound. A compound nobody ran counts as 0."""
    allocation = pd.read_csv(config.ALLOCATION_FILE).dropna(subset=["soft", "medium", "hard"])
    stints = stint_table(laps)
    rows = []
    for r in allocation.itertuples():
        for label in ("soft", "medium", "hard"):
            compound = getattr(r, label)
            n = int(((stints["Round"] == r.round) & (stints["CompoundAbsolute"] == compound)).sum())
            rows.append((r.round, r.city, label.upper(), compound, n))
    return pd.DataFrame(rows, columns=["Round", "City", "Label", "Compound", "Stints"])


def stint_slopes(laps: pd.DataFrame) -> pd.DataFrame:
    """Naive slope of LapTime on TyreLife inside each stint (np.polyfit, degree 1).

    Naive because inside one stint tyre age and race lap rise together, so this slope is
    tyre wear MINUS the speed-up from burning fuel; it is a sanity check, not the final beta.
    """
    def slope(stint: pd.DataFrame) -> float:
        return np.polyfit(stint["TyreLife"].astype(float), stint["LapTime"], 1)[0]

    slopes = laps.groupby(STINT, observed=True)[["TyreLife", "LapTime"]].apply(slope).rename("slope")
    meta = laps.groupby(STINT, observed=True)[["City", "CompoundAbsolute"]].first()
    return pd.concat([slopes, meta], axis=1).reset_index()


def circuit_variance_share(laps: pd.DataFrame) -> float:
    """Share of the variance in raw lap time that lies between circuits."""
    within = laps.groupby("Round")["LapTime"].apply(lambda s: ((s - s.mean()) ** 2).sum()).sum()
    return float(1 - within / ((laps["LapTime"] - laps["LapTime"].mean()) ** 2).sum())
