# Validation: do the calls match what teams did?

Reproduce: `python -m f1_pit_strategy.validate` (this file is generated). Needs `decision_summary.csv` (decision layer) and the raw laps.

**Test.** For each of the 13 Tier 1 circuits, count the pit stops of the cars that finished (a finisher's last lap reaches 90% of the race's last lap).
A 1-Stop call agrees if more than half of the finishers made exactly one stop; a 2-Stop call agrees if more than half made two or more.

## Result

| Circuit | Model call | Finishers | 1 stop | 2 stops | 3+ stops | Modal / median | Made the call's count | Stops under SC/VSC/red | Green-flag equivalent | Wet laps | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Barcelona | 2-Stop (clear) | 17 | 0 | 10 | 7 | 2 / 2 | 100% | 15% | 82% | 0% | agrees |
| Spielberg | 2-Stop (clear) | 18 | 0 | 15 | 3 | 2 / 2 | 100% | 18% | 83% | 0% | agrees |
| Budapest | 2-Stop (clear) | 19 | 2 | 12 | 5 | 2 / 2 | 89% | 20% | 74% | 0% | agrees |
| Zandvoort | 2-Stop (uncertain) | 17 | 0 | 1 | 16 | 3 / 3 | 100% | 42% | 82% | 11% | agrees |
| Kuala Lumpur | 2-Stop (uncertain) | 20 | 0 | 1 | 19 | 3 / 3 | 100% | 54% | 40% | 11% | agrees |
| Monaco | 1-Stop (uncertain) | 16 | 0 | 0 | 16 | 5 / 5 | 0% | 78% | 81% | 0% | disagrees, explained by free stops |
| Austin | 1-Stop (uncertain) | 19 | 10 | 9 | 0 | 1 / 1 | 53% | 4% | 58% | 0% | agrees |
| Singapore | 1-Stop (clear) | 19 | 14 | 5 | 0 | 1 / 1 | 74% | 21% | 95% | 0% | agrees |
| Mexico City | 1-Stop (clear) | 18 | 0 | 8 | 10 | 2 / 3 | 0% | 64% | 94% | 0% | disagrees, explained by free stops |
| Silverstone | 1-Stop (clear) | 20 | 0 | 16 | 4 | 2 / 2 | 0% | 59% | 90% | 0% | disagrees, explained by free stops |
| Suzuka | 1-Stop (clear) | 20 | 18 | 1 | 1 | 1 / 1 | 90% | 50% | 95% | 0% | agrees |
| Miami | 1-Stop (clear) | 18 | 16 | 1 | 1 | 1 / 1 | 89% | 10% | 89% | 0% | agrees |
| Madrid | 1-Stop (clear) | 18 | 14 | 4 | 0 | 1 / 1 | 78% | 45% | 89% | 0% | agrees |

`Green-flag equivalent` repeats the comparison after discounting the cheap stops made under a safety car, virtual safety car or red flag (each driver counts max(1, stops under green or yellow)).

**Summary.** The model agrees with the real stop count at 10 of 13 circuits (and 7 of its 9 clear calls).
3 disagree (Monaco, Mexico City, Silverstone); all of them are explained by free stops under safety cars, virtual safety cars and red flags (the green-flag equivalent count then matches the call).

How the model compares with two naive rules (circuits agreeing):

| Rule | On actual stops | On green-flag equivalent stops |
|---|---|---|
| Model | 10 of 13 | 12 of 13 |
| Always 1-Stop | 5 of 13 | 9 of 13 |
| Always 2-Stop | 8 of 13 | 4 of 13 |

## Reading the disagreements

- The model describes a **green-flag** race. Where a safety car, virtual safety car or red flag came, teams took extra, nearly free stops, so the real count is higher than the green-flag optimum. This is the limitation written in the scope (section 10), now measured.
- **Overtaking difficulty (H5) is not tested.** The `circuit_overtaking.csv` table has not been compiled, so no claim is made about it. It stays a hypothesis for the circuits where unexplained gaps remain.
- Zandvoort and Kuala Lumpur had rain laps (11% each), which also pushes stop counts up for reasons the model ignores.
- Mexico City's data stops at lap 56 of 71, so stops after lap 56 are not observed.

## Montréal check: why is d = 0.000?

- **Collinearity is not the cause.** After removing driver and compound effects, tyre age and race lap correlate 0.56 at Montréal (rank 9 of 19, 1 = lowest), and its standard error (0.0045) is the 3rd smallest of 19: the estimate is precise, not unstable.
- **It is not clipped at zero.** The estimates are C4 -0.0025 (se 0.0064), C5 +0.0038 (se 0.0067); one is negative.
- **It is stable.** d stays between -0.0041 and +0.0011 when the model changes (base +0.0001; plus a squared race-lap term -0.0011; laps after 25 only +0.0011; team intercepts -0.0041).
- **Reading.** At Montréal the tyres show essentially no wear after fuel burn and track evolution are removed (95% interval -0.009 to +0.009), for the compounds actually run (C4, C5); the hardest allocated compound had too few stints to estimate. Montréal is Tier 2, so it gets no strategy call.

## Limits

- Fifteen to twenty finishers per race and one race per circuit: a single season, so a call that disagrees once is a flag, not a refutation.
- "Modal stops" are a proxy for the best strategy, not proof of it: teams optimise finishing position, the model optimises race time (scope section 10).
- With few clear 2-Stop calls the sample is small; the baseline table shows what a naive rule would score.
