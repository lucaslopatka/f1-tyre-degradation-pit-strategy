"""Turns the findings into a ranked insight brief (workflows: insight-synthesis, impact-quantification,
technical-to-business-translator, executive-summary-generator).

Process: list findings, ask So what / Why / Now what, quantify impact
with a range, score impact, confidence and actionability from 1 to 3, lead with the
highest total, keep the top five, write an executive summary.

Writes reports/analysis/05_insight_brief.md.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm

from f1_pit_strategy.eda import helpers, settings


def fuel_effect(laps: pd.DataFrame) -> tuple[float, float, float]:
    """Slope of circuit-adjusted lap time on race lap, with a naive 95% interval."""
    fit = sm.OLS(laps["LapTimeDelta"], sm.add_constant(laps["LapNumber"].astype(float))).fit()
    low, high = fit.conf_int().loc["LapNumber"]
    return float(fit.params["LapNumber"]), float(low), float(high)


def threshold_table(laps: pd.DataFrame, bias: float) -> pd.DataFrame:
    """Closed-form threshold 12P/N^2 per circuit, and the fuel effect as a share of it.

    P is NOT measured yet: 22 s is the scope document's example, 18 and 26 are a
    plausible range. The table sizes the risk of ignoring the fuel effect; it is not a result.
    """
    n = laps.groupby("City", observed=True)["TotalLaps"].first().sort_values()
    rows = []
    for city, laps_in_race in n.items():
        t = {p: 12 * p / laps_in_race ** 2 for p in (settings.PIT_LOSS_LOW, settings.PIT_LOSS_BASE, settings.PIT_LOSS_HIGH)}
        rows.append((city, int(laps_in_race), round(t[settings.PIT_LOSS_BASE], 3),
                     f"{bias / t[settings.PIT_LOSS_HIGH]:.0%}", f"{bias / t[settings.PIT_LOSS_BASE]:.0%}", f"{bias / t[settings.PIT_LOSS_LOW]:.0%}"))
    return pd.DataFrame(rows, columns=["Circuit", "Race laps N", "Threshold at P=22 (s/lap)",
                                       "Fuel effect as % of threshold, P=26", "P=22", "P=18"])


def build_insights(laps, excl, cells, slopes, stints, eta2, bias, share_design, bad_share, share_range) -> list[dict]:
    over30 = float((laps["TyreLife"] > 30).mean())
    # Stint length = race laps from first to last clean lap. TyreLife is not used here: a used set
    # carries laps from before the stint, which would overstate how long the stint ran.
    span = laps.groupby(helpers.STINT, observed=True)["LapNumber"].agg(lambda s: s.max() - s.min() + 1)
    long_stints = int((span >= 28).sum())
    thin, mid = int((cells["Stints"] < 4).sum()), int(cells["Stints"].between(4, 7).sum())
    s = slopes["slope"]
    return [
        dict(name="Fuel burn and track evolution hide tyre wear",
             finding=f"Cars get {bias:.3f} s per lap faster as the race goes on, so lap time falls with tyre age in the raw data.",
             so_what="A model that leaves race lap out would report that tyres do not degrade, and every circuit would get the wrong stop count.",
             why="Tyre age and race lap rise together inside a stint; fuel is burned and the track rubbers in, which outweighs wear.",
             now_what="Keep race lap in the model and estimate degradation from stints that start at different laps.",
             impact=f"The effect equals {share_range} of the stop-count threshold across the 19 circuits (at the example pit loss of 22 s), so ignoring it could flip decisions.",
             confidence="High: 15,206 laps, same sign in every analysis.", scores=(3, 3, 3), plain="The car gets lighter as fuel burns, so it speeds up and hides how much the tyres slow it."),
        dict(name="The circuit decides lap time, not the tyre",
             finding=f"{eta2:.1%} of lap-time variance is between circuits; medians run from 73 s to 112 s.",
             so_what="Comparing laps across circuits mostly compares tracks, so every estimate must be made inside a circuit.",
             why="Track length and layout differ by far more than any tyre effect.",
             now_what="Measure lap time against each circuit's own median, or give the model a circuit term.",
             impact="Without it, almost all of the variation the model sees would be circuit noise.",
             confidence="High: variance split computed on all clean laps.", scores=(3, 3, 3), plain="A lap at Spa takes about 39 seconds longer than at Spielberg, so we only compare a track with itself."),
        dict(name="Seven circuit-compound pairs cannot be estimated",
             finding=f"{thin} of {len(cells)} circuit-compound cells have fewer than 4 stints and {mid} more have only 4 to 7.",
             so_what=f"The decision rule has no evidence for {thin / len(cells):.0%} of the compound choices at the circuits where they were barely used.",
             why="Teams chose other compounds at those races; six of the seven are the C3 compound.",
             now_what="Report them as not estimable instead of filling them in.",
             impact=f"{thin} cells ({thin / len(cells):.0%}) drop out; all circuits keep at least two estimable compounds.",
             confidence="High: counted directly.", scores=(2, 3, 3), plain="For a few tyre choices at a few tracks, almost nobody drove them, so we cannot say how they wear."),
        dict(name="One-stop evidence is the thinnest",
             finding=f"Only {over30:.1%} of laps are on tyres older than 30 laps, and only {long_stints} of {len(stints)} stints run 28 or more race laps.",
             so_what="A one-stop in a 57-lap race needs stints of about 28 laps or more, which is where the data runs out.",
             why="Most teams stop before 30 laps, so long-stint behaviour is rarely observed.",
             now_what="Show wider intervals beyond 30 laps and flag any one-stop verdict that relies on extrapolation.",
             impact=f"{long_stints} stints ({long_stints / len(stints):.0%} of all) carry the evidence for the longest stints; tyre age counts laps on used sets from before the stint, so it overstates stint length.",
             confidence="Medium: depends on how wear behaves beyond the observed range.", scores=(3, 2, 2), plain="We have seen few long runs on one set of tyres, so claims about very long runs are less certain."),
        dict(name="Single stints are too noisy to read alone",
             finding=f"Per-stint slopes have a standard deviation of {s.std():.3f} s per lap against a median of {s.median():+.3f}, and {(s > 0).mean():.0%} slope upward.",
             so_what="A conclusion drawn from one stint is mostly noise; only pooled estimates are usable.",
             why="Few laps per stint, traffic, and tyre-management choices add variation.",
             now_what="Pool stints and weight them by their precision in stage 2 of the model.",
             impact="Pooling is needed for every one of the 854 stints.",
             confidence="High: distribution computed on all stints.", scores=(2, 3, 3), plain="One stint can look flat or steep by chance, so we average many of them."),
        dict(name="Data quality is good; most loss is by design",
             finding=f"{len(excl) / (len(laps) + len(excl)):.1%} of laps were removed, {share_design:.0%} of those by design; bad data is only {bad_share:.1%} of raw laps.",
             so_what="The size of the cleaning loss is not a warning sign.",
             why="Pit, lap-1, safety-car and restart laps are not normal racing.",
             now_what="Proceed to modelling.", impact="No rework needed.", confidence="High: every count reconciles (report 01).",
             scores=(2, 3, 1), plain="We threw away mostly laps that are not normal racing, not faulty data."),
        dict(name="Mexico City data stops at lap 56 of 71",
             finding="The API returned no laps after 56; clean tyre ages stop near 43 laps.",
             so_what="Its slope would be extrapolated for a full-distance strategy.",
             why="Source feed issue; cause unknown.",
             now_what="State it as a limitation; retry the download only if Mexico City becomes decisive.",
             impact="1 of 19 circuits, with no C3 stints either.", confidence="High: checked against race results.", scores=(1, 3, 2),
             plain="One race is missing its last 15 laps."),
    ]


def run() -> None:
    laps, excl = helpers.load_clean(), helpers.load_exclusions()
    raw_rows = len(helpers.load_ingested())
    stints, cells, slopes = helpers.stint_table(laps), helpers.cell_counts(laps), helpers.stint_slopes(laps)
    slope, low, high = fuel_effect(laps)
    bias = abs(slope)
    within = laps.groupby("Round")["LapTime"].apply(lambda s: ((s - s.mean()) ** 2).sum()).sum()
    eta2 = 1 - within / ((laps["LapTime"] - laps["LapTime"].mean()) ** 2).sum()
    by_design = excl["reason"].isin(["lap_1", "in_or_out_lap", "not_green", "after_non_green"]).sum() / len(excl)
    bad = excl["reason"].isin(["missing_laptime", "not_accurate", "missing_compound", "missing_tyrelife", "bad_track_temp", "slow_outlier"]).sum() / raw_rows
    thresholds = threshold_table(laps, bias)
    n_laps = laps.groupby("City", observed=True)["TotalLaps"].first()
    share22 = bias / (12 * settings.PIT_LOSS_BASE / n_laps ** 2)
    share_range = f"{share22.min():.0%} to {share22.max():.0%}"
    insights = build_insights(laps, excl, cells, slopes, stints, eta2, bias, by_design, bad, share_range)
    for i in insights:
        i["total"] = sum(i["scores"])
    ranked = sorted(insights, key=lambda i: (-i["total"], -i["scores"][0]))
    top, rest = ranked[:5], ranked[5:]

    def block(n: int, i: dict) -> str:
        a, b, c = i["scores"]
        return f"""### {n}. {i['name']}
- **Finding:** {i['finding']}
- **Why it matters (so what):** {i['so_what']}
- **Why it happens:** {i['why']}
- **Action (now what):** {i['now_what']}
- **Impact:** {i['impact']}
- **Confidence:** {i['confidence']}
- **In plain words:** {i['plain']}
- **Score:** impact {a}, confidence {b}, actionability {c} = {i['total']} of 9
"""

    score_table = pd.DataFrame([(i["name"], *i["scores"], i["total"]) for i in ranked],
                               columns=["Insight", "Impact", "Confidence", "Actionability", "Total (of 9)"])
    text = f"""# 05. Insight brief (workflows: insight-synthesis, impact-quantification, technical-to-business-translator, executive-summary-generator)

**Topic:** what the cleaned 2026 lap data can and cannot say about one-stop versus two-stop strategy.
**Author:** Claude with the project author. **Date:** {helpers.today()}.
**Audience:** the project author, and a reviewer judging the project (data analyst or strategy-minded reader).

## Executive summary

**Situation.** The project asks, circuit by circuit, whether two stops beat one: two stops win when tyre degradation `beta`
exceeds `12P / N^2`. Before estimating `beta`, the 2026 lap data was cleaned and profiled.

**Key insights**
1. Fuel burn and track evolution speed cars up by {bias:.3f} s per race lap, as large as {share_range} of the stop-count threshold (at the example pit loss); ignoring it could flip stop-count decisions.
2. The circuit explains {eta2:.0%} of lap-time variance, so all estimates must be made within a circuit.
3. {int((cells['Stints'] >= 8).sum())} of {len(cells)} circuit-compound pairs have 8 or more stints; {int((cells['Stints'] < 4).sum())} cannot be estimated.

**Recommendations.** Keep race lap in the model (expected outcome: degradation is no longer masked); declare the {int((cells['Stints'] < 4).sum())} thin pairs not estimable;
flag one-stop verdicts that depend on tyre ages beyond 30 laps.

**Decision needed.** Confirm that the project proceeds to pit-lane loss and the model on the current data, with the 25% wet cutoff kept
as the default and the traffic filter left to v2. No extra resources are needed.

## Governing insight
The clean data can support per-circuit degradation estimates for {int((cells['Stints'] >= 8).sum())} of {len(cells)} circuit-compound pairs, provided the model first
removes a fuel-and-track speed-up of about {bias:.3f} s per race lap that is large next to the decision threshold.

## Supporting insights (ranked; top five)

{chr(10).join(block(n, i) for n, i in enumerate(top, 1))}

Also noted (lower priority): {'; '.join(f"{i['name']} ({i['total']} of 9)" for i in rest) or 'none'}.

{helpers.md_table(score_table)}

## Impact estimate: how big is the fuel-and-track effect against the decision threshold?

**Baseline.** The threshold for equal stint splits is `12P / N^2`. `N` is each circuit's race distance (from the data).
`P`, the pit-lane loss, is **not measured yet**: 22 s is the scope document's example, and 18 s and 26 s are our assumed range.

**Estimate.** The fuel-and-track effect is {bias:.4f} s per lap (naive 95% interval {abs(high):.4f} to {abs(low):.4f}; the interval is too narrow because laps of
one driver in one race are not independent). If a model ignored it, it would understate `beta` by about that amount.

{helpers.md_table(thresholds)}

**Range.** At the example pit loss (22 s) the effect is {share_range} of the threshold across circuits. At P = 26 s the shares are lower and at P = 18 s higher, as the table shows.
**Sensitivity.** The share scales with `N^2 / P`: long races are most exposed because their threshold is smallest ({share22.idxmax()}, {int(n_laps.max())} laps: {share22.max():.0%}), short races least ({share22.idxmin()}, {int(n_laps.min())} laps: {share22.min():.0%}).
**Assumptions to confirm.** `P` per circuit (next project step); that the effect is the same at every circuit (it is pooled here).
**Confidence: medium.** The effect size is well measured; the threshold is illustrative until `P` is estimated.
**Recommended action.** Include race lap in stage 1 and re-run this table with the measured `P`.

## What we do not know
1. The actual degradation `beta` per circuit and compound (the model is not built).
2. The pit-lane loss `P` per circuit.
3. How much dirty air inflates slopes (the traffic filter is deferred).

## Prioritisation rationale
Insights were scored 1 to 3 on impact, confidence and actionability; those with the highest totals that change how the model is built come first.
Findings that only describe data quality rank lower because they need no action.

## Recommended next steps

| Action | Priority | Owner | By |
|---|---|---|---|
| Pit-lane loss `P` per circuit and stage 1 of the model: done (`pit_loss.py`, `degradation.py`, `docs/decision.md`) | Done | Analyst | done |
| Stage 2 (weighted regression of compound slopes, H1 to H3) | High | Analyst | next |
| Keep the {int((cells['Stints'] < 4).sum())} thin cells marked not estimable in every output | High | Analyst | done in the decision table |
| Add the traffic filter and compare slopes | Low | Analyst | v2 |

## Plain-language note
Each insight has an "In plain words" line; terms such as variance, slope and confidence interval are explained inline.

## Links
Full analysis: reports 01 to 04 in `reports/analysis/` and the charts in `docs/eda.md`. Data: `data/processed/clean_laps.parquet`.
"""
    helpers.write_report("05_insight_brief.md", text)
    print(thresholds[["Circuit", "Race laps N", "P=22"]].to_string(index=False))
    print("bias", round(bias, 4), "CI", round(low, 4), round(high, 4), "| top:", [i["name"] for i in top])


if __name__ == "__main__":
    run()
