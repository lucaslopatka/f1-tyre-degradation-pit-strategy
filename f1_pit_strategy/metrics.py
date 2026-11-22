"""Fit and residual metrics of the per-circuit degradation model.

    python -m f1_pit_strategy.metrics

Per circuit this reports how well the model of degradation.py fits and whether its assumptions look
reasonable, next to the result (d). R-squared alone is misleading here: the driver intercepts
(car and driver pace) explain most of the lap-time variation, so R-squared is also computed for a
driver-only model, and the difference shows what the race-lap and tyre terms add.

Writes data/processed/model_metrics.csv and docs/model_metrics.md.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from f1_pit_strategy import config, degradation
from f1_pit_strategy.eda import helpers


def lag1_autocorrelation(sub: pd.DataFrame, resid: pd.Series) -> float:
    """Correlation between a lap's residual and the previous lap's residual in the same stint.

    Only consecutive race laps are paired (cleaning removes some laps). A value well above 0 means
    laps in a stint are not independent, which is why standard errors are clustered by stint.
    """
    d = sub.assign(resid=resid).sort_values(["StintId", "LapNumber"])
    prev = d.groupby("StintId")[["resid", "LapNumber"]].shift(1)
    paired = (d["LapNumber"] - prev["LapNumber"]) == 1
    return float(np.corrcoef(d.loc[paired, "resid"], prev.loc[paired, "resid"])[0, 1])


def circuit_metrics(laps: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for round_number, sub in laps.groupby("Round"):
        fit, _ = degradation.fit_circuit(sub)
        baseline = smf.ols("LapTime ~ C(Driver)", data=sub).fit()
        rmse = float(np.sqrt(fit.ssr / fit.df_resid))
        rows.append({"Round": round_number, "City": sub["City"].iloc[0], "Laps": len(sub), "Stints": sub["StintId"].nunique(),
                     "R2": fit.rsquared, "R2_adj": fit.rsquared_adj, "R2_driver_only": baseline.rsquared,
                     "R2_added": fit.rsquared - baseline.rsquared, "RMSE": rmse,
                     "Lag1": lag1_autocorrelation(sub, fit.resid),
                     "Beyond3SD": float((fit.resid.abs() > 3 * rmse).mean())})
    return pd.DataFrame(rows)


def markdown(m: pd.DataFrame, summary: pd.DataFrame) -> str:
    t = m.merge(summary[["Round", "D", "D_Low", "D_High", "Tier"]], on="Round")
    table = pd.DataFrame({
        "Circuit": t["City"], "Laps": t["Laps"], "Stints": t["Stints"],
        "R²": t["R2"].round(3), "Adj. R²": t["R2_adj"].round(3), "R² driver only": t["R2_driver_only"].round(3),
        "R² added": t["R2_added"].round(3), "Residual SD (s)": t["RMSE"].round(2), "Lag-1 residual corr.": t["Lag1"].round(2),
        "Beyond 3 SD": (t["Beyond3SD"] * 100).round(1).astype(str) + "%",
        "d (s/lap), 95% interval": [f"{r.D:.3f} ({r.D_Low:.3f} to {r.D_High:.3f})" for r in t.itertuples()],
        "Tier": t["Tier"]})
    return f"""# Model metrics: how well does the degradation model fit?

Reproduce: `python -m f1_pit_strategy.metrics` (this file is generated). Model: one regression per circuit on the clean laps, `LapTime ~ driver + LapNumber + compound + compound:TyreLife`
(see `docs/scope.md` section 8 and `f1_pit_strategy/degradation.py`).

{helpers.md_table(table)}

**Columns.** *R²* is the share of lap-time variance the whole model explains. *R² driver only* is the same for a model with driver intercepts alone, and *R² added* is the gain from the race-lap and
tyre terms. *Residual SD* is the typical miss in seconds (residual standard error). *Lag-1 residual corr.* is the correlation between consecutive laps' residuals inside a stint. *Beyond 3 SD* is the
share of laps whose residual is more than three residual SDs. *Tier* is the decision tier (1 = strategy call, 2 = no call).

## Reading the table

- **Fit.** R² runs from {m['R2'].min():.2f} to {m['R2'].max():.2f} (median {m['R2'].median():.2f}), but a driver-only model already reaches {m['R2_driver_only'].min():.2f} to {m['R2_driver_only'].max():.2f}. The race-lap and tyre terms add a median
  {m['R2_added'].median():.3f} (range {m['R2_added'].min():.3f} to {m['R2_added'].max():.3f}). So a high R² mostly reflects car and driver pace and says little about whether the wear slope is right; the interval on d is the better evidence.
- **Size of the miss.** The residual SD is a median {m['RMSE'].median():.2f} s per lap (range {m['RMSE'].min():.2f} to {m['RMSE'].max():.2f}; largest at {', '.join(m.nlargest(2, 'RMSE')['City'])}). A wear rate of 0.05 s per lap adds only 1 s after 20 laps, so single laps are noisy
  relative to the effect and the estimates need many laps, which is what the intervals reflect.
- **Independence.** Residuals of consecutive laps in a stint correlate {m['Lag1'].min():+.2f} to {m['Lag1'].max():+.2f} (median {m['Lag1'].median():+.2f}). Laps in a stint are therefore not independent, so ordinary standard errors would be too
  small; this is why the intervals use standard errors clustered by stint. The strongest are {', '.join(m.nlargest(2, 'Lag1')['City'])}, where traffic (not filtered in v1) is a likely contributor (not tested).
- **Outliers.** A median {m['Beyond3SD'].median() * 100:.1f}% of laps lie beyond three residual SDs (max {m['Beyond3SD'].max() * 100:.1f}%), a mild heavy tail.

## Other metrics in the project

- Validation against real stop counts (agreement with finishers, naive baselines): `docs/validation.md`.
- Pit-lane loss (median P, IQR, number of stops) and the decision table: `docs/decision.md`.
- Data-quality score of the raw laps (8.9 of 10), cleaning funnel and EDA statistics: `docs/eda.md` and `reports/analysis/`.

## Limits

- All metrics are in-sample: they describe the fit on the laps used to estimate it, not prediction on new races. The out-of-sample test that matters here is the comparison with real stop counts.
- R² with many intercepts rewards the driver terms; adjusted R² is shown for that reason.
"""


def main() -> None:
    laps = degradation.load_laps()
    m = circuit_metrics(laps)
    m.to_csv(config.PROCESSED_DIR / "model_metrics.csv", index=False)
    summary = pd.read_csv(config.PROCESSED_DIR / "decision_summary.csv")
    helpers.write_doc("model_metrics.md", markdown(m, summary))
    pd.set_option("display.width", 220)
    print(m.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
