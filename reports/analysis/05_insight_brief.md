# 05. Insight brief (workflows: insight-synthesis, impact-quantification, technical-to-business-translator, executive-summary-generator)

**Topic:** what the cleaned 2026 lap data can and cannot say about one-stop versus two-stop strategy.
**Author:** Claude with the project author. **Date:** 2026-11-19.
**Audience:** the project author, and a reviewer judging the project (data analyst or strategy-minded reader).

## Executive summary

**Situation.** The project asks, circuit by circuit, whether two stops beat one: two stops win when tyre degradation `beta`
exceeds `12P / N^2`. Before estimating `beta`, the 2026 lap data was cleaned and profiled.

**Key insights**
1. Fuel burn and track evolution speed cars up by 0.037 s per race lap, as large as 27% to 84% of the stop-count threshold (at the example pit loss); ignoring it could flip stop-count decisions.
2. The circuit explains 98% of lap-time variance, so all estimates must be made within a circuit.
3. 45 of 57 circuit-compound pairs have 8 or more stints; 7 cannot be estimated.

**Recommendations.** Keep race lap in the model (expected outcome: degradation is no longer masked); declare the 7 thin pairs not estimable;
flag one-stop verdicts that depend on tyre ages beyond 30 laps.

**Decision needed.** Confirm that the project proceeds to pit-lane loss and the model on the current data, with the 25% wet cutoff kept
as the default and the traffic filter left to v2. No extra resources are needed.

## Governing insight
The clean data can support per-circuit degradation estimates for 45 of 57 circuit-compound pairs, provided the model first
removes a fuel-and-track speed-up of about 0.037 s per race lap that is large next to the decision threshold.

## Supporting insights (ranked; top five)

### 1. Fuel burn and track evolution hide tyre wear
- **Finding:** Cars get 0.037 s per lap faster as the race goes on, so lap time falls with tyre age in the raw data.
- **Why it matters (so what):** A model that leaves race lap out would report that tyres do not degrade, and every circuit would get the wrong stop count.
- **Why it happens:** Tyre age and race lap rise together inside a stint; fuel is burned and the track rubbers in, which outweighs wear.
- **Action (now what):** Keep race lap in the model and estimate degradation from stints that start at different laps.
- **Impact:** The effect equals 27% to 84% of the stop-count threshold across the 19 circuits (at the example pit loss of 22 s), so ignoring it could flip decisions.
- **Confidence:** High: 15,206 laps, same sign in every analysis.
- **In plain words:** The car gets lighter as fuel burns, so it speeds up and hides how much the tyres slow it.
- **Score:** impact 3, confidence 3, actionability 3 = 9 of 9

### 2. The circuit decides lap time, not the tyre
- **Finding:** 97.9% of lap-time variance is between circuits; medians run from 73 s to 112 s.
- **Why it matters (so what):** Comparing laps across circuits mostly compares tracks, so every estimate must be made inside a circuit.
- **Why it happens:** Track length and layout differ by far more than any tyre effect.
- **Action (now what):** Measure lap time against each circuit's own median, or give the model a circuit term.
- **Impact:** Without it, almost all of the variation the model sees would be circuit noise.
- **Confidence:** High: variance split computed on all clean laps.
- **In plain words:** A lap at Spa takes about 39 seconds longer than at Spielberg, so we only compare a track with itself.
- **Score:** impact 3, confidence 3, actionability 3 = 9 of 9

### 3. Seven circuit-compound pairs cannot be estimated
- **Finding:** 7 of 57 circuit-compound cells have fewer than 4 stints and 5 more have only 4 to 7.
- **Why it matters (so what):** The decision rule has no evidence for 12% of the compound choices at the circuits where they were barely used.
- **Why it happens:** Teams chose other compounds at those races; six of the seven are the C3 compound.
- **Action (now what):** Report them as not estimable instead of filling them in.
- **Impact:** 7 cells (12%) drop out; all circuits keep at least two estimable compounds.
- **Confidence:** High: counted directly.
- **In plain words:** For a few tyre choices at a few tracks, almost nobody drove them, so we cannot say how they wear.
- **Score:** impact 2, confidence 3, actionability 3 = 8 of 9

### 4. Single stints are too noisy to read alone
- **Finding:** Per-stint slopes have a standard deviation of 0.127 s per lap against a median of +0.007, and 56% slope upward.
- **Why it matters (so what):** A conclusion drawn from one stint is mostly noise; only pooled estimates are usable.
- **Why it happens:** Few laps per stint, traffic, and tyre-management choices add variation.
- **Action (now what):** Pool stints and weight them by their precision in stage 2 of the model.
- **Impact:** Pooling is needed for every one of the 854 stints.
- **Confidence:** High: distribution computed on all stints.
- **In plain words:** One stint can look flat or steep by chance, so we average many of them.
- **Score:** impact 2, confidence 3, actionability 3 = 8 of 9

### 5. One-stop evidence is the thinnest
- **Finding:** Only 8.8% of laps are on tyres older than 30 laps, and only 179 of 854 stints run 28 or more race laps.
- **Why it matters (so what):** A one-stop in a 57-lap race needs stints of about 28 laps or more, which is where the data runs out.
- **Why it happens:** Most teams stop before 30 laps, so long-stint behaviour is rarely observed.
- **Action (now what):** Show wider intervals beyond 30 laps and flag any one-stop verdict that relies on extrapolation.
- **Impact:** 179 stints (21% of all) carry the evidence for the longest stints; tyre age counts laps on used sets from before the stint, so it overstates stint length.
- **Confidence:** Medium: depends on how wear behaves beyond the observed range.
- **In plain words:** We have seen few long runs on one set of tyres, so claims about very long runs are less certain.
- **Score:** impact 3, confidence 2, actionability 2 = 7 of 9


Also noted (lower priority): Data quality is good; most loss is by design (6 of 9); Mexico City data stops at lap 56 of 71 (6 of 9).

| Insight | Impact | Confidence | Actionability | Total (of 9) |
|---|---|---|---|---|
| Fuel burn and track evolution hide tyre wear | 3 | 3 | 3 | 9 |
| The circuit decides lap time, not the tyre | 3 | 3 | 3 | 9 |
| Seven circuit-compound pairs cannot be estimated | 2 | 3 | 3 | 8 |
| Single stints are too noisy to read alone | 2 | 3 | 3 | 8 |
| One-stop evidence is the thinnest | 3 | 2 | 2 | 7 |
| Data quality is good; most loss is by design | 2 | 3 | 1 | 6 |
| Mexico City data stops at lap 56 of 71 | 1 | 3 | 2 | 6 |

## Impact estimate: how big is the fuel-and-track effect against the decision threshold?

**Baseline.** The threshold for equal stint splits is `12P / N^2`. `N` is each circuit's race distance (from the data).
`P`, the pit-lane loss, is **not measured yet**: 22 s is the scope document's example, and 18 s and 26 s are our assumed range.

**Estimate.** The fuel-and-track effect is 0.0366 s per lap (naive 95% interval 0.0353 to 0.0380; the interval is too narrow because laps of
one driver in one race are not independent). If a model ignored it, it would understate `beta` by about that amount.

| Circuit | Race laps N | Threshold at P=22 (s/lap) | Fuel effect as % of threshold, P=26 | P=22 | P=18 |
|---|---|---|---|---|---|
| Spa | 44 | 0.136 | 23% | 27% | 33% |
| Baku | 51 | 0.101 | 31% | 36% | 44% |
| Silverstone | 52 | 0.098 | 32% | 37% | 46% |
| Monza | 53 | 0.094 | 33% | 39% | 48% |
| Suzuka | 53 | 0.094 | 33% | 39% | 48% |
| Kuala Lumpur | 55 | 0.087 | 35% | 42% | 51% |
| Austin | 56 | 0.084 | 37% | 43% | 53% |
| Shanghai | 56 | 0.084 | 37% | 43% | 53% |
| Miami | 57 | 0.081 | 38% | 45% | 55% |
| Madrid | 57 | 0.081 | 38% | 45% | 55% |
| Melbourne | 58 | 0.078 | 39% | 47% | 57% |
| Singapore | 62 | 0.069 | 45% | 53% | 65% |
| Barcelona | 66 | 0.061 | 51% | 60% | 74% |
| Montréal | 68 | 0.057 | 54% | 64% | 78% |
| Budapest | 70 | 0.054 | 57% | 68% | 83% |
| Mexico City | 71 | 0.052 | 59% | 70% | 85% |
| Spielberg | 71 | 0.052 | 59% | 70% | 85% |
| Zandvoort | 72 | 0.051 | 61% | 72% | 88% |
| Monaco | 78 | 0.043 | 71% | 84% | 103% |

**Range.** At the example pit loss (22 s) the effect is 27% to 84% of the threshold across circuits. At P = 26 s the shares are lower and at P = 18 s higher, as the table shows.
**Sensitivity.** The share scales with `N^2 / P`: long races are most exposed because their threshold is smallest (Monaco, 78 laps: 84%), short races least (Spa, 44 laps: 27%).
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
| Estimate pit-lane loss `P` per circuit from the in-laps and out-laps in the audit table | High | Analyst | before the model |
| Build stage 1 (slope per stint with shared race lap) and stage 2 (weighted regression) | High | Analyst | after `P` |
| Mark the 7 thin cells not estimable in every output | High | Analyst | with the model |
| Add the traffic filter and compare slopes | Low | Analyst | v2 |

## Plain-language note
Each insight has an "In plain words" line; terms such as variance, slope and confidence interval are explained inline.

## Links
Full analysis: reports 01 to 04 in `reports/analysis/` and the charts in `docs/eda.md`. Data: `data/processed/clean_laps.parquet`.
