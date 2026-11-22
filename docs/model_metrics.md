# Model metrics: how well does the degradation model fit?

Reproduce: `python -m f1_pit_strategy.metrics` (this file is generated). Model: one regression per circuit on the clean laps, `LapTime ~ driver + LapNumber + compound + compound:TyreLife`
(see `docs/scope.md` section 8 and `f1_pit_strategy/degradation.py`).

| Circuit | Laps | Stints | R² | Adj. R² | R² driver only | R² added | Residual SD (s) | Lag-1 residual corr. | Beyond 3 SD | d (s/lap), 95% interval | Tier |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Melbourne | 774 | 47 | 0.784 | 0.777 | 0.639 | 0.145 | 0.78 | 0.42 | 1.3% | 0.029 (0.018 to 0.040) | 2 |
| Shanghai | 639 | 35 | 0.876 | 0.872 | 0.633 | 0.243 | 0.51 | 0.35 | 1.3% | 0.052 (0.040 to 0.064) | 2 |
| Suzuka | 891 | 42 | 0.911 | 0.908 | 0.614 | 0.297 | 0.47 | 0.28 | 1.6% | 0.050 (0.031 to 0.069) | 1 |
| Miami | 712 | 37 | 0.846 | 0.84 | 0.775 | 0.07 | 0.6 | 0.31 | 2.0% | 0.018 (-0.004 to 0.040) | 1 |
| Montréal | 714 | 45 | 0.761 | 0.752 | 0.652 | 0.109 | 0.78 | 0.24 | 2.2% | 0.000 (-0.009 to 0.009) | 2 |
| Monaco | 1,119 | 49 | 0.573 | 0.563 | 0.439 | 0.134 | 1.12 | 0.65 | 0.9% | 0.041 (0.026 to 0.057) | 1 |
| Barcelona | 966 | 62 | 0.878 | 0.875 | 0.646 | 0.232 | 0.62 | 0.36 | 1.9% | 0.152 (0.138 to 0.165) | 1 |
| Spielberg | 1,118 | 61 | 0.839 | 0.836 | 0.596 | 0.243 | 0.57 | 0.37 | 1.7% | 0.081 (0.073 to 0.090) | 1 |
| Silverstone | 758 | 48 | 0.903 | 0.9 | 0.718 | 0.185 | 0.52 | 0.25 | 1.5% | 0.060 (0.050 to 0.071) | 1 |
| Spa | 597 | 40 | 0.865 | 0.859 | 0.772 | 0.093 | 0.64 | 0.34 | 1.8% | 0.051 (0.034 to 0.067) | 2 |
| Budapest | 1,175 | 65 | 0.824 | 0.82 | 0.56 | 0.265 | 0.7 | 0.39 | 1.3% | 0.071 (0.059 to 0.084) | 1 |
| Zandvoort | 485 | 50 | 0.849 | 0.841 | 0.604 | 0.245 | 0.64 | 0.26 | 1.4% | 0.055 (0.040 to 0.070) | 1 |
| Monza | 833 | 29 | 0.755 | 0.747 | 0.661 | 0.094 | 0.6 | 0.22 | 1.6% | 0.015 (0.004 to 0.026) | 2 |
| Madrid | 915 | 45 | 0.761 | 0.754 | 0.522 | 0.24 | 1.06 | 0.53 | 1.7% | 0.017 (0.002 to 0.031) | 1 |
| Baku | 648 | 39 | 0.91 | 0.907 | 0.522 | 0.389 | 0.48 | 0.3 | 1.4% | 0.010 (0.002 to 0.019) | 2 |
| Kuala Lumpur | 385 | 33 | 0.756 | 0.738 | 0.492 | 0.264 | 0.64 | 0.2 | 1.3% | 0.110 (0.087 to 0.133) | 1 |
| Singapore | 951 | 43 | 0.762 | 0.756 | 0.633 | 0.129 | 0.83 | 0.46 | 2.1% | 0.049 (0.032 to 0.066) | 1 |
| Austin | 844 | 50 | 0.847 | 0.842 | 0.568 | 0.279 | 0.6 | 0.37 | 1.4% | 0.066 (0.053 to 0.080) | 1 |
| Mexico City | 682 | 34 | 0.796 | 0.789 | 0.712 | 0.084 | 0.43 | 0.36 | 2.3% | 0.031 (0.024 to 0.038) | 1 |

**Columns.** *R²* is the share of lap-time variance the whole model explains. *R² driver only* is the same for a model with driver intercepts alone, and *R² added* is the gain from the race-lap and
tyre terms. *Residual SD* is the typical miss in seconds (residual standard error). *Lag-1 residual corr.* is the correlation between consecutive laps' residuals inside a stint. *Beyond 3 SD* is the
share of laps whose residual is more than three residual SDs. *Tier* is the decision tier (1 = strategy call, 2 = no call).

## Reading the table

- **Fit.** R² runs from 0.57 to 0.91 (median 0.84), but a driver-only model already reaches 0.44 to 0.78. The race-lap and tyre terms add a median
  0.232 (range 0.070 to 0.389). So a high R² mostly reflects car and driver pace and says little about whether the wear slope is right; the interval on d is the better evidence.
- **Size of the miss.** The residual SD is a median 0.62 s per lap (range 0.43 to 1.12; largest at Monaco, Madrid). A wear rate of 0.05 s per lap adds only 1 s after 20 laps, so single laps are noisy
  relative to the effect and the estimates need many laps, which is what the intervals reflect.
- **Independence.** Residuals of consecutive laps in a stint correlate +0.20 to +0.65 (median +0.35). Laps in a stint are therefore not independent, so ordinary standard errors would be too
  small; this is why the intervals use standard errors clustered by stint. The strongest are Monaco, Madrid, where traffic (not filtered in v1) is a likely contributor (not tested).
- **Outliers.** A median 1.6% of laps lie beyond three residual SDs (max 2.3%), a mild heavy tail.

## Other metrics in the project

- Validation against real stop counts (agreement with finishers, naive baselines): `docs/validation.md`.
- Pit-lane loss (median P, IQR, number of stops) and the decision table: `docs/decision.md`.
- Stage 2 hypothesis tests (joint F-test for H2, WLS fits for H1 and H3, weighted R² 0.21 to 0.91, residual scale, weight concentration): `docs/stage2.md`.
- Data-quality score of the raw laps (8.9 of 10), cleaning funnel and EDA statistics: `docs/eda.md` and `reports/analysis/`.

## Limits

- All metrics are in-sample: they describe the fit on the laps used to estimate it, not prediction on new races. The out-of-sample test that matters here is the comparison with real stop counts.
- R² with many intercepts rewards the driver terms; adjusted R² is shown for that reason.
