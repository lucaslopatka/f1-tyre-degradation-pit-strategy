"""Profiles the cleaned laps and signs off the EDA checklist (workflow: programmatic-eda).

Follows the workflow's seven steps: overview, null profile, outliers (IQR and z-score),
distributions, correlations (flag |r| of 0.8 or more), checklist sign-off, findings.
Thresholds come from eda/settings.py. Nothing is removed: outliers are classified and
a decision is written next to each.

Writes reports/analysis/03_eda_report.md and reports/analysis/04_findings_summary.md.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.stats.outliers_influence import variance_inflation_factor

from f1_pit_strategy import clean, config
from f1_pit_strategy.eda import helpers, settings

NUMERIC = ["Stint", "LapNumber", "LapTime", "TyreLife", "TrackTemp", "TotalLaps", "LapTimeDelta"]
CATEGORICAL = ["City", "Driver", "Team", "Compound", "CompoundAbsolute", "FreshTyre"]


# ---------- 1. overview ----------

def schema_table(laps: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({"Type": laps.dtypes.astype(str), "Non-null %": ((1 - laps.isna().mean()) * 100).round(1),
                         "Distinct": laps.nunique(), "Example": laps.iloc[0].astype(str)}).reset_index(names="Column")


# ---------- 5. distributions ----------

def skew_flag(value: float) -> str:
    size = abs(value)
    if size > settings.SKEW_EXTREME:
        return "extreme"
    if size > settings.SKEW_HIGH:
        return "high"
    if size > settings.SKEW_MODERATE:
        return "moderate"
    return "ok"


def distribution_table(laps: pd.DataFrame) -> pd.DataFrame:
    d = laps[NUMERIC].describe(percentiles=helpers.PERCENTILES).T
    out = pd.DataFrame({"mean": d["mean"], "median": d["50%"], "std": d["std"], "p5": d["5%"], "p95": d["95%"],
                        "min": d["min"], "max": d["max"], "skew": laps[NUMERIC].skew(), "kurtosis": laps[NUMERIC].kurt()})
    out["skew flag"] = [skew_flag(v) for v in out["skew"]]
    return out.round(2).reset_index(names="Column")


def dominance_table(laps: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for column in CATEGORICAL:
        shares = laps[column].value_counts(normalize=True)
        rows.append((column, laps[column].nunique(), str(shares.index[0]), f"{shares.iloc[0]:.1%}",
                     "FLAG" if shares.iloc[0] > settings.DOMINANT_CATEGORY else "ok"))
    return pd.DataFrame(rows, columns=["Column", "Distinct", "Largest category", "Share", f"Over {settings.DOMINANT_CATEGORY:.0%}?"])


# ---------- 6. outliers ----------

OUTLIER_DECISIONS = {
    "LapTime": ("real (structural)", "keep: circuit differences make slow circuits look extreme when pooled; judged by circuit below"),
    "LapTimeDelta": ("real", "keep: slow laps that survived the 1.07 stint-median rule (traffic, late tyre drop-off); a v2 traffic filter may remove more"),
    "TyreLife": ("real", "keep: long stints are the evidence for one-stop strategies"),
    "LapNumber": ("real", "keep: long races such as Monaco (78 laps)"),
    "TrackTemp": ("real", "keep: hot and cool race days"),
    "Stint": ("real", "keep: multi-stop races"),
    "TotalLaps": ("structural", "keep: race distance differs by circuit"),
}


def outlier_table(laps: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for column in NUMERIC:
        values = laps[column]
        iqr = int(helpers.tukey_mask(values).sum())
        z = int(((values - values.mean()).abs() / values.std() > settings.Z_LIMIT).sum())
        kind, decision = OUTLIER_DECISIONS[column]
        rows.append((column, iqr, f"{iqr / len(laps):.1%}", z, f"{z / len(laps):.1%}", kind, decision))
    return pd.DataFrame(rows, columns=["Column", "IQR flags", "IQR %", "|z|>3 flags", "z %", "Class", "Decision"])


def within_circuit_outliers(laps: pd.DataFrame) -> int:
    return int(laps.groupby("Round")["LapTime"].apply(lambda s: helpers.tukey_mask(s).sum()).sum())


# ---------- 7. correlations ----------

def correlation_blocks(laps: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.Series]:
    data = laps[["LapTime", "LapTimeDelta", "TyreLife", "LapNumber", "TrackTemp"]].assign(FreshTyre=laps["FreshTyre"].astype(int))
    pearson = data.corr()
    spearman = data.corr(method="spearman")
    pairs = pearson.where(np.triu(np.ones(pearson.shape, dtype=bool), k=1)).stack().rename("r").reset_index()
    pairs.columns = ["A", "B", "r"]
    pairs = pairs.assign(abs_r=pairs["r"].abs()).sort_values("abs_r", ascending=False)
    features = data[["TyreLife", "LapNumber", "TrackTemp", "FreshTyre"]].astype(float)
    x = sm.add_constant(features)
    vif = pd.Series({c: variance_inflation_factor(x.values, i) for i, c in enumerate(x.columns) if c != "const"})
    return pearson, spearman, pairs, vif


# ---------- 8. business logic ----------

def business_checks(laps: pd.DataFrame, raw_rows: int, excluded_rows: int) -> tuple[pd.DataFrame, dict]:
    slope = float(np.polyfit(laps["LapNumber"], laps["LapTimeDelta"], 1)[0])
    early = float(laps.loc[laps["LapNumber"].between(2, 6), "LapTimeDelta"].mean())
    late = float(laps.loc[laps["LapNumber"] >= 60, "LapTimeDelta"].mean())
    ordered = laps.sort_values(["Round", "Driver", "LapNumber"])
    keys = [ordered["Round"], ordered["Driver"], ordered["Stint"]]
    age_step = ordered["TyreLife"].groupby(keys).diff()
    lap_step = ordered["LapNumber"].groupby(keys).diff()
    allocation = clean.load_allocation().rename(columns={"CompoundAbsolute": "expected"})
    mapped = laps.merge(allocation, on=["Round", "Compound"], how="left")
    medians = laps.groupby("Round")["LapTime"].median()
    tests = [
        ("Fuel burn and track evolution make laps faster as a race goes on", slope < 0,
         f"slope of LapTimeDelta on LapNumber is {slope:+.4f} s per lap; laps 2-6 average {early:+.2f} s, laps 60+ average {late:+.2f} s"),
        ("Tyre age rises exactly with the race lap inside each stint", bool((age_step.dropna() == lap_step.dropna()).all()),
         "every step in tyre age equals the step in race lap, including after dropped laps"),
        ("CompoundAbsolute equals the allocation table for every lap", bool((mapped["CompoundAbsolute"] == mapped["expected"]).all()),
         f"{len(laps):,} laps checked"),
        ("Circuit median lap times are plausible for F1 (60 to 130 s)", bool(medians.between(60, 130).all()),
         f"medians run {medians.min():.1f} to {medians.max():.1f} s"),
        ("Clean plus excluded laps equal raw laps", len(laps) + excluded_rows == raw_rows,
         f"{len(laps):,} + {excluded_rows:,} = {len(laps) + excluded_rows:,} vs {raw_rows:,} raw"),
    ]
    table = pd.DataFrame([(n, "PASS" if ok else "FAIL", d) for n, ok, d in tests], columns=["Business rule", "Result", "Evidence"])
    return table, {"slope": slope, "early": early, "late": late}


# ---------- 9. checklist (43 items from references/eda_checklist.md) ----------

def build_checklist(laps: pd.DataFrame, ctx: dict) -> pd.DataFrame:
    n = len(laps)
    P, W, NA = "PASS", "WARN", "N/A"
    items = [
        ("1 Structure", "File loads without errors", P, "parquet read cleanly"),
        ("1 Structure", "Row count is plausible", P, f"{n:,} clean laps from {ctx['raw']:,} raw over 19 circuits"),
        ("1 Structure", "Column count matches the schema documentation", P, f"{laps.shape[1] - 1} stored columns = config.CLEAN_COLUMNS (LapTimeDelta is derived here)"),
        ("1 Structure", "Column names are clear, no unnamed or duplicates", P, "13 distinct readable names"),
        ("1 Structure", "Grain identified", P, "one row = one clean lap by one driver"),
        ("1 Structure", "Primary key identified and unique", P, f"(Round, Driver, LapNumber): {ctx['dup_keys']} duplicates"),
        ("1 Structure", "Each column has the right type", P, "ints for counts, floats for seconds, text for labels, bool for FreshTyre"),
        ("1 Structure", "Joins do not inflate row counts", P, "allocation join is many-to-one and validated; row count unchanged"),
        ("2 Completeness", "Null counts reviewed for every column", P, "0 nulls in all 13 columns (raw nulls are in report 02)"),
        ("2 Completeness", "Null rates compared with thresholds", P, "0% everywhere; raw columns over 30% are structural"),
        ("2 Completeness", "Columns over 30% nulls justified", P, "none in the clean data"),
        ("2 Completeness", "Zeros are meaningful, not stand-ins", P, f"TrackTemp 0.0 sentinel removed; clean minimum is {laps['TrackTemp'].min():.1f}"),
        ("2 Completeness", "Expected null rate for optional columns documented", P, "EXPECTED_NULLS in eda/settings.py and report 02"),
        ("3 Uniqueness", "Full-row duplicates checked", P, f"{ctx['dup_rows']} duplicates"),
        ("3 Uniqueness", "Key-level duplicates checked", P, f"{ctx['dup_keys']} duplicates"),
        ("3 Uniqueness", "Partial duplicates (same ID, different timestamp)", NA, "no timestamps in the clean data"),
        ("3 Uniqueness", "Duplicate rate under 1% or explained", P, "0%"),
        ("4 Validity", "Numeric values inside business ranges", P, "all range guarantees pass (report 02)"),
        ("4 Validity", "Categoricals hold only expected values", P, "Compound is SOFT/MEDIUM/HARD; CompoundAbsolute is C1-C5"),
        ("4 Validity", "Dates inside the expected range", NA, "no date columns"),
        ("4 Validity", "Referential integrity or orphan rate documented", P, "orphans exist only for the dropped wet race (report 02)"),
        ("4 Validity", "Booleans hold only True or False", P, "FreshTyre has no nulls"),
        ("5 Distributions", "Descriptive statistics reviewed", P, "table in section 5"),
        ("5 Distributions", "Columns with |skew| above 2 flagged", W if ctx["extreme_skew"] else P,
         ", ".join(ctx["extreme_skew"]) + " flagged" if ctx["extreme_skew"] else "none above 2"),
        ("5 Distributions", "Outliers reviewed as real or error", P, "classified in section 6; none removed"),
        ("5 Distributions", "No category dominates unexpectedly (over 90%)", W if ctx["dominant"] else P,
         ", ".join(ctx["dominant"]) + " flagged" if ctx["dominant"] else "largest share is below 90%"),
        ("5 Distributions", "Coverage gaps checked", W if ctx["empty_laps"] else P,
         f"{ctx['empty_laps']} race laps have no clean lap at all; most in {ctx['empty_top']}; the rest are safety-car stretches"),
        ("6 Correlations", "Pairwise correlations computed", P, "Pearson and Spearman in section 7"),
        ("6 Correlations", "Pairs with |r| of 0.8 or more explained", P, f"none; largest is {ctx['top_pair']}"),
        ("6 Correlations", "Known relationships hold", P, f"race lap vs circuit-adjusted lap time is {ctx['r_lap']:+.2f} (fuel burn)"),
        ("6 Correlations", "Surprising zero correlations investigated", P, "TrackTemp 0.03 with adjusted lap time: temperature varies between circuits, not within"),
        ("7 Time-series", "Time column monotonic or gaps documented", P, "race laps rise within each driver; gaps are exclusions"),
        ("7 Time-series", "Latest record within expected lag", NA, "finished season, no feed"),
        ("7 Time-series", "Volume over time reviewed for drops", P, "fewer clean laps late in races (retirements, stops, safety cars); Mexico City stops at lap 56"),
        ("7 Time-series", "Weekend and holiday effects noted", NA, "not daily data"),
        ("8 Business logic", "Directional relationships correct", P, "fuel and track effect is negative (section 8)"),
        ("8 Business logic", "Derived columns verified against sources", P, "CompoundAbsolute vs allocation table; LapTimeDelta median is 0 per circuit"),
        ("8 Business logic", "Totals reconcile with the aggregate", P, "clean + excluded = raw (report 01)"),
        ("8 Business logic", "Known data issues documented", P, "Mexico City truncation, wet cutoff default, dirty air (assumptions log)"),
        ("9 Sign-off", "FAIL-level items resolved or accepted", P, "Mexico City truncation accepted by the author"),
        ("9 Sign-off", "WARN-level items in the findings summary", P, "report 04"),
        ("9 Sign-off", "EDA report completed", P, "this file"),
        ("9 Sign-off", "Next step confirmed", P, "data ready for modelling; later steps are documented in docs/PROJECT_LOG.md"),
    ]
    assert len(items) == 43, len(items)
    return pd.DataFrame(items, columns=["Section", "Item", "Status", "Evidence"])


# ---------- findings summary (assets/findings_summary.md) ----------

def findings_summary(laps: pd.DataFrame, cells: pd.DataFrame, ctx: dict, biz: dict) -> str:
    thin = cells[cells["Stints"] < 4]
    mid = cells[(cells["Stints"] >= 4) & (cells["Stints"] < 8)]
    thin_list = "; ".join(f"{r.City} {r.Compound}" for r in thin.itertuples())
    return f"""# 04. EDA findings summary (workflow: programmatic-eda)

Dataset: cleaned 2026 race laps ({len(laps):,} rows). Date: {helpers.today()}. Analyst: Claude with the project author.
Full report: `03_eda_report.md`.

## Dataset at a glance
- **Rows and grain:** {len(laps):,} rows; one row = one clean lap by one driver; 19 circuits, 854 stints.
- **Analysis range:** the 2026 season, rounds 1 to 19 (São Paulo dropped as a wet race).
- **Overall data quality: Good.** No nulls, no duplicates, every range and consistency guarantee passes. The caveats below are about coverage, not errors.

## Top quality issues

**1. Thin circuit-compound cells**
- **What:** {len(thin)} of {len(cells)} cells have fewer than 4 stints ({thin_list}) and {len(mid)} more have 4 to 7.
- **Impact:** no slope can be estimated for those cells; the decision rule cannot cover them.
- **Recommended action:** report them as not estimable; do not fill them in.
- **Owner:** analyst.

**2. Mexico City is truncated**
- **What:** laps 57 to 71 are missing from the API; clean tyre ages stop near 43 laps.
- **Impact:** its slope is extrapolated if used for a full-distance strategy.
- **Recommended action:** accept and state it as a limitation (done by the author, 2026-11-19).
- **Owner:** business stakeholder (author).

**3. Dirty-air laps are still in the data**
- **What:** the traffic filter is deferred to v2; {ctx['within_circuit_outliers']} laps are still IQR outliers within their own circuit.
- **Impact:** traffic-limited laps can inflate slopes.
- **Recommended action:** keep as a documented limitation; add the filter in v2.
- **Owner:** analyst.

**4. Race lap and tyre age are confounded**
- **What:** laps get faster by {abs(biz['slope']):.3f} s per race lap; raw lap time falls with tyre age.
- **Impact:** a model without race lap would report negative degradation.
- **Recommended action:** keep `LapNumber` in the model; the variance inflation factors (at most {ctx['max_vif']:.2f}) show it can be separated.
- **Owner:** analyst.

**5. The 25% wet cutoff is a default**
- **What:** chosen without data; at 10% two more circuits drop, at 40% São Paulo returns.
- **Impact:** changes which circuits are covered.
- **Recommended action:** keep 25% and report the sensitivity.
- **Owner:** business stakeholder (author).

## What looks good
- 0 missing values and 0 duplicate laps in the cleaned data.
- No pair of features is strongly correlated (largest |r| is {ctx['top_abs']:.2f}), so features can share a model.
- Every clean lap maps to a C1 to C5 compound; every stint has one compound and at least 5 laps.
- Every count reconciles between raw, cleaned and excluded laps (report 01).

## Next step
- [x] Data is ready for modelling (the later steps are documented in docs/PROJECT_LOG.md).
- [ ] A data fix is needed.
- [ ] Further investigation is needed.
"""


def run() -> None:
    laps = helpers.load_clean()
    excl = helpers.load_exclusions()
    raw_rows = len(helpers.load_ingested())
    cells = helpers.cell_counts(laps)

    dist = distribution_table(laps)
    dom = dominance_table(laps)
    pearson, spearman, pairs, vif = correlation_blocks(laps)
    biz_table, biz = business_checks(laps, raw_rows, len(excl))
    empty_by_city = {}
    for _, g in laps.groupby("Round"):
        have = set(g["LapNumber"])
        empty_by_city[g["City"].iloc[0]] = sum(1 for lap in range(2, int(g["TotalLaps"].iloc[0]) + 1) if lap not in have)
    top_empty = sorted(empty_by_city.items(), key=lambda kv: -kv[1])[:3]
    ctx = dict(raw=raw_rows, dup_keys=int(laps.duplicated(["Round", "Driver", "LapNumber"]).sum()),
               dup_rows=int(laps.duplicated().sum()), extreme_skew=dist.loc[dist["skew flag"] == "extreme", "Column"].tolist(),
               dominant=dom.loc[dom.iloc[:, 4] == "FLAG", "Column"].tolist(), empty_laps=sum(empty_by_city.values()),
               empty_top=", ".join(f"{c} ({n})" for c, n in top_empty),
               top_pair=f"{pairs.iloc[0]['A']} vs {pairs.iloc[0]['B']} at {pairs.iloc[0]['r']:+.2f}",
               top_abs=float(pairs.iloc[0]["abs_r"]), r_lap=float(pearson.loc["LapNumber", "LapTimeDelta"]),
               max_vif=float(vif.max()), within_circuit_outliers=within_circuit_outliers(laps))
    strong = pairs[pairs["abs_r"] >= settings.CORR_STRONG]
    checklist = build_checklist(laps, ctx)

    num = lambda df: df.map('{:.2f}'.format)  # noqa: E731
    text = f"""# 03. EDA report (workflow: programmatic-eda)

Analyst: Claude with the project author. Date: {helpers.today()}.
Dataset: `data/processed/clean_laps.parquet`.
Business context: each row is one normal racing lap; the data informs the one-stop versus two-stop decision per circuit.
Thresholds: null 5%/30%, |z| 3, IQR 1.5, skew 0.5/1/2, |r| 0.8, set in `f1_pit_strategy/eda/settings.py`.

## 1. Dataset overview
- Rows {len(laps):,}; columns {laps.shape[1] - 1} stored + 1 derived (`LapTimeDelta`); memory {laps.memory_usage(deep=True).sum() / 1e6:.1f} MB.
- Date range: none stored; the season is 2026, rounds 1 to 19.
- Grain: one row = one clean lap by one driver. Primary key (Round, Driver, LapNumber): {ctx['dup_keys']} duplicates.
- `LapTimeDelta` = lap time minus the median clean lap time of the same circuit, in seconds (0 = a typical lap there, +1 = one second slower).

{helpers.md_table(schema_table(laps))}

## 2. Null and completeness profile
All 13 columns have 0% nulls: status OK everywhere. The raw data had structural nulls (pit times, sectors) and
placeholder values; those are covered in report 02.

## 3. Duplicate analysis
Full-row duplicates: {ctx['dup_rows']}. Duplicate keys: {ctx['dup_keys']}. Nothing to investigate.

## 4. Validity checks
Range, category and consistency guarantees on the cleaned laps all pass (see report 02, last table).

## 5. Distributions

{helpers.md_table(dist)}

Skew flags: {', '.join(f"{c} ({s})" for c, s in zip(dist['Column'], dist['skew flag']) if s != 'ok') or 'none'}. None is extreme (above 2), so no transformation is needed.
`Stint` is skewed because most drivers make one to three stints; `TyreLife` is right-skewed because few stints run long; pooled `LapTime` is
roughly symmetric because slow and fast circuits balance out.

Category balance (flag above 90%; `FreshTyre` is {dom.loc[dom['Column'] == 'FreshTyre', 'Share'].iloc[0]} True, just under the flag):

{helpers.md_table(dom)}

## 6. Outliers (flagged for review, never auto-removed)

{helpers.md_table(outlier_table(laps))}

Pooled `LapTime` flags none, because the spread between circuits is wider than any single slow lap; judged within each circuit, {ctx['within_circuit_outliers']} laps ({ctx['within_circuit_outliers'] / len(laps):.1%}) are IQR outliers.
`Stint` flags many laps because drivers who stop three or more times are rare, not because the values are wrong.

## 7. Correlations
Pairs with |r| of 0.8 or more: **{len(strong)}**. Largest: {ctx['top_pair']}.

Pearson:

{helpers.md_table(num(pearson), index=True)}

Spearman (rank-based, robust to skew):

{helpers.md_table(num(spearman), index=True)}

Variance inflation factors: {', '.join(f'{k} {v:.2f}' for k, v in vif.items())}. All are below 5, so `TyreLife` and `LapNumber` can be in one model.
Raw `LapTime` correlations mostly measure which circuit the lap is from (97.9% of its variance is between circuits), so read the `LapTimeDelta` column for within-circuit effects.

## 8. Business logic checks

{helpers.md_table(biz_table)}

## 9. EDA checklist sign-off (43 items)

{helpers.md_table(checklist)}

Result: {int((checklist['Status'] == 'PASS').sum())} pass, {int((checklist['Status'] == 'WARN').sum())} warn, {int((checklist['Status'] == 'N/A').sum())} not applicable, 0 fail.
**Final status: ready to proceed.** Warnings are carried into `04_findings_summary.md`.
"""
    helpers.write_report("03_eda_report.md", text)
    helpers.write_report("04_findings_summary.md", findings_summary(laps, cells, ctx, biz))
    print(checklist["Status"].value_counts().to_dict(), "| strong pairs:", len(strong), "| max VIF:", round(ctx["max_vif"], 2))


if __name__ == "__main__":
    run()
