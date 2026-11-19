"""Step 7: tyre degradation rate (beta, seconds per lap of tyre age) per circuit and compound.

    python -m f1_pit_strategy.degradation

One regression per circuit, on that circuit's clean laps:

    LapTime ~ driver intercepts + LapNumber + compound intercepts + (TyreLife slope per compound)

- Driver intercepts remove car and driver pace (team explains 48% of what is left once the
  circuit is removed, see docs/eda.md).
- LapNumber is shared by all stints. It absorbs fuel burn and track evolution together.
- The TyreLife slope per compound is beta: how much slower the car gets per extra lap of
  tyre age, after those two effects are removed.

Why a pooled regression and not one slope per stint: inside a stint, tyre age and race lap rise
together, so a single stint cannot tell wear from fuel burn (docs/scope.md section 5). What
separates them is that drivers start stints on different race laps, which only a pooled fit uses.

Standard errors are clustered by stint, because laps in the same stint are not independent.

The circuit-level rate d is the lap-weighted mean of the estimable compound slopes (weights =
clean laps each compound ran at that circuit), with its variance taken from the regression's
covariance matrix. Cells with fewer than MIN_CELL_STINTS stints are not estimable and are left
out of d, but their laps stay in the fit (they help identify the race-lap effect).

Writes data/processed/degradation_by_cell.csv and degradation_by_circuit.csv.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from f1_pit_strategy import config

FORMULA = "LapTime ~ C({fe}) + LapNumber + C(CompoundAbsolute) + C(CompoundAbsolute):TyreLife"
Z95 = 1.96


def load_laps() -> pd.DataFrame:
    """Clean laps with plain types (statsmodels is safest with str, int and float)."""
    laps = pd.read_parquet(config.PROCESSED_DIR / "clean_laps.parquet")
    laps = laps.astype({"Driver": str, "Team": str, "CompoundAbsolute": str, "City": str})
    laps["TyreLife"] = laps["TyreLife"].astype(float)
    laps["StintId"] = laps["Driver"] + "-" + laps["Stint"].astype(str)
    return laps


def fit_circuit(laps: pd.DataFrame, fe: str = "Driver"):
    """Fit the circuit regression with standard errors clustered by stint."""
    groups = pd.factorize(laps["StintId"])[0]
    model = smf.ols(FORMULA.format(fe=fe), data=laps)
    result = model.fit(cov_type="cluster", cov_kwds={"groups": groups})
    full_rank = np.linalg.matrix_rank(model.exog) == model.exog.shape[1]
    return result, full_rank


def cell_table(laps: pd.DataFrame, result) -> pd.DataFrame:
    """One row per compound at this circuit: stints, laps, beta, standard error, flags."""
    rows = []
    for comp, sub in laps.groupby("CompoundAbsolute"):
        name = f"C(CompoundAbsolute)[{comp}]:TyreLife"
        stints = sub["StintId"].nunique()
        beta, se = float(result.params[name]), float(result.bse[name])
        rows.append({"Compound": comp, "Stints": stints, "Laps": len(sub), "ParamName": name,
                     "Beta": beta, "SE": se, "Estimable": stints >= config.MIN_CELL_STINTS,
                     "Thin": config.MIN_CELL_STINTS <= stints < config.THIN_CELL_STINTS})
    return pd.DataFrame(rows)


def circuit_rate(cells: pd.DataFrame, result) -> tuple[float, float]:
    """Lap-weighted mean of the estimable betas and its standard error: d = w'b, var = w'Vw."""
    use = cells[cells["Estimable"]]
    if use.empty:
        return np.nan, np.nan
    w = (use["Laps"] / use["Laps"].sum()).to_numpy()
    cov = result.cov_params().loc[use["ParamName"], use["ParamName"]].to_numpy()
    return float(w @ use["Beta"].to_numpy()), float(np.sqrt(w @ cov @ w))


def run_all(laps: pd.DataFrame, fe: str = "Driver") -> tuple[pd.DataFrame, pd.DataFrame]:
    cell_rows, circuit_rows = [], []
    for round_number, sub in laps.groupby("Round"):
        result, full_rank = fit_circuit(sub, fe)
        cells = cell_table(sub, result)
        d, d_se = circuit_rate(cells, result)
        city = sub["City"].iloc[0]
        circuit_rows.append({"Round": round_number, "City": city, "CleanLaps": len(sub), "Stints": sub["StintId"].nunique(),
                             "RaceLapEffect": float(result.params["LapNumber"]), "D": d, "D_SE": d_se,
                             "D_Low": d - Z95 * d_se, "D_High": d + Z95 * d_se,
                             "CellsUsed": int(cells["Estimable"].sum()), "FullRank": full_rank, "R2": result.rsquared})
        cell_rows.append(cells.drop(columns="ParamName").assign(Round=round_number, City=city))
    return pd.concat(cell_rows, ignore_index=True), pd.DataFrame(circuit_rows)


def main() -> None:
    laps = load_laps()
    cells, circuits = run_all(laps)
    cells["Low"], cells["High"] = cells["Beta"] - Z95 * cells["SE"], cells["Beta"] + Z95 * cells["SE"]
    cells.to_csv(config.PROCESSED_DIR / "degradation_by_cell.csv", index=False)
    circuits.to_csv(config.PROCESSED_DIR / "degradation_by_circuit.csv", index=False)

    pd.set_option("display.width", 200)
    print("=== per circuit ===")
    print(circuits.round(4).to_string(index=False))
    print("\n=== per circuit and compound (estimable cells) ===")
    shown = cells[cells["Estimable"]][["City", "Compound", "Stints", "Laps", "Beta", "SE", "Low", "High", "Thin"]]
    print(shown.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
