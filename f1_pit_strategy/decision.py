"""Decision layer: cross each circuit's degradation rate d with the pit-stop threshold 12P/N^2.

    python -m f1_pit_strategy.decision

Rule: two stops beat one when d > 12 P / N^2 (equal stint splits, docs/scope.md section 2).

Two tiers, so the strategy call only uses a P we can trust:
  Tier 1: circuits with at least MIN_STOPS_FOR_P usable green-flag, dry stops. Full call.
  Tier 2: the rest. Their d and lap count are shown, but P, threshold and call are N/A.
          P is never imputed (see docs/scope.md section 14).

Reads degradation_by_circuit.csv and pit_loss.csv; writes data/processed/decision_summary.csv,
docs/decision.md and reports/figures/09_decision_chart.png.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from f1_pit_strategy import config, degradation
from f1_pit_strategy.eda import helpers
from f1_pit_strategy.eda.helpers import BLUE, GREY, VERMILLION


def build_summary(d_by_circuit: pd.DataFrame, pit: pd.DataFrame) -> pd.DataFrame:
    """One row per circuit: d, P, threshold, tier, call, and how sure the call is."""
    s = d_by_circuit.merge(pit[["Round", "N", "stops", "P", "p25", "p75", "threshold_beta"]], on="Round", validate="one_to_one")
    s["Tier"] = np.where(s["stops"].fillna(0) >= config.MIN_STOPS_FOR_P, 1, 2)
    t1 = s["Tier"] == 1
    s["Threshold"] = np.where(t1, s["threshold_beta"], np.nan)
    s["ThrLow"], s["ThrHigh"] = np.where(t1, 12 * s["p25"] / s["N"] ** 2, np.nan), np.where(t1, 12 * s["p75"] / s["N"] ** 2, np.nan)
    s["Call"] = np.where(~t1, config.NA_TEXT, np.where(s["D"] > s["Threshold"], "2-Stop", "1-Stop"))
    clear = (s["D_Low"] > s["ThrHigh"]) | (s["D_High"] < s["ThrLow"])
    s["Certainty"] = np.where(~t1, "", np.where(clear, "clear", "uncertain"))
    s["Margin"] = s["D"] - s["Threshold"]
    return s


def table_rows(s: pd.DataFrame) -> pd.DataFrame:
    """The summary table: Tier 1 first (2-Stop calls, then 1-Stop, widest margin first), then Tier 2."""
    s = pd.concat([s[s["Tier"] == 1].sort_values("Margin", ascending=False), s[s["Tier"] == 2].sort_values("D", ascending=False)])
    def p_text(r) -> str:
        if r.Tier == 2:
            return config.NA_TEXT
        text = f"{r.P:.1f}"
        return f"{text} (IQR {r.p25:.1f}-{r.p75:.1f})" if r.stops <= config.BORDERLINE_MAX_STOPS else text
    return pd.DataFrame({
        "Circuit": s["City"], "Clean Laps": s["CleanLaps"],
        "Degradation Rate (s/lap)": [f"{r.D:.3f} ({r.D_Low:.3f} to {r.D_High:.3f})" for r in s.itertuples()],
        "Valid Pit Stops (n)": s["stops"].astype(int),
        "Median P (s)": [p_text(r) for r in s.itertuples()],
        "Threshold (12P/N²)": [config.NA_TEXT if r.Tier == 2 else f"{r.Threshold:.3f}" for r in s.itertuples()],
        "Recommended Strategy": s["Call"], "Certainty of call": s["Certainty"]})


def decision_chart(s: pd.DataFrame) -> None:
    t1, t2 = s[s["Tier"] == 1], s[s["Tier"] == 2]
    fig, ax = plt.subplots(figsize=(9.5, 8.2))
    top = 0.17
    ax.fill_between([0, top], [0, top], top, color=VERMILLION, alpha=0.07, lw=0)
    ax.fill_between([0, top], 0, [0, top], color=BLUE, alpha=0.07, lw=0)
    ax.plot([0, top], [0, top], color="#444444", ls="--", lw=1.4)
    ax.text(0.004, 0.135, "2-Stop zone\n(tyres wear faster\nthan the threshold)", color=VERMILLION, fontsize=10, weight="bold", va="top")
    ax.text(0.168, 0.006, "1-Stop zone", color=BLUE, fontsize=10, weight="bold", ha="right")
    for r in t1.itertuples():
        ax.plot([r.Threshold] * 2, [r.D_Low, r.D_High], color=GREY, lw=1.2, zorder=1)
        if r.stops <= config.BORDERLINE_MAX_STOPS:  # P's spread, only where P rests on few stops
            ax.plot([r.ThrLow, r.ThrHigh], [r.D] * 2, color="#555555", lw=2.4, zorder=2, solid_capstyle="butt")
        colour = VERMILLION if r.Call == "2-Stop" else BLUE
        ax.scatter(r.Threshold, r.D, s=70, zorder=3, edgecolor=colour, facecolor=colour if r.Certainty == "clear" else "white", linewidth=1.8)
    nudge = {"Budapest": (-6, 9), "Monaco": (-6, -15), "Zandvoort": (-8, 8), "Spielberg": (7, 4), "Austin": (-8, 8), "Singapore": (-8, 9),
             "Silverstone": (7, 2), "Suzuka": (6, -15), "Madrid": (-8, 8), "Miami": (-6, 9), "Mexico City": (7, -8), "Kuala Lumpur": (-10, -17), "Barcelona": (7, -4)}
    for r in t1.itertuples():
        dx, dy = nudge.get(r.City, (6, 5))
        ax.annotate(r.City, (r.Threshold, r.D), xytext=(dx, dy), textcoords="offset points", fontsize=9.5, ha="right" if dx < 0 else "left")
    ax.set_xlim(0, top); ax.set_ylim(-0.005, top)
    ax.set_xlabel("Threshold 12P/N² (s/lap): the wear rate above which a second stop pays for itself")
    ax.set_ylabel("Observed degradation rate d (s/lap)")
    ax.set_title("Where degradation beats the pit-stop threshold, the 13 Tier 1 circuits", loc="left", fontsize=13, weight="bold", y=1.075)
    ax.text(0, 1.03, f"Excluded (fewer than {config.MIN_STOPS_FOR_P} green-flag stops): {', '.join(t2.sort_values('Round')['City'])}.", transform=ax.transAxes, fontsize=9.5, color="#444444")
    fig.subplots_adjust(bottom=0.2)
    fig.text(0.07, 0.085, "Filled dot: the 95% interval of d clears the threshold range. Hollow dot: it overlaps (call uncertain). Grey vertical bar: 95% interval of d.\nDark horizontal bar: P's IQR, shown for circuits with 15 stops or fewer.",
             fontsize=8.5, style="italic", color="#444444", va="center")
    helpers.style_axes(ax)
    helpers.save_figure(fig, "09_decision_chart.png", f"Source: FastF1 timing 2026, clean laps (degradation) and {int(t1['stops'].sum())} green-flag stops (P). Equal stint splits assumed.")


def robustness(s: pd.DataFrame, laps: pd.DataFrame) -> str:
    """Repeat with team intercepts instead of driver intercepts and report what moves."""
    _, alt = degradation.run_all(laps, fe="Team")
    m = s.merge(alt[["Round", "D"]], on="Round", suffixes=("", "_team"))
    t1 = m[m["Tier"] == 1]
    flips = int(((t1["D_team"] > t1["Threshold"]) != (t1["D"] > t1["Threshold"])).sum())
    return (f"Replacing driver intercepts by team intercepts changes d by at most {(m['D_team'] - m['D']).abs().max():.3f} s/lap "
            f"(correlation {np.corrcoef(m['D'], m['D_team'])[0, 1]:.2f} across the 19 circuits) and flips {flips} of the 13 Tier 1 calls.")


def markdown(s: pd.DataFrame, table: pd.DataFrame, robust: str) -> str:
    t1, t2 = s[s["Tier"] == 1], s[s["Tier"] == 2]
    border = t1[t1["stops"] <= config.BORDERLINE_MAX_STOPS].sort_values("stops")
    two, unsure = int((t1["Call"] == "2-Stop").sum()), int((t1["Certainty"] == "uncertain").sum())
    return f"""# Decision layer: one stop or two?

Reproduce: `python -m f1_pit_strategy.decision` (this file is generated). Needs `degradation_by_circuit.csv` (from `degradation.py`) and `pit_loss.csv` (from `pit_loss.py`).

**Rule.** Two stops beat one when the degradation rate d is above the threshold 12P/N² (P = pit-lane loss in seconds, N = race laps, equal stint splits).
d is the circuit's lap-weighted mean of its compound wear slopes, from one regression per circuit (driver intercepts, shared race-lap term, a tyre-age slope per compound; standard errors clustered by stint).

## Result

At the {len(t1)} Tier 1 circuits the rule gives **{two} two-stop and {len(t1) - two} one-stop calls**; {unsure} of the {len(t1)} calls are uncertain because the 95% interval of d overlaps the threshold range (P's IQR).

{helpers.md_table(table)}

`Certainty of call` is *clear* when the whole 95% interval of d lies above (or below) the threshold range built from P's IQR, and *uncertain* when it overlaps. Order: Tier 1 by margin (d minus threshold), then Tier 2.

![09_decision_chart.png](../reports/figures/09_decision_chart.png)

## Why a scatter plot with error bars and a y = x line

- **The decision is a comparison of two numbers in the same unit.** d (observed wear) and the threshold 12P/N² are both seconds per lap. Putting the threshold on x and d on y, with a
  dashed y = x line, turns the rule into geometry: above the line two stops, below one stop, and the distance from the line is the margin. Paired bars for 13 circuits would make the reader subtract
  by eye; a bar of the margin alone would hide whether a circuit is far from the line because wear is high or because the threshold (pit loss, race length) is low.
- **The line is the rule itself.** Both axes use the same limits (0 to 0.17), so the 45 degree line is an honest boundary, not a drawing choice.
- **Error bars show what the point estimate hides.** The vertical bar is the 95% interval of d; the horizontal bar is P's IQR for the circuits where P rests on few stops. Uncertainty in d and in the
  threshold sit on different axes, so a 2D plot shows both at once. A filled dot means the interval clears the threshold range, a hollow dot means the call could flip.
- **Readable and accessible.** Direct labels (no legend lookup), colour-blind-safe colours, and the excluded Tier 2 circuits named in the subtitle.
- **Limits.** Thirteen labelled points are close to crowding; the chart shows Tier 1 only, so the table above carries the exact numbers and Tier 2. The intervals are statistical: they do not weigh the cost
  of a wrong call.

## Methodological notes

**Why six circuits have no call (Tier 2).** {', '.join(f'{r.City} (n = {int(r.stops)})' for r in t2.sort_values('stops').itertuples())} have fewer than {config.MIN_STOPS_FOR_P} usable green-flag, dry stops. Safety cars, yellow flags and rain removed most of their green-flag stops (833 stops found, 317 usable overall), and a median P from so few stops is too noisy to decide a strategy. We do not impute P or borrow it from other circuits; their degradation rate and lap count are still shown because those rest on hundreds of laps.

**Borderline Tier 1 circuits.** {', '.join(f'{r.City} (n = {int(r.stops)}, P {r.P:.1f} s, IQR {r.p25:.1f} to {r.p75:.1f})' for r in border.itertuples())} sit just above the cutoff; their P's spread is shown in the table and as dark horizontal bars on the chart.

**Robustness.** {robust}

## Limits

- The 12P/N² rule assumes equal stint splits and one linear wear rate per race; real strategies mix compounds and stint lengths (the grid-search optimiser, a later step, relaxes that).
- d is a mean of compound slopes weighted by laps run, so it describes the mix teams actually ran. Wear beyond about 30 laps of tyre age is thinly observed (docs/eda.md, chart 5), and a one-stop needs long stints.
- A stint's slope shows wear plus the race-lap effect together; the model splits them using stints that start on different laps. A wrong race-lap effect would shift every compound of a circuit by the same amount.
- Mexico City data stops at lap 56 of 71 (N = 71 is used). Traffic is not filtered. P is the median of the stop-lap loss and carries the approximations listed in docs/scope.md.
- Intervals use stint-clustered standard errors with 30 to 65 stints per circuit; they are approximate.
"""


def main() -> None:
    d = pd.read_csv(config.PROCESSED_DIR / "degradation_by_circuit.csv")
    pit = pd.read_csv(config.PROCESSED_DIR / "pit_loss.csv")
    s = build_summary(d, pit)
    table = table_rows(s)
    s.to_csv(config.PROCESSED_DIR / "decision_summary.csv", index=False)
    decision_chart(s)
    helpers.write_doc("decision.md", markdown(s, table, robustness(s, degradation.load_laps())))
    pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 60)
    print(table.to_string(index=False))


if __name__ == "__main__":
    main()
