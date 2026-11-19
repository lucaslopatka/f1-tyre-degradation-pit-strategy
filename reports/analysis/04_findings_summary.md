# 04. EDA findings summary (workflow: programmatic-eda)

Dataset: cleaned 2026 race laps (15,206 rows). Date: 2026-11-19. Analyst: Claude with the project author.
Full report: `03_eda_report.md`.

## Dataset at a glance
- **Rows and grain:** 15,206 rows; one row = one clean lap by one driver; 19 circuits, 854 stints.
- **Analysis range:** the 2026 season, rounds 1 to 19 (São Paulo dropped as a wet race).
- **Overall data quality: Good.** No nulls, no duplicates, every range and consistency guarantee passes. The caveats below are about coverage, not errors.

## Top quality issues

**1. Thin circuit-compound cells**
- **What:** 7 of 57 cells have fewer than 4 stints (Shanghai C4; Suzuka C3; Montréal C3; Silverstone C3; Baku C3; Singapore C3; Mexico City C3) and 5 more have 4 to 7.
- **Impact:** no slope can be estimated for those cells; the decision rule cannot cover them.
- **Recommended action:** report them as not estimable; do not fill them in.
- **Owner:** analyst.

**2. Mexico City is truncated**
- **What:** laps 57 to 71 are missing from the API; clean tyre ages stop near 43 laps.
- **Impact:** its slope is extrapolated if used for a full-distance strategy.
- **Recommended action:** accept and state it as a limitation (done by the author, 2026-11-19).
- **Owner:** business stakeholder (author).

**3. Dirty-air laps are still in the data**
- **What:** the traffic filter is deferred to v2; 200 laps are still IQR outliers within their own circuit.
- **Impact:** traffic-limited laps can inflate slopes.
- **Recommended action:** keep as a documented limitation; add the filter in v2.
- **Owner:** analyst.

**4. Race lap and tyre age are confounded**
- **What:** laps get faster by 0.037 s per race lap; raw lap time falls with tyre age.
- **Impact:** a model without race lap would report negative degradation.
- **Recommended action:** keep `LapNumber` in the model; the variance inflation factors (at most 1.30) show it can be separated.
- **Owner:** analyst.

**5. The 25% wet cutoff is a default**
- **What:** chosen without data; at 10% two more circuits drop, at 40% São Paulo returns.
- **Impact:** changes which circuits are covered.
- **Recommended action:** keep 25% and report the sensitivity.
- **Owner:** business stakeholder (author).

## What looks good
- 0 missing values and 0 duplicate laps in the cleaned data.
- No pair of features is strongly correlated (largest |r| is 0.46), so features can share a model.
- Every clean lap maps to a C1 to C5 compound; every stint has one compound and at least 5 laps.
- Every count reconciles between raw, cleaned and excluded laps (report 01).

## Next step
- [x] Data is ready to proceed to the next analysis (pit-lane loss, then the degradation model).
- [ ] A data fix is needed.
- [ ] Further investigation is needed.
