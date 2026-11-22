"""Stage 2: do the hypotheses H1, H2 and H3 hold? (docs/scope.md sections 4 and 8)

    python -m f1_pit_strategy.stage2

Input: the circuit-compound slopes (Beta) and standard errors (SE) from stage 1 (degradation.py), one row
per cell with at least MIN_CELL_STINTS stints. Every test is an ordinary weighted least squares (WLS)
regression of those slopes with weights = 1 / SE^2, so a cell estimated more precisely in stage 1 counts more:

- H2 (Beta differs between circuits): joint F-test, the model Beta ~ Compound against Beta ~ Compound + Circuit.
- H1 (a softer compound wears faster): Beta ~ Circuit + Softness; Softness must have a positive coefficient.
- H3 (hotter track, more wear): Beta ~ Compound + Temp, with standard errors clustered by circuit because the
  cells of one circuit share a single temperature (only 19 distinct values, not 50). Circuit intercepts cannot
  be used here: temperature is a circuit-level variable and they would absorb it.

statsmodels' WLS treats the weights as known only up to a constant and estimates the residual variance (the
scale). If the scale is above 1, the cells scatter more than their stage-1 standard errors imply, and the
standard errors and F-test widen to match. That is the standard, transparent way to allow for it.

Writes data/processed/stage2_tests.csv, reports/figures/10_degradation_by_cell.png, docs/stage2.md.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats

from f1_pit_strategy import config, degradation
from f1_pit_strategy.eda import helpers

COLORS = dict(zip(helpers.COMPOUNDS, plt.cm.viridis(np.linspace(0.0, 0.9, 5))))


def load_cells() -> pd.DataFrame:
    """Estimable cells with softness (C-number), the WLS weight and the circuit's mean track temperature."""
    cells = pd.read_csv(config.PROCESSED_DIR / "degradation_by_cell.csv")
    cells = cells[cells["Estimable"]].copy()
    cells["Softness"] = cells["Compound"].str[1].astype(int)
    cells["Weight"] = 1 / cells["SE"] ** 2
    laps = pd.read_parquet(config.PROCESSED_DIR / "clean_laps.parquet")
    cells["Temp"] = cells["Round"].map(laps.groupby("Round")["TrackTemp"].mean())
    return cells.reset_index(drop=True)


def wls(formula: str, cells: pd.DataFrame, **fit_options):
    """Weighted least squares with inverse-variance weights."""
    return smf.wls(formula, data=cells, weights=cells["Weight"]).fit(**fit_options)


def one_sided_p(coef: float, p_two: float) -> float:
    """p-value for H: coefficient > 0, from a two-sided p-value."""
    return p_two / 2 if coef > 0 else 1 - p_two / 2


def weight_concentration(cells: pd.DataFrame) -> dict:
    w = cells["Weight"].sort_values(ascending=False)
    return {"ratio": float(w.max() / w.min()), "top5": float(w.head(5).sum() / w.sum()), "effective_n": float(w.sum() ** 2 / (w ** 2).sum())}


def test_h2(cells: pd.DataFrame) -> dict:
    """Do circuit intercepts improve the fit of Beta ~ Compound? Joint F-test on all circuit coefficients."""
    restricted, full = wls("Beta ~ C(Compound)", cells), wls("Beta ~ C(Compound) + C(Round)", cells)
    f_value, p, df_diff = full.compare_f_test(restricted)
    return {"F": float(f_value), "p": float(p), "df_num": int(df_diff), "df_den": int(full.df_resid),
            "rss_restricted": float(restricted.ssr), "rss_full": float(full.ssr),
            "r2_restricted": float(restricted.rsquared), "r2_full": float(full.rsquared),
            "scale_restricted": float(restricted.scale), "scale_full": float(full.scale)}


def test_h1(cells: pd.DataFrame) -> dict:
    """Inside a circuit, does beta rise with softness? (the C-number: soft, medium, hard are consecutive numbers)"""
    res = wls("Beta ~ C(Round) + Softness", cells)
    coef, p_two = float(res.params["Softness"]), float(res.pvalues["Softness"])
    low, high = res.conf_int().loc["Softness"]
    robust = wls("Beta ~ C(Round) + Softness", cells, cov_type="HC3")
    return {"coef": coef, "se": float(res.bse["Softness"]), "low": float(low), "high": float(high), "p_two": p_two,
            "p_one": one_sided_p(coef, p_two), "scale": float(res.scale), "robust_p_two": float(robust.pvalues["Softness"])}


def pair_check(cells: pd.DataFrame) -> dict:
    """Inside each circuit, does the softer compound of every pair have the higher beta?"""
    wins = total = 0
    for _, g in cells.groupby("Round"):
        g = g.sort_values("Softness")
        for i in range(len(g)):
            for j in range(i + 1, len(g)):
                total += 1
                wins += int(g["Beta"].iloc[j] > g["Beta"].iloc[i])
    return {"wins": wins, "pairs": total, "p": float(stats.binomtest(wins, total, 0.5).pvalue)}


def test_h3(cells: pd.DataFrame) -> dict:
    """Beta ~ Compound + Temp. Primary errors are clustered by circuit; the plain WLS result is kept for comparison."""
    plain = wls("Beta ~ C(Compound) + Temp", cells)
    clustered = wls("Beta ~ C(Compound) + Temp", cells, cov_type="cluster", cov_kwds={"groups": cells["Round"].to_numpy()})
    low, high = clustered.conf_int().loc["Temp"]
    return {"coef": float(clustered.params["Temp"]), "se": float(clustered.bse["Temp"]), "low": float(low), "high": float(high),
            "p": float(clustered.pvalues["Temp"]), "plain_se": float(plain.bse["Temp"]), "plain_p": float(plain.pvalues["Temp"]),
            "scale": float(plain.scale)}


def h1_sensitivity(laps: pd.DataFrame) -> pd.DataFrame:
    """Repeat stage 1 and H1 with other tyre-age windows, to see whether warm-up or long-run wear explains the result."""
    rows = []
    for label, sub in [("all laps", laps), ("tyre age 6 or more", laps[laps["TyreLife"] >= 6]),
                       ("tyre age 11 or more", laps[laps["TyreLife"] >= 11]), ("tyre age 20 or less", laps[laps["TyreLife"] <= 20])]:
        cells_all, _ = degradation.run_all(sub)
        c = cells_all[cells_all["Estimable"]].copy()
        c["Softness"], c["Weight"] = c["Compound"].str[1].astype(int), 1 / c["SE"] ** 2
        r = test_h1(c)
        rows.append({"Laps used": label, "Cells": len(c), "Softness effect (s/lap per C-step)": f"{r['coef']:+.4f}",
                     "95% interval": f"{r['low']:+.3f} to {r['high']:+.3f}", "Two-sided p": f"{r['p_two']:.2f}"})
    return pd.DataFrame(rows)


def h1_by_circuit(cells: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """For each circuit with two or more estimable compounds: do the slopes rise from hardest to softest?"""
    rows = []
    for _, g in cells.groupby("Round"):
        g = g.sort_values("Softness")
        if len(g) < 2:
            continue
        step = np.diff(g["Beta"].to_numpy())
        verdict = "rises" if np.all(step > 0) else ("falls" if np.all(step < 0) else "mixed")
        rows.append({"Circuit": g["City"].iloc[0], "Slope by compound, hardest to softest": "  ".join(f"{k} {v:+.3f}" for k, v in zip(g["Compound"], g["Beta"])),
                     "With softness": verdict})
    table = pd.DataFrame(rows)
    return table, table["With softness"].value_counts().to_dict()


def pace_check(laps: pd.DataFrame, cells: pd.DataFrame) -> dict:
    """A second sanity check: is the softest compound faster than the hardest on a fresh tyre?

    Uses each circuit's fitted compound intercepts and slopes: predicted lap time of the softest minus the
    hardest compound at tyre age 5 and 15 (negative = softer is faster).
    """
    diffs = {5: [], 15: []}
    for round_number, sub in laps.groupby("Round"):
        c = cells[cells["Round"] == round_number].sort_values("Softness")
        if len(c) < 2:
            continue
        fit, _ = degradation.fit_circuit(sub)

        def predicted(comp: str, age: int) -> float:
            return fit.params.get(f"C(CompoundAbsolute)[T.{comp}]", 0.0) + fit.params[f"C(CompoundAbsolute)[{comp}]:TyreLife"] * age
        for age in diffs:
            diffs[age].append(predicted(c["Compound"].iloc[-1], age) - predicted(c["Compound"].iloc[0], age))
    return {age: {"faster": int(sum(d < 0 for d in v)), "n": len(v), "median": float(np.median(v))} for age, v in diffs.items()}


def plot_cells(cells: pd.DataFrame, circuits: pd.DataFrame) -> None:
    order = circuits.sort_values("D")["City"].tolist()
    ypos = {city: i for i, city in enumerate(order)}
    fig, ax = plt.subplots(figsize=(9.5, 8.2))
    for comp, g in cells.groupby("Compound"):
        offset = (g["Softness"].to_numpy() - 3) * 0.13
        ax.errorbar(g["Beta"], [ypos[c] for c in g["City"]] + offset, xerr=[g["Beta"] - g["Low"], g["High"] - g["Beta"]], fmt="o", ms=5,
                    color=COLORS[comp], elinewidth=1.2, capsize=0, label=comp)
    ax.axvline(0, color="#444444", lw=0.9)
    ax.set_yticks(range(len(order)), order)
    ax.set_xlabel("Degradation slope beta (s per lap of tyre age), with 95% interval")
    ax.set_title("Degradation differs a lot between circuits, and softer compounds do not wear faster", loc="left", fontsize=12.5, weight="bold")
    ax.legend(title="Compound (C1 hard to C5 soft)", loc="lower right", frameon=False, fontsize=9)
    helpers.style_axes(ax)
    helpers.save_figure(fig, "10_degradation_by_cell.png", f"Source: FastF1 timing 2026, stage 1 model, {len(cells)} circuit-compound cells with at least {config.MIN_CELL_STINTS} stints.")


def markdown(cells, h1, pairs, h2, h3, sens, means, conc, extra) -> str:
    verdict = lambda ok: "Supported" if ok else "Not supported"  # noqa: E731
    pos, ci_pos = int((cells["Beta"] > 0).sum()), int((cells["Low"] > 0).sum())
    table = pd.DataFrame([
        {"Hypothesis": "H1: a softer compound wears faster (beta rises with softness inside a circuit)",
         "Result": f"{h1['coef']:+.4f} s/lap per compound step (SE {h1['se']:.4f}, 95% interval {h1['low']:+.3f} to {h1['high']:+.3f}, two-sided p = {h1['p_two']:.2f}); the softer compound of a pair wears more in {pairs['wins']} of {pairs['pairs']} within-circuit pairs",
         "Verdict": verdict(h1["p_one"] < 0.05 and pairs["wins"] / pairs["pairs"] > 0.5)},
        {"Hypothesis": "H2: beta differs between circuits for the same compound",
         "Result": f"Joint F-test of the circuit terms: F = {h2['F']:.2f} on {h2['df_num']} and {h2['df_den']} degrees of freedom, p = {h2['p']:.1g}; weighted R² rises from {h2['r2_restricted']:.2f} (compound only) to {h2['r2_full']:.2f} (compound + circuit)",
         "Verdict": verdict(h2["p"] < 0.05)},
        {"Hypothesis": "H3: wear rises with track temperature (compound controlled)",
         "Result": f"{h3['coef']:+.4f} s/lap per °C (SE {h3['se']:.4f} clustered by circuit, 95% interval {h3['low']:+.4f} to {h3['high']:+.4f}, p = {h3['p']:.2f}) across {cells['Round'].nunique()} circuits; plain WLS gives p = {h3['plain_p']:.2f}",
         "Verdict": verdict(h3["p"] < 0.05 and h3["coef"] > 0)}])
    return f"""# Stage 2: do the hypotheses hold?

Reproduce: `python -m f1_pit_strategy.stage2` (this file is generated). Data: the {len(cells)} circuit-compound slopes from stage 1 that rest on at least {config.MIN_CELL_STINTS} stints, from {cells['Round'].nunique()} circuits.

**Method.** Every test is an ordinary weighted least squares (WLS) regression of the stage-1 slopes, with weight 1 / SE² per cell, so a slope estimated more precisely counts more. The weights range {conc['ratio']:.0f}-fold, the five most precise cells carry
{conc['top5']:.0%} of the total weight and the effective sample is {conc['effective_n']:.0f} of {len(cells)} cells, so a handful of precise cells drive every result. Standard WLS also estimates a scale (the residual variance after weighting): 1 would mean the stage-1 standard errors explain the
scatter fully; ours are {h2['scale_full']:.1f} to {h2['scale_restricted']:.1f}, so the cells scatter more than their standard errors imply, and the standard errors and the F-test below are widened to match.

## Result

{helpers.md_table(table)}

Beyond the three hypotheses: {pos} of {len(cells)} slopes are positive and {ci_pos} have a 95% interval entirely above zero, so tyres do wear in most circuit-compound cells.

![10_degradation_by_cell.png](../reports/figures/10_degradation_by_cell.png)

## What it means

### H2 holds, and it is the one the project needs
**How it was tested.** Two WLS models are compared. The restricted one explains each slope by its compound alone (`Beta ~ Compound`, {h2['df_den'] + h2['df_num']} residual degrees of freedom, weighted squared error {h2['rss_restricted']:.1f}). The full one adds one intercept per circuit
(`Beta ~ Compound + Circuit`, {h2['df_den']} residual degrees of freedom, weighted squared error {h2['rss_full']:.1f}). The F statistic is the improvement per added circuit parameter divided by the leftover scatter per degree of freedom:
(({h2['rss_restricted']:.1f} - {h2['rss_full']:.1f}) / {h2['df_num']}) / ({h2['rss_full']:.1f} / {h2['df_den']}) = {h2['F']:.2f}, with p = {h2['p']:.1g}. In plain words: compound alone explains {h2['r2_restricted']:.0%} of the weighted variation in slopes, and knowing the circuit raises that to {h2['r2_full']:.0%}.
Example, C3: {extra['hi'].City} {extra['hi'].Beta:.3f} (plus or minus {extra['hi'].SE:.3f}) against {extra['lo'].City} {extra['lo'].Beta:.3f} (plus or minus {extra['lo'].SE:.3f}).

**What it does and does not show.** It is evidence, not proof. The test asks whether differences *between* circuits are large compared with the scatter left *inside* circuits (scale {h2['scale_full']:.1f} in the full model), which is a demanding comparison, and it still rejects clearly.
It tests "circuits differ given compound"; a circuit x compound interaction cannot be tested separately because each circuit-compound pair has one slope. It says circuits differ, not why.
**Consequence.** If we had assumed every circuit wears alike (one rate of about 0.05 s/lap), the rule would call Barcelona and Budapest one-stops, while 89% to 100% of their finishers made two or more stops.

### H1 does not hold, and it is an open problem
**How the test was done.** Inside each circuit we compare the wear slopes of the compounds it ran. A WLS regression gives each circuit its own intercept (so circuit differences drop out) and one coefficient for "one step softer" (`Beta ~ Circuit + Softness`).
If softer tyres wear faster, that coefficient must be positive. It is {h1['coef']:+.4f} s/lap per step (95% interval {h1['low']:+.3f} to {h1['high']:+.3f}): the data rule out a large effect but not a small one. A version with heteroscedasticity-robust errors agrees (p = {h1['robust_p_two']:.2f}).

Circuit by circuit, the slope rises with softness in {extra['counts'].get('rises', 0)} circuits, falls in {extra['counts'].get('falls', 0)} and is mixed in {extra['counts'].get('mixed', 0)}:

{helpers.md_table(extra['h1_table'])}

A second sanity check, pace: on a fresh tyre (age 5) the softest compound is faster than the hardest in {extra['pace'][5]['faster']} of {extra['pace'][5]['n']} circuits, but only by a median {abs(extra['pace'][5]['median']):.2f} s;
at tyre age 15 it is faster in {extra['pace'][15]['faster']} of {extra['pace'][15]['n']}. Softer compounds are normally clearly faster when new, so this is a second mild warning.

**Why it matters.** That softer tyres wear faster is what we know from tyre design and from racing; your scope uses it as a sanity check on the data and the model (section 4). When a check that should pass fails, either the world is surprising or the measurement is off,
and the second is far more likely here. Consequences for the objective:
- The wear rate d might be biased by an amount and in a direction we cannot yet tell. The calls with a wide margin (for example Barcelona, Spielberg, Budapest) are less exposed; the four uncertain calls (Monaco, Zandvoort, Kuala Lumpur, Austin) are the most exposed.
- We cannot say which compound to run in which stint. The rule gives one stop count per circuit, not a compound plan.
- What still supports the calls: the circuit differences are real (H2) and the calls match real stop counts at 10 of 13 circuits (`docs/validation.md`).

**Possible causes (not yet tested).** A straight-line race-lap effect shared by all compounds may be wrong: soft and hard stints are run at different points of the race, so a misfit in how the car speeds up over a race lands on the compound terms.
Drivers may manage soft tyres, which flattens their slope. Wear may not be linear (curvature is still to be tested, scope section 8). Next checks: a flexible race-lap effect, a quadratic tyre-age term, and same-driver comparisons inside one race.

### H3 is not supported, and this test cannot settle it
The result is {h3['coef']:+.4f} s/lap per degree (95% interval {h3['low']:+.4f} to {h3['high']:+.4f}, errors clustered by circuit). Across the {extra['t_range']:.0f} degrees between the coolest and hottest circuit that is anything from {extra['t_range'] * h3['low']:+.2f} to {extra['t_range'] * h3['high']:+.2f} s/lap,
against typical wear of 0.05: the data are uninformative, not evidence that temperature does nothing. Plain WLS gives a smaller p-value ({h3['plain_p']:.2f}) but it treats the {len(cells)} cells as {len(cells)} independent temperature readings, when cells of one circuit share one temperature
(only {cells['Round'].nunique()} distinct values), so its standard error ({h3['plain_se']:.4f}) is too small; the clustered version ({h3['se']:.4f}) is the one to read. Reasons it is hard to see:
- With one race per circuit we compare circuits, and circuits also differ in surface, layout and tyre energy, which swamp temperature with only 19 of them.
- Temperature inside a race moves together with race lap (the track warms or cools as the race goes on), so it cannot be separated within a circuit.
- A circuit's average temperature is coarse, and tyres have an optimal window, so the link need not be a straight line.

**Consequence.** The rule measures each circuit's d directly, so it needs no temperature formula. What it cannot do is predict a hotter or colder race than the one in the data.

## H1 under other tyre-age windows

{helpers.md_table(sens)}

## Limits

- Stage 2 works on estimates, not on laps: stage-1 error reaches it only through the weights, and 50 cells over 19 circuits give limited power, especially for H3 and for C1 (2 cells).
- A few precise cells carry much of the weight (see Method); tests are in-sample and the stage-1 standard errors are approximate, so p-values are guides, not exact.
- Nothing here changes the Tier 1 and Tier 2 calls: d comes from stage 1.
"""


def main() -> None:
    cells = load_cells()
    circuits = pd.read_csv(config.PROCESSED_DIR / "degradation_by_circuit.csv")
    h2, h3, pairs, h1 = test_h2(cells), test_h3(cells), pair_check(cells), test_h1(cells)
    means = {k: float(np.average(g["Beta"], weights=g["Weight"])) for k, g in cells.groupby("Compound")}
    laps_all = degradation.load_laps()
    sens = h1_sensitivity(laps_all)
    c3 = cells[cells["Compound"] == "C3"]
    h1_table, counts = h1_by_circuit(cells)
    extra = {"hi": c3.loc[c3["Beta"].idxmax()], "lo": c3.loc[c3["Beta"].idxmin()], "counts": counts, "h1_table": h1_table,
             "pace": pace_check(laps_all, cells), "t_range": float(cells["Temp"].max() - cells["Temp"].min())}
    pd.DataFrame([{"test": "H1", **h1, **{f"pairs_{k}": v for k, v in pairs.items()}}, {"test": "H2", **h2}, {"test": "H3", **h3}]).to_csv(
        config.PROCESSED_DIR / "stage2_tests.csv", index=False)
    plot_cells(cells, circuits)
    helpers.write_doc("stage2.md", markdown(cells, h1, pairs, h2, h3, sens, means, weight_concentration(cells), extra))
    print(pd.DataFrame([{"H1": h1, "pairs": pairs, "H2": h2, "H3": h3}]).T.to_string())
    print(sens.to_string(index=False))


if __name__ == "__main__":
    main()
