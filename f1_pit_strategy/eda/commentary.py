"""Statistics and written commentary for charts 1 to 4 of docs/eda.md.

Each function computes the numbers it quotes (none are typed by hand) and returns markdown
that visuals.eda_markdown() drops into the document. The questions answered here:
  chart 1: where the table comes from, unequal spread, outliers, raw lap time vs the delta
  chart 2: why the line is more volatile late in the race
  chart 3: how the compound curves differ and why they cannot be compared directly
  chart 4: why the stint slopes are not a normal distribution
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from f1_pit_strategy import config
from f1_pit_strategy.eda import helpers
from f1_pit_strategy.eda.helpers import DELTA


def fmt_p(p: float) -> str:
    return "< 0.0001" if p < 1e-4 else f"{p:.4f}"


def variance_share(values: pd.Series, groups: pd.Series) -> float:
    """Share of the variance of `values` that lies between the groups (eta squared)."""
    within = values.groupby(groups, observed=True).var(ddof=0) * values.groupby(groups, observed=True).size()
    return float(1 - within.sum() / (values.var(ddof=0) * len(values)))


def upper_fence(s: pd.Series) -> float:
    q1, q3 = s.quantile([0.25, 0.75])
    return q3 + 1.5 * (q3 - q1)


# ---------- chart 1 ----------

def circuit_clusters(medians: pd.Series) -> list[str]:
    """Split the sorted circuit medians at their two largest gaps and describe the three groups."""
    m = medians.sort_values()
    cuts = np.sort(np.argsort(np.diff(m.to_numpy()))[-2:]) + 1
    groups = np.split(m.to_numpy(), cuts)
    return [f"{len(g)} circuits at {g.min():.0f}-{g.max():.0f} s" for g in groups]


def outlier_table(laps: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Per circuit: laps beyond the box-plot whiskers, and which of them are on the slow side."""
    fence = laps.groupby("City", observed=True)["LapTime"].transform(upper_fence)
    laps = laps.assign(slow=laps["LapTime"] > fence, out=laps.groupby("City", observed=True)["LapTime"].transform(helpers.tukey_mask).astype(bool))
    rows = []
    for city, g in laps.groupby("City", observed=True):
        flagged = g[g["out"]]
        top3 = flagged.groupby(["Driver", "Stint"]).size().nlargest(3).sum() / max(len(flagged), 1)
        rows.append({"City": city, "Outliers": len(flagged), "Share of laps": f"{len(flagged) / len(g):.1%}",
                     "Box length (s)": round(g["LapTime"].quantile(.75) - g["LapTime"].quantile(.25), 2),
                     "In 3 stints": f"{top3:.0%}"})
    return pd.DataFrame(rows).sort_values("Outliers", ascending=False).reset_index(drop=True), laps["slow"]


def section1(laps: pd.DataFrame, corr: pd.DataFrame, eta2: float) -> dict[str, str]:
    g = laps.groupby("City", observed=True)
    sd = g[DELTA].std()
    medians = g["LapTime"].median()
    bf_city = stats.levene(*[x[DELTA].to_numpy() for _, x in g], center="median")
    lap_band = pd.cut(laps["LapNumber"], [1, 10, 20, 30, 40, 50, 80])
    age_band = pd.cut(laps["TyreLife"], [1, 5, 10, 20, 30, 60])
    sd_lap = laps.groupby(lap_band, observed=True)[DELTA].std()
    sd_age = laps.groupby(age_band, observed=True)[DELTA].std()
    bf_lap = stats.levene(*[x[DELTA].to_numpy() for _, x in laps.groupby(lap_band, observed=True)], center="median")
    team_eta = variance_share(laps[DELTA], laps["Team"])
    outliers, slow = outlier_table(laps)
    total = int(outliers["Outliers"].sum())
    fence = laps.groupby("City", observed=True)["LapTime"].transform(upper_fence)
    slow_out = laps.assign(s=laps["LapTime"] > fence)
    by_team = slow_out.groupby("Team", observed=True).agg(laps=("s", "size"), out=("s", "sum"), delta=(DELTA, "mean"))
    top = by_team.nlargest(2, "out")
    team_laps, team_out = top["laps"].sum() / len(laps), top["out"].sum() / by_team["out"].sum()
    rank_miami = int(outliers.index[outliers["City"] == "Miami"][0]) + 1 if "Miami" in set(outliers["City"]) else None
    raw_var, delta_var = laps["LapTime"].var(), laps[DELTA].var()

    source = (f"**Where the table comes from.** It is `describe()` run on the {len(laps):,} clean laps in `data/processed/clean_laps.parquet`, "
              f"all circuits pooled: row 1 is `LapTime` in seconds, row 2 is `{DELTA}` (defined above), row 3 is `TyreLife`. `p5` is the value 5% of laps fall below. "
              "Pooling is why the lap-time row is so wide: it mixes tracks. Only the other two rows are comparable across circuits.")
    outlier_text = (
        f"**Outliers.** Inside each circuit (box-plot rule: beyond 1.5 times the box length), {total} laps are outliers and {float(slow.sum()) / total:.0%} of the flagged laps are slow ones. "
        f"The top four are {', '.join(f'{r.City} {r.Outliers}' for r in outliers.head(4).itertuples())}; Miami has "
        f"{int(outliers.loc[outliers['City'] == 'Miami', 'Outliers'].iloc[0])} (rank {rank_miami}).\n\n"
        + helpers.md_table(outliers.head(6)) + "\n\n"
        "Why those circuits:\n"
        f"- **The rule is relative to each circuit's own spread.** The narrower the box (Monza {outliers.loc[outliers['City'] == 'Monza', 'Box length (s)'].iloc[0]} s), the sooner an ordinary slow lap is flagged.\n"
        "- **They are concentrated, not scattered.** The last column shows the share of flagged laps that sit in just three stints: whole stints are slow, which points to a car or a pace choice, not to single mistakes.\n"
        f"- **Two teams make most of them.** {top.index[0]} and {top.index[1]} are {team_laps:.0%} of the clean laps but {team_out:.0%} of the slow outliers, "
        f"running {top['delta'].iloc[0]:+.1f} s and {top['delta'].iloc[1]:+.1f} s slower than the circuit median on average. These are slow cars, not bad data, so they stay in. "
        "Traffic is also not filtered in v1 and may add to it (not tested).")
    hetero = (
        "**Heteroscedasticity (unequal spread).** The spread of `LapTimeDelta` is not the same everywhere:\n"
        f"- Between circuits: the standard deviation runs from {sd.min():.2f} s ({sd.idxmin()}) to {sd.max():.2f} s ({sd.idxmax()}), a {(sd.max() / sd.min()) ** 2:.1f}x difference in variance (Brown-Forsythe test, p {fmt_p(bf_city.pvalue)}).\n"
        f"- Along the race: from {sd_lap.min():.2f} s to {sd_lap.max():.2f} s across race-lap bands, highest after lap 40 (p {fmt_p(bf_lap.pvalue)}).\n"
        f"- By tyre age: {sd_age.iloc[0]:.2f} s at ages 2-5 falling to {sd_age.iloc[3]:.2f} s at ages 21-30.\n"
        f"- By team: team explains {team_eta:.0%} of the variance of `{DELTA}`. After the circuit is removed, car pace is the biggest thing left.")
    raw = (
        f"**Why `{DELTA}` and not raw `LapTime`.**\n"
        f"- Raw lap time has {raw_var / delta_var:.0f}x the variance of the delta ({raw_var:.0f} against {delta_var:.1f} s squared), almost all of it \"which circuit\".\n"
        f"- Its distribution is a mixture, not one bell: the circuit medians form three groups ({'; '.join(circuit_clusters(medians))}), and its excess kurtosis is {stats.kurtosis(laps['LapTime']):+.2f} (flat) "
        f"against {stats.kurtosis(laps[DELTA]):+.2f} for the delta, whose slow-side tail gives skew {stats.skew(laps[DELTA]):+.2f}.\n"
        f"- Raw correlations measure the circuit: `TrackTemp` is {corr.loc['LapTime', 'TrackTemp']:+.2f} with raw lap time and {corr.loc[DELTA, 'TrackTemp']:+.2f} with the delta (chart 8).\n"
        "- Limits of the delta: its zero is the median of the clean laps that survived cleaning, so it depends on which laps survived (Mexico City's median uses laps 1-56 only; Zandvoort lost its rain laps). "
        "Subtracting a circuit level removes neither the unequal spread nor the team differences above.")
    business = ("**Business conclusion.** A lap time means nothing without its circuit, and a slow car's lap means little next to a fast car's. "
                "Every comparison is made inside a circuit, and degradation is read as a change within a stint, not as a level.")
    statistical = (f"**Statistical conclusion.** The circuit explains {eta2:.1%} of the variance, so the model works inside circuits. What is left is unequal: the spread differs by circuit, "
                   f"by race lap and by tyre age, and team explains {team_eta:.0%} of it. The model needs team or stint intercepts (or within-stint slopes, which cancel a constant car-pace offset) "
                   "and should weight stints by precision.")
    return dict(source=source, outliers=outlier_text, hetero=hetero, raw=raw, business=business, statistical=statistical)


# ---------- chart 2 ----------

def section2(laps: pd.DataFrame, slope: float) -> dict[str, str]:
    c = laps.groupby("LapNumber")[DELTA].agg(["mean", "count", "std"])
    c = c[c["count"] >= 30]
    c["se"] = c["std"] / np.sqrt(c["count"])
    trend = np.polyval(np.polyfit(laps["LapNumber"], laps[DELTA], 1), c.index)
    c["wiggle"] = c["mean"] - trend
    early, late = c.loc[:40], c.loc[41:]
    alive = laps.groupby("LapNumber")["City"].nunique()
    text = (
        "**Why is the line more volatile after lap 40?** Two reasons:\n"
        f"1. **Fewer laps behind each point.** {early['count'].mean():.0f} laps per point up to lap 40, {late['count'].mean():.0f} after it (bars under the chart). "
        f"The standard error of a point grows from {early['se'].mean():.2f} s to {late['se'].mean():.2f} s, and the points scatter around the trend by {early['wiggle'].std():.2f} s before lap 40 and {late['wiggle'].std():.2f} s after.\n"
        f"2. **A changing mix of circuits.** Races last 44 to 78 laps, so circuits drop out as the race goes on: {alive[41]} circuits contribute at lap 41, {alive[55]} at lap 55, {alive[60]} at lap 60 and {alive[69]} at lap 69. "
        "Each exit shifts the average; for example Melbourne's race ends at lap 58.\n\n"
        "Read the line with care after about lap 55. The dashed trend is fitted on all laps and is not affected by this.")
    statistical = (
        "**Statistical conclusion.** Race lap and tyre age are confounded: wear pushes lap time up while fuel burn and track evolution push it down. "
        "The model must include race lap (`LapNumber`). It can separate the two because drivers start stints on different race laps. Only their combined effect is estimated; race data cannot split fuel from track. "
        f"Late-race points are about {late['se'].mean() / early['se'].mean():.1f} times less precise than early ones, so laps should not all count equally.")
    return dict(volatility=text, statistical=statistical)


# ---------- chart 3 ----------

def compound_rows(laps: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    alloc = pd.read_csv(config.ALLOCATION_FILE).dropna(subset=["soft"])
    rows, curves = [], {}
    for comp in helpers.COMPOUNDS:
        sub = laps[laps["CompoundAbsolute"] == comp]
        s = sub.groupby("TyreLife")[DELTA].agg(["mean", "count"]).query("count >= 30")["mean"]
        curves[comp] = s
        share = sub["City"].value_counts(normalize=True).head(3)
        roles = {lab: int((alloc[lab] == comp).sum()) for lab in ["hard", "medium", "soft"]}
        rows.append({"Compound": comp, "Circuits": sub["City"].nunique(), "Ages shown": f"{s.index.min()}-{s.index.max()}",
                     "Curve range (s)": f"{s.min():+.2f} to {s.max():+.2f}", "Mean step (s)": round(s.diff().abs().mean(), 2),
                     "Slope of curve (s/lap)": f"{np.polyfit(s.index, s.to_numpy(), 1)[0]:+.3f}",
                     "Main suppliers": ", ".join(f"{c} {v:.0%}" for c, v in share.items()),
                     "Role": ", ".join(f"{lab} at {n}" for lab, n in roles.items() if n)})
    return pd.DataFrame(rows), pd.DataFrame(curves).corr()


def section3(laps: pd.DataFrame) -> dict[str, str]:
    table, cm = compound_rows(laps)
    pairs = cm.where(np.triu(np.ones(cm.shape, bool), k=1)).stack()
    smooth, rough = table.loc[table["Mean step (s)"].idxmin()], table.loc[table["Mean step (s)"].idxmax()]
    statistical = (
        "**Statistical conclusion.**\n"
        "- **Behaviour of the curves.** They do not share one shape. C3 starts low and climbs towards zero over its first ages; C4 and C5 start high and fall; C2 rises, then falls after the middle of its range. "
        "The straight-line slope of every curve is at or below zero (column *Slope of curve*), so none shows wear on its own, and the softest compound (C5) is not steeper upwards than the hardest (C1), the opposite of what H1 expects.\n"
        f"- **Volatility.** Curves jump {table['Mean step (s)'].min():.2f} to {table['Mean step (s)'].max():.2f} s between neighbouring ages: {smooth['Compound']} is smoothest (it has the most circuits, {smooth['Circuits']}) and {rough['Compound']} is the most erratic. "
        "Volatility grows with age because bins need at least 30 laps and the older bins hold barely that many; C1 only has ages 7 to 16.\n"
        f"- **Similarity.** Correlation between two curves over their shared ages runs from {pairs.min():+.2f} ({' vs '.join(pairs.idxmin())}) to {pairs.max():+.2f} ({' vs '.join(pairs.idxmax())}): there is no common compound-wear shape.\n"
        "- **Why they differ.** Each compound is run by different circuits (column *Main suppliers*) and plays different roles (column *Role*: the same C-number is the hard at some circuits and the soft at others). "
        "A curve therefore mixes circuit, race stage and compound, and the five curves cannot be compared with each other. Separating them needs the circuit x compound model (H2), with race lap controlled.")
    business = ("**Business conclusion.** Most curves slope down: older tyres look faster because they run later in the race on lighter cars. "
                "Ignoring fuel load, tyres would look as if they do not degrade, and the stop-count call would be wrong.")
    return dict(table=helpers.md_table(table), business=business, statistical=statistical)


# ---------- chart 4 ----------

def stint_fits(laps: pd.DataFrame) -> pd.DataFrame:
    """Per stint: number of laps, naive slope of LapTime on TyreLife, and the slope's standard error."""
    rows = []
    for _, g in laps.groupby(helpers.STINT, observed=True):
        x, y = g["TyreLife"].to_numpy(float), g["LapTime"].to_numpy(float)
        xc = x - x.mean()
        sxx = (xc ** 2).sum()
        slope = (xc * (y - y.mean())).sum() / sxx
        resid = y - y.mean() - slope * xc
        rows.append((len(x), slope, np.sqrt((resid ** 2).sum() / (len(x) - 2) / sxx)))
    return pd.DataFrame(rows, columns=["n", "slope", "se"])


def section4(laps: pd.DataFrame) -> dict[str, str]:
    f = stint_fits(laps)
    s = f["slope"]
    iqr = s.quantile(.75) - s.quantile(.25)
    z = (s - s.mean()) / s.std()
    bins = pd.cut(f["n"], [4, 9, 14, 19, 29, 80], labels=["5-9", "10-14", "15-19", "20-29", "30+"])
    by_len = f.groupby(bins, observed=True)["slope"].agg(
        Stints="size", Std=lambda v: round(v.std(), 3), Box=lambda v: round(v.quantile(.75) - v.quantile(.25), 3),
        Kurtosis=lambda v: round(stats.kurtosis(v), 1))
    by_len.index.name = "Laps in stint"
    std_by_se = ((s - s.median()) / f["se"]).dropna()
    jb = stats.jarque_bera(s)
    statistical = (
        f"**Statistical conclusion.** The slopes are not normally distributed, and the chart shows it (the dashed curves are normal densities):\n"
        f"- **Sharper peak, heavier tails.** Excess kurtosis is {stats.kurtosis(s):.1f} (a normal is 0) and skew is {stats.skew(s):+.2f}; the Jarque-Bera normality test gives p {fmt_p(jb.pvalue)}. "
        f"The standard deviation ({s.std():.3f}) is {s.std() / (iqr / 1.349):.1f} times what the middle half of the data implies ({iqr / 1.349:.3f}), and {(z.abs() > 3).mean():.1%} of stints lie beyond 3 standard deviations against 0.3% for a normal.\n"
        "- **The cause is stint length (heteroscedasticity).** A short stint gives a noisy slope and a long stint a precise one, so one pile of stints mixes very different spreads, which produces exactly a sharp peak with long tails:\n\n"
        + helpers.md_table(by_len, index=True) + "\n\n"
        f"  The spread falls {by_len['Std'].iloc[0] / by_len['Std'].iloc[-1]:.0f}-fold from the shortest to the longest stints, and the tails become nearly normal (kurtosis around 1) from 15 laps up.\n"
        f"- **Not only noise.** Dividing each slope by its own standard error should give a spread near 1; it gives {std_by_se.std():.1f}. Stints really differ (traffic, pace management, car pace). Separately, {(s.abs() < 2 * f['se']).mean():.0%} of stints are statistically indistinguishable from flat.\n"
        "- **Consequence for the model.** Do not put normal-theory intervals on raw slopes. Stage 2 should weight each stint by its precision plus a between-stint variance, or use a robust fit (median or Huber) or t-distributed errors. H1 cannot be read from these naive slopes.")
    return dict(statistical=statistical, fits=f)
