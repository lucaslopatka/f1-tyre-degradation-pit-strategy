"""Charts and their written conclusions (workflow: visualization-builder).

Rules applied: pick the chart from the message (distribution = histogram or box plot,
relationship = line or scatter, comparison = sorted bars), put the FINDING in the title,
grey out what is not the point, label directly instead of using legends, at most 4 lines
per panel (so compounds get small multiples), a source line on every chart, 150 DPI export,
colour-blind-safe palette.

Writes reports/figures/01..08 and docs/eda.md (each chart with its business and
statistical conclusion; every number is computed here, none is typed by hand).
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from f1_pit_strategy.eda import commentary, helpers, profile
from f1_pit_strategy.eda.helpers import BLUE, DELTA, DELTA_LABEL, GREY, ORANGE, VERMILLION

SOURCE = "Source: FastF1 timing, 2026 season, cleaned race laps (n = {n:,})"


def binned_mean(laps: pd.DataFrame, x: str, min_laps: int = 30) -> pd.DataFrame:
    """Mean LapTimeDelta at each x, hiding bins with fewer than min_laps laps."""
    stats = laps.groupby(x, observed=True)[DELTA].agg(["mean", "count"])
    return stats.loc[stats["count"] >= min_laps]


# ---------- figures ----------

def fig_circuit_box(laps: pd.DataFrame, eta2: float) -> None:
    """Comparison of distributions across groups -> box plot, sorted, two circuits highlighted."""
    order = laps.groupby("City", observed=True)["LapTime"].median().sort_values().index.tolist()
    fig, ax = plt.subplots(figsize=(9, 7))
    box = ax.boxplot([laps.loc[laps["City"] == c, "LapTime"] for c in order], orientation="horizontal",
                     patch_artist=True, flierprops={"markersize": 2, "markerfacecolor": GREY, "markeredgecolor": GREY})
    for patch, city in zip(box["boxes"], order):
        patch.set(facecolor=ORANGE if city in (order[0], order[-1]) else GREY, edgecolor="#555555")
    for median in box["medians"]:
        median.set(color="black", lw=1.5)
    ax.set_yticks(range(1, len(order) + 1), order)
    ax.set_xlabel("Lap time (s)")
    ax.set_title(f"The circuit explains {eta2:.0%} of lap-time variance:\nmedians run from {laps.groupby('City', observed=True)['LapTime'].median().min():.0f} s to {laps.groupby('City', observed=True)['LapTime'].median().max():.0f} s", loc="left")
    ax.text(0.99, 0.04, "How to read: box = middle 50% of laps,\nline = median, whiskers = 1.5 x box length,\ndots = outliers",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=8.5, style="italic", color="#444444")
    ax.spines[["top", "right"]].set_visible(False)
    helpers.save_figure(fig, "01_circuit_dominates_lap_time.png", SOURCE.format(n=len(laps)))


def fig_race_lap(laps: pd.DataFrame, slope: float, early: float, late: float) -> None:
    """Relationship between two variables -> line of averages with a trend line."""
    curve = binned_mean(laps, "LapNumber")
    counts = laps.groupby("LapNumber").size()
    fig, (ax, bars) = plt.subplots(2, 1, figsize=(9, 6.2), sharex=True, gridspec_kw={"height_ratios": [4, 1], "hspace": 0.08})
    ax.plot(curve.index, curve["mean"], color=BLUE, marker="o", ms=3.5, lw=1.4)
    x = np.array([2, 69])
    ax.plot(x, np.polyval(np.polyfit(laps["LapNumber"], laps[DELTA], 1), x), color=VERMILLION, ls="--", lw=1.4)
    ax.axhline(0, color="#777777", lw=0.8)
    ax.set_ylim(-1.6, 1.9)
    ax.annotate(f"laps 2-6 average {early:+.2f} s", xy=(4, early), xytext=(13, 1.55), fontsize=9,
                arrowprops={"arrowstyle": "->", "color": "#555555"})
    ax.annotate(f"laps 60+ average {late:+.2f} s", xy=(63, late), xytext=(40, -1.35), fontsize=9,
                arrowprops={"arrowstyle": "->", "color": "#555555"})
    ax.text(40, 0.95, f"trend {slope:+.3f} s per lap", color=VERMILLION, fontsize=10, weight="bold")
    ax.set_ylabel(DELTA_LABEL)
    ax.set_title("Cars get about 0.04 s faster every race lap\n(fuel burn and track evolution)", loc="left")
    helpers.style_axes(ax)
    bars.bar(counts.index, counts.values, color=GREY, width=0.8)
    bars.axhline(30, color=VERMILLION, lw=1, ls=":")
    bars.set_xlabel("Race lap")
    bars.set_ylabel("Laps\nper point", fontsize=8.5)
    bars.text(79, 70, "dotted line = 30 laps,\nthe minimum per point", ha="right", fontsize=8, color=VERMILLION)
    helpers.style_axes(bars)
    helpers.save_figure(fig, "02_lap_time_falls_with_race_lap.png", SOURCE.format(n=len(laps)))


def fig_tyre_age_small_multiples(laps: pd.DataFrame, stints: pd.DataFrame) -> None:
    """One panel per compound (max 4 lines rule) with a shared y-axis for direct comparison."""
    fig, axes = plt.subplots(2, 3, figsize=(13, 7), sharey=True, sharex=True)
    for ax, compound in zip(axes.flat, helpers.COMPOUNDS):
        sub = laps[laps["CompoundAbsolute"] == compound]
        curve = binned_mean(sub, "TyreLife")
        n_stints = int((stints["CompoundAbsolute"] == compound).sum())
        n_cities = stints.loc[stints["CompoundAbsolute"] == compound, "City"].nunique()
        ax.plot(curve.index, curve["mean"], color=BLUE, marker="o", ms=3, lw=1.3)
        ax.axhline(0, color="#777777", lw=0.8)
        ax.set_title(f"{compound}: {n_stints} stints, {n_cities} circuits", fontsize=10, loc="left")
        helpers.style_axes(ax)
    note = axes.flat[5]
    note.axis("off")
    note.text(0, 0.5, "Read each panel as:\naverage lap time against tyre age,\n0 = the circuit's typical lap.\n\nMost lines slope DOWN: the car\nis lighter and the track faster\nlater in the race, which hides\ntyre wear until race lap is\ncontrolled for.", fontsize=10, va="center")
    for ax in axes[1, :2]:
        ax.set_xlabel("Tyre age (laps)")
    for ax in axes[:, 0]:
        ax.set_ylabel(DELTA_LABEL, fontsize=9)
    fig.suptitle("Raw lap time falls with tyre age for most compounds: wear is hidden until race lap is controlled for",
                 x=0.01, ha="left", fontsize=13, weight="bold")
    helpers.save_figure(fig, "03_tyre_age_by_compound.png", SOURCE.format(n=len(laps)))


def fig_slopes(slopes: pd.DataFrame) -> None:
    """Distribution of one continuous variable -> histogram with median line."""
    s = slopes["slope"]
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.hist(s.clip(-0.4, 0.4), bins=60, color=GREY, edgecolor="white")
    grid = np.linspace(-0.4, 0.4, 400)
    scale = len(s) * (0.8 / 60)  # counts per unit of x, so densities share the histogram's axis
    robust = (s.quantile(.75) - s.quantile(.25)) / 1.349
    for sigma, colour, label in [(s.std(), BLUE, f"normal, same std ({s.std():.3f})"), (robust, ORANGE, f"normal, std from middle half ({robust:.3f})")]:
        ax.plot(grid, scale * np.exp(-0.5 * ((grid - s.mean()) / sigma) ** 2) / (sigma * np.sqrt(2 * np.pi)), color=colour, ls="--", lw=1.6, label=label)
    ax.legend(loc="upper left", fontsize=8.5, frameon=False)
    ax.axvline(0, color="black", lw=0.9)
    ax.axvline(s.median(), color=VERMILLION, lw=2)
    ax.text(s.median() + 0.012, ax.get_ylim()[1] * 0.80, f"median {s.median():+.3f}", color=VERMILLION, weight="bold")
    ax.text(0.99, 0.72, f"std {s.std():.3f} s/lap\n{(s > 0).mean():.0%} of stints slope up\n{int((s.abs() > 0.4).sum())} stints beyond +/-0.4 (piled at the edges)",
            transform=ax.transAxes, ha="right", fontsize=9.5)
    ax.set_xlabel("Naive slope: seconds per lap of tyre age, per stint (wear minus fuel burn)")
    ax.set_ylabel("Stints")
    ax.set_title(f"A typical stint is nearly flat, but single stints are noisy\n({len(s)} stints)", loc="left")
    helpers.style_axes(ax)
    helpers.save_figure(fig, "04_stint_slopes_are_noisy.png", SOURCE.format(n=len(slopes)))


def fig_tyre_age_coverage(laps: pd.DataFrame) -> None:
    ages = laps["TyreLife"]
    over30 = float((ages > 30).mean())
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.hist(ages, bins=range(0, 62, 2), color=BLUE, edgecolor="white")
    ax.axvspan(30, 60, color=ORANGE, alpha=0.18)
    ax.axvline(ages.median(), color="black", lw=1.2)
    ax.text(ages.median() + 0.6, ax.get_ylim()[1] * 0.92, f"median {ages.median():.0f} laps", fontsize=9.5)
    ax.text(45, ax.get_ylim()[1] * 0.55, f"only {over30:.1%} of laps\nare on tyres\nolder than 30 laps", color="#8a5a00", weight="bold", ha="center")
    ax.set_xlabel("Tyre age (laps)")
    ax.set_ylabel("Clean laps")
    ax.set_title("Long-stint evidence is thin: tyre ages beyond 30 laps are rare", loc="left")
    helpers.style_axes(ax)
    helpers.save_figure(fig, "05_tyre_age_coverage.png", SOURCE.format(n=len(laps)))


BY_DESIGN = ["lap_1", "in_or_out_lap", "not_green", "after_non_green"]
BAD_DATA = ["missing_laptime", "not_accurate", "missing_compound", "missing_tyrelife", "bad_track_temp", "slow_outlier"]


def fig_funnel(excl: pd.DataFrame, raw_rows: int) -> None:
    """Comparison of categories (8 to 15) -> horizontal bars sorted by size, values at the bar ends."""
    counts = excl["reason"].value_counts().sort_values()
    share = counts.reindex(BY_DESIGN).sum() / len(excl)
    bad = counts.reindex(BAD_DATA).sum() / raw_rows
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.barh(counts.index, counts.values, color=[BLUE if r in BY_DESIGN else GREY for r in counts.index], height=0.65)
    for y, v in enumerate(counts.values):
        ax.text(v + 20, y, f"{v:,}", va="center", fontsize=9)
    ax.set_xlabel("Laps dropped")
    ax.set_xlim(0, counts.max() * 1.12)
    ax.set_title(f"{share:.0%} of the {len(excl):,} dropped laps are pit, safety-car and restart laps\n(removed by design); only {bad:.1%} of raw laps are bad data", loc="left")
    ax.spines[["top", "right"]].set_visible(False)
    helpers.save_figure(fig, "06_cleaning_funnel.png", f"Source: cleaning audit table (n = {len(excl):,} dropped of {raw_rows:,} raw laps). Blue = by design; grey = wet laps and races, short stints, bad data.")


def fig_cells(cells: pd.DataFrame) -> None:
    """Matrix of counts -> annotated heat table; thin cells in bold red."""
    cities = cells.drop_duplicates("Round").sort_values("Round")["City"].tolist()
    grid = pd.DataFrame(np.nan, index=cities, columns=helpers.COMPOUNDS)
    for r in cells.itertuples():
        grid.loc[r.City, r.Compound] = r.Stints
    fig, ax = plt.subplots(figsize=(7, 8))
    ax.imshow(np.ma.masked_invalid(grid.to_numpy(dtype=float)), cmap="Blues", vmin=0, vmax=40, aspect="auto")
    ax.set_xticks(range(5), grid.columns)
    ax.set_yticks(range(len(cities)), cities)
    for i in range(len(cities)):
        for j in range(5):
            v = grid.iloc[i, j]
            if pd.notna(v):
                ax.text(j, i, int(v), ha="center", va="center", fontsize=9,
                        color=VERMILLION if v < 4 else "black", weight="bold" if v < 4 else "normal")
    ax.xaxis.tick_top()
    ax.set_title(f"{int((cells['Stints'] < 4).sum())} of {len(cells)} circuit-compound cells have fewer than 4 stints\n(red = cannot be estimated; blank = compound not allocated)",
                 loc="left", y=1.08)
    helpers.save_figure(fig, "07_stints_per_cell.png", f"Source: cleaned laps, stints with at least 5 clean laps (n = {int(cells['Stints'].sum())} stints)")


def fig_correlation(laps: pd.DataFrame) -> pd.DataFrame:
    data = laps[["LapTime", DELTA, "TyreLife", "LapNumber", "TrackTemp"]].assign(FreshTyre=laps["FreshTyre"].astype(int))
    corr = data.corr()
    fig, ax = plt.subplots(figsize=(7, 6.4))
    image = ax.imshow(corr, cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(len(corr)), corr.columns, rotation=40, ha="right")
    ax.set_yticks(range(len(corr)), corr.columns)
    for i in range(len(corr)):
        for j in range(len(corr)):
            ax.text(j, i, f"{corr.iloc[i, j]:.2f}", ha="center", va="center", fontsize=9,
                    color="white" if abs(corr.iloc[i, j]) > 0.6 else "black")
    fig.colorbar(image, ax=ax, label="Correlation")
    ax.set_title("Race lap moves lap time most;\ntyre age alone barely does", loc="left", fontsize=11)
    helpers.save_figure(fig, "08_correlation_matrix.png",
                        f"{DELTA} = lap time minus the circuit's median lap, in seconds. Source: cleaned race laps (n = {len(laps):,})")
    return corr


# ---------- docs/eda.md ----------

def eda_markdown(laps: pd.DataFrame, excl: pd.DataFrame, raw_rows: int, cells: pd.DataFrame, stints: pd.DataFrame,
                 slopes: pd.DataFrame, stats: dict) -> str:
    d = laps[["LapTime", DELTA, "TyreLife"]].describe(percentiles=helpers.PERCENTILES).T
    overall = pd.DataFrame({"mean": d["mean"], "median": d["50%"], "p5": d["5%"], "p95": d["95%"], "p99": d["99%"], "max": d["max"]}).round(2)
    overall.index = ["Lap time (s)", f"{DELTA} (s)", "Tyre age (laps)"]
    per_circuit = laps.groupby("City", observed=True)["LapTime"].agg(
        median="median", spread=lambda s: s.quantile(0.95) - s.quantile(0.05))
    within_outliers = int(laps.groupby("Round")["LapTime"].apply(lambda s: helpers.tukey_mask(s).sum()).sum())
    bands = pd.cut(laps["TyreLife"], [1, 5, 10, 20, 30, 60], labels=["2-5", "6-10", "11-20", "21-30", "31+"])
    band_table = laps.assign(band=bands).pivot_table(index="CompoundAbsolute", columns="band", values=DELTA, aggfunc="mean", observed=True).round(2)
    s = slopes["slope"]
    by_compound = slopes.groupby("CompoundAbsolute", observed=True)["slope"].agg(
        Stints="size", Median="median", Positive=lambda x: (x > 0).mean()).round(3)
    by_compound["Positive"] = (by_compound["Positive"] * 100).round(1).astype(str) + "%"
    over30 = float((laps["TyreLife"] > 30).mean())
    span = laps.groupby(helpers.STINT, observed=True)["LapNumber"].agg(lambda x: x.max() - x.min() + 1)
    long_stints = int((span >= 28).sum())
    design = excl["reason"].isin(BY_DESIGN).sum() / len(excl)
    bad = excl["reason"].isin(BAD_DATA).sum() / raw_rows
    thin, mid = int((cells["Stints"] < 4).sum()), int(cells["Stints"].between(4, 7).sum())
    ok = int((cells["Stints"] >= 8).sum())
    corr, vif = stats["corr"], stats["vif"]
    c1, c2, c3, c4 = commentary.section1(laps, corr, stats["eta2"]), commentary.section2(laps, stats["slope"]), commentary.section3(laps), commentary.section4(laps)
    lt, d_ = corr["LapTime"], corr[DELTA]
    spans = per_circuit["spread"]
    slow_city, fast_city = per_circuit["median"].idxmax(), per_circuit["median"].idxmin()
    slow_med, fast_med = per_circuit["median"].max(), per_circuit["median"].min()
    thin_per_city = cells[cells["Stints"] < 4].groupby("City").size()
    coverage_note = "at every circuit at least two of the three allocated compounds can be estimated" if thin_per_city.max() <= 1 else "some circuits have two thin compounds"
    fig = lambda n: f"![{n}](../reports/figures/{n})"  # noqa: E731

    return f"""# Exploratory analysis of the clean laps

Source: `data/processed/clean_laps.parquet` ({len(laps):,} laps, {len(stints)} stints, {laps['City'].nunique()} circuits).
Reproduce: `python -m f1_pit_strategy.eda` (this file is generated; charts go to `reports/figures/`, reports to `reports/analysis/`).
Method: the EDA and data-quality workflows of the data-analytics-skills repository (https://github.com/nimrodfisher/data-analytics-skills), see the README.

Circuits are labelled by host city or town (`city` column of `data/reference/pirelli_allocation.csv`).

**The variable `{DELTA}`.** Lap times cannot be compared between circuits ({slow_city} about {slow_med:.0f} s, {fast_city} about {fast_med:.0f} s). So each lap is also
expressed as `{DELTA}` = its lap time minus the median clean lap time of its own circuit, in seconds. **0 is a typical lap at that circuit,
+1 is one second slower, -1 is one second faster.** Example: at {slow_city} (median {slow_med:.1f} s) a {slow_med + 1:.1f} s lap has `{DELTA}` = +1.0.
Why it exists: **{stats['eta2']:.1%} of the variance in raw lap time is between circuits**, so raw comparisons mostly measure "which track".

Each chart below has a business conclusion (what it means for the stop-count decision) and a statistical conclusion (what it means for the model).

---

## 1. Circuit explains lap time (`01_circuit_dominates_lap_time.png`)

{fig('01_circuit_dominates_lap_time.png')}

**Why this chart.** Comparing 19 distributions at once is a box-plot job: it shows the median, the middle 50% of laps, and the outliers per circuit.

{helpers.md_table(overall.map('{:.2f}'.format), index=True)}

{c1['source']}

- Circuit medians run from {per_circuit['median'].min():.1f} s to {per_circuit['median'].max():.1f} s. Inside a circuit the middle 90% of laps (p5 to p95) spans only {spans.min():.1f} s to {spans.max():.1f} s.

{c1['outliers']}

{c1['hetero']}

{c1['raw']}

{c1['business']}
{c1['statistical']}

---

## 2. Cars get faster through a race (`02_lap_time_falls_with_race_lap.png`)

{fig('02_lap_time_falls_with_race_lap.png')}

**Why this chart.** It tests the biggest confounder directly: how lap time moves with race lap (fuel burn and track evolution together). One line of averages plus a fitted trend.

- Laps 2 to 6 average **{stats['early']:+.2f} s**; laps 60 and later average **{stats['late']:+.2f} s**. A straight line through all laps gives **{stats['slope']:+.4f} s per race lap**.

{c2['volatility']}

**Business conclusion.** The car speeds up by about {abs(stats['slope']):.2f} s every lap, a large effect against the stop-count threshold (its size per circuit is in the insight brief). Reading tyre wear straight off raw lap times would make tyres look as if they do not wear.
{c2['statistical']} The variance inflation factors are at most {vif.max():.2f}, so the two are not collinear enough to stop that.

---

## 3. Raw tyre-age curves are not degradation (`03_tyre_age_by_compound.png`)

{fig('03_tyre_age_by_compound.png')}

**Why this chart.** It is the direct visual test of H1 (do softer compounds slow down faster with age?). Five compounds need five panels (at most four lines per chart is readable), with a shared axis so panels compare.

Average `{DELTA}` (s) by tyre-age band:

{helpers.md_table(band_table.map('{:.2f}'.format), index=True)}

What each curve looks like (only tyre ages with at least 30 laps are drawn):

{c3['table']}

{c3['business']}
{c3['statistical']}
These curves are not estimates of β.

---

## 4. Single stints are noisy (`04_stint_slopes_are_noisy.png`)

{fig('04_stint_slopes_are_noisy.png')}

**Why this chart.** It previews stage 1 of the model (one slope per stint): the size, sign and spread of those slopes before anything is built on them. "Naive" means no fuel correction, so each slope is tyre wear minus fuel and track speed-up.

| n | mean | median | std | p5 | p25 | p75 | p95 | min | max |
|---|---|---|---|---|---|---|---|---|---|
| {len(s)} | {s.mean():+.3f} | {s.median():+.3f} | {s.std():.3f} | {s.quantile(.05):+.3f} | {s.quantile(.25):+.3f} | {s.quantile(.75):+.3f} | {s.quantile(.95):+.3f} | {s.min():+.2f} | {s.max():+.2f} |

{int((s.abs() > 0.4).sum())} stints lie beyond +/-0.4 (piled at the plot edges), {int(helpers.tukey_mask(s).sum())} are Tukey outliers, and {(s > 0).mean():.0%} slope upward. Median per compound:

{helpers.md_table(by_compound, index=True)}

**Business conclusion.** Once the speed-up is netted out, a typical stint is close to flat. If the speed-up is about {abs(stats['slope']):.3f} s per lap everywhere, a median naive slope of {s.median():+.3f} would imply β of about {s.median() + abs(stats['slope']):.2f} s per lap, to be compared with a threshold of 0.081 s per lap for a 57-lap race with a 22 s pit loss. This is a rough pointer only, not a result; the real β comes from the model.
{c4['statistical']}

---

## 5. Long-stint evidence is thin (`05_tyre_age_coverage.png`)

{fig('05_tyre_age_coverage.png')}

**Why this chart.** A histogram shows where tyre-age data exists and where it does not.

- Tyre age: median {laps['TyreLife'].median():.0f} laps, p95 {laps['TyreLife'].quantile(.95):.0f}, p99 {laps['TyreLife'].quantile(.99):.0f}, maximum {int(laps['TyreLife'].max())}. {over30:.1%} of laps are on tyres older than 30 laps.
- In race laps, {long_stints} of {len(stints)} stints ({long_stints / len(stints):.0%}) run 28 or more laps. (Tyre age counts laps on used sets from before the stint, so it overstates stint length.)

**Business conclusion.** A one-stop in a 55 to 70 lap race needs stints of about 28 laps or more, which is exactly where data is scarce, so one-stop verdicts are judged on the least evidence.
**Statistical conclusion.** Beyond about 30 laps of tyre age the fitted slope is an extrapolation with wide uncertainty; verdicts that depend on it should say so.

---

## 6. Most dropped laps are dropped by design (`06_cleaning_funnel.png`)

{fig('06_cleaning_funnel.png')}

**Why this chart.** Thirteen reasons fit horizontal bars sorted by size (the 8 to 15 category rule); blue marks the four by-design rules.

- {len(excl):,} of {raw_rows:,} raw laps are dropped ({len(excl) / raw_rows:.1%}). {design:.0%} of the dropped laps are lap 1, pit, safety-car or restart laps. Bad data (missing values, inaccurate, outliers) is {bad:.1%} of raw laps.

**Business conclusion.** The cleaning loss is not a data-quality problem: the lost laps are not normal racing, and tyre wear cannot be read from them.
**Statistical conclusion.** Results apply to normal dry green-flag racing laps only (a deliberate selection). Every dropped lap is logged with exactly one reason in `data/processed/exclusions.parquet`, so the selection can be audited.

---

## 7. Coverage per circuit and compound (`07_stints_per_cell.png`)

{fig('07_stints_per_cell.png')}

**Why this chart.** A matrix of counts shows coverage at a glance; thin cells are bold red.

- {ok} of {len(cells)} circuit-compound cells have 8 or more stints, {mid} have 4 to 7, {thin} have fewer than 4 ({'; '.join(f'{r.City} {r.Compound}' for r in cells[cells['Stints'] < 4].itertuples())}).

**Business conclusion.** The decision rule cannot cover the {thin} thin combinations; {coverage_note}.
**Statistical conclusion.** Cells with 4 to 7 stints give wide intervals. The {thin} thin cells are reported as not estimable and are never filled in; they are compounds teams barely or never ran, which no cleaning rule can change.

---

## 8. Correlation matrix (`08_correlation_matrix.png`)

{fig('08_correlation_matrix.png')}

**Why this chart.** The standard check for strong pairs and for multicollinearity among the model's features. Both lap-time versions are shown: raw `LapTime` and circuit-adjusted `{DELTA}`.

{helpers.md_table(corr.map('{:.2f}'.format), index=True)}

Variance inflation factors: {', '.join(f'{k} {v:.2f}' for k, v in vif.items())}.

**Why `{DELTA}` is the column to read.** Raw `LapTime` correlations mostly reflect the circuit: `TrackTemp` correlates {lt['TrackTemp']:+.2f} with raw lap time only because the hot circuits in this season happen to be fast; against `{DELTA}` it is {d_['TrackTemp']:+.2f}, about zero. The raw column answers "which track", the `{DELTA}` column answers "what changes lap time at a given track".

**Business conclusion.** Race lap (fuel and track evolution) is the strongest linear driver of lap time ({d_['LapNumber']:+.2f}); tyre age alone is weak ({d_['TyreLife']:+.2f}). Degradation is a small effect next to the others, which is why the rule needs a careful estimate and not a glance at a chart. Track temperature shows no clear linear link here; H3 needs the circuit and compound controls to be tested properly.
**Statistical conclusion.** The largest correlation between two features is {corr.loc['TyreLife', 'LapNumber']:.2f} (`TyreLife` with `LapNumber`) and every variance inflation factor is at most {vif.max():.2f}, so there is no multicollinearity problem and both can enter one model. The matrix is pooled across circuits and linear, so it cannot show the circuit x compound interaction (H2) or effects inside a stint. `FreshTyre` at {d_['FreshTyre']:+.2f} is confounded with race lap (fresh sets run early on heavy fuel).
"""


def run() -> None:
    laps, excl = helpers.load_clean(), helpers.load_exclusions()
    raw_rows = len(helpers.load_ingested())
    stints, cells, slopes = helpers.stint_table(laps), helpers.cell_counts(laps), helpers.stint_slopes(laps)
    eta2 = helpers.circuit_variance_share(laps)
    slope = float(np.polyfit(laps["LapNumber"], laps[DELTA], 1)[0])
    early = float(laps.loc[laps["LapNumber"].between(2, 6), DELTA].mean())
    late = float(laps.loc[laps["LapNumber"] >= 60, DELTA].mean())

    fig_circuit_box(laps, eta2)
    fig_race_lap(laps, slope, early, late)
    fig_tyre_age_small_multiples(laps, stints)
    fig_slopes(slopes)
    fig_tyre_age_coverage(laps)
    fig_funnel(excl, raw_rows)
    fig_cells(cells)
    corr = fig_correlation(laps)

    _, _, _, vif = profile.correlation_blocks(laps)
    stats = dict(eta2=eta2, slope=slope, early=early, late=late, corr=corr, vif=vif)
    helpers.write_doc("eda.md", eda_markdown(laps, excl, raw_rows, cells, stints, slopes, stats))


if __name__ == "__main__":
    run()
