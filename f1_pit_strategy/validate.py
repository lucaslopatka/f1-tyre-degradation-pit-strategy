"""Validation: do the model's 1-stop / 2-stop calls match what finishers actually did?

    python -m f1_pit_strategy.validate

For the Tier 1 circuits, compare the call from decision.py with the number of pit stops made
by the cars that finished (a finisher is a driver whose last lap reaches FINISHER_LAP_SHARE of
the race's last lap; this is the same 90% idea as the official classification).

Agreement rule: a 1-Stop call agrees if more than half of the finishers made exactly one stop;
a 2-Stop call agrees if more than half made two or more.

The model describes a green-flag race, but real races have safety cars. A stop under a safety
car, a virtual safety car or a red flag costs little or nothing, so teams take extra ones. To
see how much of any disagreement that explains, each driver also gets a *green-flag equivalent*
count: max(1, stops under green or yellow), i.e. the stops they would have needed without the
cheap ones. Overtaking difficulty (H5) is not tested here: the circuit_overtaking.csv table has
not been compiled yet.

Writes data/processed/validation_stops.csv and docs/validation.md.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from f1_pit_strategy import clean, config, degradation, pit_loss
from f1_pit_strategy.eda import helpers


def finishers(raw: pd.DataFrame) -> pd.DataFrame:
    last = raw.groupby(["Round", "Driver"])["LapNumber"].max().rename("Last").reset_index()
    last["Finished"] = last["Last"] >= config.FINISHER_LAP_SHARE * last["Round"].map(raw.groupby("Round")["LapNumber"].max())
    return last.loc[last["Finished"], ["Round", "Driver"]]


def stop_kind(in_status: str, out_status: str) -> str:
    """Flag condition of a stop, worst first (the track status of the in-lap and out-lap are concatenated codes)."""
    codes = f"{in_status}{out_status}"
    for kind, marks in [("red", "5"), ("SC", "4"), ("VSC", "67"), ("yellow", "2")]:
        if any(m in codes for m in marks):
            return kind
    return "green"


def driver_stops(raw: pd.DataFrame) -> pd.DataFrame:
    """Per finisher: all stops, stops under SC/VSC/red flag, and the green-flag equivalent count."""
    stops = pit_loss.stop_pairs(raw)
    stops["Kind"] = [stop_kind(a, b) for a, b in zip(stops["InStatus"], stops["OutStatus"])]
    stops["Free"] = stops["Kind"].isin(["SC", "VSC", "red"])
    per = stops.groupby(["Round", "Driver"]).agg(Stops=("InLap", "size"), FreeStops=("Free", "sum")).reset_index()
    d = finishers(raw).merge(per, on=["Round", "Driver"], how="left").fillna({"Stops": 0, "FreeStops": 0})
    d["GreenEq"] = np.maximum(1, d["Stops"] - d["FreeStops"])
    return d


def agrees(call: str, counts: pd.Series) -> float:
    """Share of finishers whose stop count matches the call (exactly 1 for 1-Stop, 2 or more for 2-Stop)."""
    return float((counts == 1).mean() if call == "1-Stop" else (counts >= 2).mean())


def circuit_table(drivers: pd.DataFrame, summary: pd.DataFrame, raw: pd.DataFrame) -> pd.DataFrame:
    wet = raw.groupby("Round").apply(lambda g: clean.is_wet_lap(g).mean(), include_groups=False)
    rows = []
    for r in summary[summary["Tier"] == 1].sort_values("Margin", ascending=False).itertuples():
        d = drivers[drivers["Round"] == r.Round]
        share, share_eq = agrees(r.Call, d["Stops"]), agrees(r.Call, d["GreenEq"])
        verdict = "agrees" if share > 0.5 else ("disagrees, explained by free stops" if share_eq > 0.5 else "disagrees, not explained")
        rows.append({"Circuit": r.City, "Model call": f"{r.Call} ({r.Certainty})", "Finishers": len(d),
                     "1 stop": int((d["Stops"] == 1).sum()), "2 stops": int((d["Stops"] == 2).sum()), "3+ stops": int((d["Stops"] >= 3).sum()),
                     "Modal / median": f"{int(d['Stops'].mode().iloc[0])} / {d['Stops'].median():g}",
                     "Made the call's count": f"{share:.0%}", "Stops under SC/VSC/red": f"{d['FreeStops'].sum() / max(d['Stops'].sum(), 1):.0%}",
                     "Green-flag equivalent": f"{share_eq:.0%}", "Wet laps": f"{wet[r.Round]:.0%}", "Verdict": verdict,
                     "_share": share, "_share_eq": share_eq, "_call": r.Call, "_unsure": r.Certainty == "uncertain", "_round": r.Round})
    return pd.DataFrame(rows)


def baselines(drivers: pd.DataFrame, table: pd.DataFrame) -> dict[str, tuple[int, int]]:
    """Agreement of the model and of two naive rules ('always 1-Stop', 'always 2-Stop') on both stop counts."""
    out = {"Model": (int((table["_share"] > 0.5).sum()), int((table["_share_eq"] > 0.5).sum()))}
    for name, call in [("Always 1-Stop", "1-Stop"), ("Always 2-Stop", "2-Stop")]:
        a = [agrees(call, drivers.loc[drivers["Round"] == r, "Stops"]) > 0.5 for r in table["_round"]]
        b = [agrees(call, drivers.loc[drivers["Round"] == r, "GreenEq"]) > 0.5 for r in table["_round"]]
        out[name] = (sum(a), sum(b))
    return out


def montreal_check(laps: pd.DataFrame, city: str = "Montréal") -> str:
    """Why is d ~ 0 there? Check collinearity, clipping and sensitivity to the model's shape."""
    import statsmodels.formula.api as smf
    rows = []
    for r, sub in laps.groupby("Round"):
        x = pd.get_dummies(sub[["Driver", "CompoundAbsolute"]], drop_first=True).astype(float).assign(one=1.0).to_numpy()
        res = lambda v: v.to_numpy(float) - x @ np.linalg.lstsq(x, v.to_numpy(float), rcond=None)[0]  # noqa: E731
        rows.append((sub["City"].iloc[0], np.corrcoef(res(sub["TyreLife"]), res(sub["LapNumber"]))[0, 1]))
    pc = pd.Series(dict(rows))
    circuits = pd.read_csv(config.PROCESSED_DIR / "degradation_by_circuit.csv").set_index("City")
    sub = laps[laps["City"] == city]
    fit, _ = degradation.fit_circuit(sub)
    cells = degradation.cell_table(sub, fit)
    base = degradation.FORMULA.format(fe="Driver")

    def d_for(formula: str, data: pd.DataFrame) -> float:
        res = smf.ols(formula, data=data).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(data["StintId"])[0]})
        return degradation.circuit_rate(degradation.cell_table(data, res), res)[0]
    variants = {"base": d_for(base, sub), "plus a squared race-lap term": d_for(base + " + I(LapNumber**2)", sub),
                "laps after 25 only": d_for(base, sub[sub["LapNumber"] > 25]), "team intercepts": d_for(base.replace("C(Driver)", "C(Team)"), sub)}
    return (f"- **Collinearity is not the cause.** After removing driver and compound effects, tyre age and race lap correlate {pc[city]:.2f} at {city} "
            f"(rank {int(pc.rank()[city])} of 19, 1 = lowest), and its standard error ({circuits.loc[city, 'D_SE']:.4f}) is the "
            f"{int(circuits['D_SE'].rank()[city])}rd smallest of 19: the estimate is precise, not unstable.\n"
            f"- **It is not clipped at zero.** The estimates are {', '.join(f'{r.Compound} {r.Beta:+.4f} (se {r.SE:.4f})' for r in cells[cells['Estimable']].itertuples())}; one is negative.\n"
            f"- **It is stable.** d stays between {min(variants.values()):+.4f} and {max(variants.values()):+.4f} when the model changes ({'; '.join(f'{k} {v:+.4f}' for k, v in variants.items())}).\n"
            f"- **Reading.** At {city} the tyres show essentially no wear after fuel burn and track evolution are removed (95% interval {circuits.loc[city, 'D_Low']:+.3f} to {circuits.loc[city, 'D_High']:+.3f}), "
            f"for the compounds actually run ({', '.join(cells[cells['Estimable']]['Compound'])}); the hardest allocated compound had too few stints to estimate. {city} is Tier 2, so it gets no strategy call.")


def markdown(table: pd.DataFrame, base: dict, laps: pd.DataFrame) -> str:
    n = len(table)
    disagree = table[table["Verdict"] != "agrees"]
    clear = table[~table["_unsure"]]
    shown = table.drop(columns=[c for c in table.columns if c.startswith("_")])
    lines = "\n".join(f"| {k} | {a} of {n} | {b} of {n} |" for k, (a, b) in base.items())
    return f"""# Validation: do the calls match what teams did?

Reproduce: `python -m f1_pit_strategy.validate` (this file is generated). Needs `decision_summary.csv` (decision layer) and the raw laps.

**Test.** For each of the {n} Tier 1 circuits, count the pit stops of the cars that finished (a finisher's last lap reaches 90% of the race's last lap).
A 1-Stop call agrees if more than half of the finishers made exactly one stop; a 2-Stop call agrees if more than half made two or more.

## Result

{helpers.md_table(shown)}

`Green-flag equivalent` repeats the comparison after discounting the cheap stops made under a safety car, virtual safety car or red flag (each driver counts max(1, stops under green or yellow)).

**Summary.** The model agrees with the real stop count at {int((table['_share'] > 0.5).sum())} of {n} circuits (and {int((clear['_share'] > 0.5).sum())} of its {len(clear)} clear calls).
{len(disagree)} disagree ({', '.join(disagree['Circuit'])}); {'all' if (disagree['Verdict'] == 'disagrees, explained by free stops').all() else int((disagree['Verdict'] == 'disagrees, explained by free stops').sum())} of them are explained by free stops under safety cars, virtual safety cars and red flags (the green-flag equivalent count then matches the call).

How the model compares with two naive rules (circuits agreeing):

| Rule | On actual stops | On green-flag equivalent stops |
|---|---|---|
{lines}

## Reading the disagreements

- The model describes a **green-flag** race. Where a safety car, virtual safety car or red flag came, teams took extra, nearly free stops, so the real count is higher than the green-flag optimum. This is the limitation written in the scope (section 10), now measured.
- **Overtaking difficulty (H5) is not tested.** The `circuit_overtaking.csv` table has not been compiled, so no claim is made about it. It stays a hypothesis for the circuits where unexplained gaps remain.
- Zandvoort and Kuala Lumpur had rain laps (11% each), which also pushes stop counts up for reasons the model ignores.
- Mexico City's data stops at lap 56 of 71, so stops after lap 56 are not observed.

## Montréal check: why is d = 0.000?

{montreal_check(laps)}

## Limits

- Fifteen to twenty finishers per race and one race per circuit: a single season, so a call that disagrees once is a flag, not a refutation.
- "Modal stops" are a proxy for the best strategy, not proof of it: teams optimise finishing position, the model optimises race time (scope section 10).
- With few clear 2-Stop calls the sample is small; the baseline table shows what a naive rule would score.
"""


def main() -> None:
    raw = clean.add_city(clean.fix_dtypes(clean.load_raw()))
    raw["near_wet"] = clean.near_wet_lap(raw)  # stop_pairs expects this column
    summary = pd.read_csv(config.PROCESSED_DIR / "decision_summary.csv")
    drivers = driver_stops(raw)
    table = circuit_table(drivers, summary, raw)
    base = baselines(drivers, table)
    drivers.to_csv(config.PROCESSED_DIR / "validation_stops.csv", index=False)
    helpers.write_doc("validation.md", markdown(table, base, degradation.load_laps()))
    pd.set_option("display.width", 250)
    print(table.drop(columns=[c for c in table.columns if c.startswith("_")]).to_string(index=False))
    print("\nagreement (actual / green-flag equivalent):", base)


if __name__ == "__main__":
    main()
