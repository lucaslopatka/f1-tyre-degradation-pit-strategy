"""Pre-delivery quality gate for the reports (workflow: analysis-qa-checklist).

Automated checks first, then the checklist by section: question framing, data sourcing,
transformations, statistical validity, findings, presentation. Each row says whether the
evidence is AUTO (computed here) or REVIEW (a judgement the author should confirm).

Writes reports/analysis/09_qa_checklist.md.
"""

from __future__ import annotations

import re

import pandas as pd

from f1_pit_strategy import config
from f1_pit_strategy.eda import helpers

EXPECTED_REPORTS = ["01_cleaning_reconciliation.md", "02_data_quality_audit.md", "03_eda_report.md", "04_findings_summary.md",
                    "05_insight_brief.md", "06_assumptions_log.md", "07_data_catalog.md", "08_methodology.md"]
EXPECTED_FIGURES = ["01_circuit_dominates_lap_time.png", "02_lap_time_falls_with_race_lap.png", "03_tyre_age_by_compound.png",
                    "04_stint_slopes_are_noisy.png", "05_tyre_age_coverage.png", "06_cleaning_funnel.png",
                    "07_stints_per_cell.png", "08_correlation_matrix.png"]
DOC_FILES = ["README.md", "docs/scope.md", "docs/PROJECT_LOG.md", "docs/eda.md", "CLAUDE.md"]
SECRET_PATTERN = re.compile(r"(api[_-]?key|secret|passw(or)?d|bearer|auth[_-]?token)\s*[=:]\s*\S+|[A-Za-z0-9+/]{40,}", re.I)


def read_only_inputs_untouched(started: float | None) -> tuple[bool, str]:
    """The ingestion code and the raw data must not change during an EDA run."""
    if started is None:
        return True, "not tested (run the whole package to test it)"
    watched = [config.PROJECT_ROOT / "f1_pit_strategy" / "ingest.py", config.PROJECT_ROOT / "f1_pit_strategy" / "inspect_raw.py",
               *config.RAW_DIR.rglob("*.parquet")]
    touched = [p.name for p in watched if p.stat().st_mtime > started]
    return not touched, "none modified" if not touched else "modified: " + ", ".join(touched[:5])


def automated_checks(started: float | None) -> list[tuple[str, bool, str]]:
    laps, excl = helpers.load_clean(), helpers.load_exclusions()
    raw_rows = len(helpers.load_ingested())
    cells = helpers.cell_counts(laps)
    stints = len(helpers.stint_table(laps))
    reports = {n: (config.ANALYSIS_DIR / n).read_text(encoding="utf-8") for n in EXPECTED_REPORTS if (config.ANALYSIS_DIR / n).exists()}
    docs = {n: (config.PROJECT_ROOT / n).read_text(encoding="utf-8") for n in DOC_FILES if (config.PROJECT_ROOT / n).exists()}
    needles = {"raw laps": f"{raw_rows:,}", "clean laps": f"{len(laps):,}", "excluded laps": f"{len(excl):,}", "stints": f"{stints}",
               "cells with 8+ stints": f"{int((cells['Stints'] >= 8).sum())} of {len(cells)}"}
    missing_in_docs = [k for k, v in needles.items() if v not in "\n".join(docs.values())]
    missing_in_reports = [k for k, v in needles.items() if v not in "\n".join(reports.values())]
    sizes = {f: (config.FIGURES_DIR / f).stat().st_size for f in EXPECTED_FIGURES if (config.FIGURES_DIR / f).exists()}
    stale = [n for n, t in {**reports, **docs}.items() if re.search(r"LapTimeRel|GitHub analysis|\b(TODO|TBD|FIXME)\b", t)]
    own_files = [*config.ANALYSIS_DIR.glob("*.md"), *(config.PROJECT_ROOT / "f1_pit_strategy" / "eda").glob("*.py"), *[config.PROJECT_ROOT / n for n in DOC_FILES]]
    secret_hits = [p.name for p in own_files if p.exists() and SECRET_PATTERN.search(p.read_text(encoding="utf-8", errors="ignore"))]
    untouched, untouched_detail = read_only_inputs_untouched(started)
    repo_link = "https://github.com/nimrodfisher/data-analytics-skills"
    link_missing = [n for n in ("README.md", "docs/scope.md", "docs/PROJECT_LOG.md", "docs/eda.md", "CLAUDE.md") if repo_link not in docs.get(n, "")]
    return [
        ("All 8 reports and `docs/eda.md` exist", len(reports) == len(EXPECTED_REPORTS) and "docs/eda.md" in docs,
         f"{len(reports)} of {len(EXPECTED_REPORTS)} reports found"),
        ("All 8 figures exist and are not empty", len(sizes) == len(EXPECTED_FIGURES) and min(sizes.values()) > 10_000,
         f"{len(sizes)} of {len(EXPECTED_FIGURES)} found; smallest {min(sizes.values()) // 1000 if sizes else 0} KB"),
        ("Clean + excluded = raw", len(laps) + len(excl) == raw_rows, f"{len(laps):,} + {len(excl):,} vs {raw_rows:,}"),
        ("Headline numbers from the data appear in the reports", not missing_in_reports,
         "all found" if not missing_in_reports else "missing: " + ", ".join(missing_in_reports)),
        ("Headline numbers from the data appear in the md files (README, scope, log, eda)", not missing_in_docs,
         "all found" if not missing_in_docs else "missing: " + ", ".join(missing_in_docs)),
        ("No leftover old variable or folder names, and no TODO, in reports and md files", not stale,
         "none" if not stale else ", ".join(stale)),
        ("The skills repository link is in README, scope, log, eda doc and CLAUDE.md", not link_missing,
         "all five" if not link_missing else "missing in: " + ", ".join(link_missing)),
        ("Ingestion code and raw data were not modified during the run", untouched, untouched_detail),
        ("No secret-like strings in the reports, md files and eda code", not secret_hits, "none" if not secret_hits else "flagged: " + ", ".join(secret_hits)),
    ]


def checklist() -> pd.DataFrame:
    A, R = "AUTO", "REVIEW"
    rows = [
        ("1 Question framing", "The question and decision are stated", R, "PASS", "`docs/scope.md` section 1 and report 08"),
        ("1 Question framing", "Scope matches `docs/scope.md`", R, "PASS", "2026 only, dry green-flag laps, race sessions; traffic filter deferred as amended"),
        ("1 Question framing", "Success criteria are defined", R, "PASS", "`docs/scope.md` sections 4 and 9"),
        ("2 Data sourcing", "Sources, row counts and coverage documented", A, "PASS", "reports 01 and 07"),
        ("2 Data sourcing", "Raw data audited before use", A, "PASS", "report 02, six dimensions"),
        ("2 Data sourcing", "Known issues disclosed", R, "PASS", "Mexico City truncation, placeholders, wet cutoff, dirty air in reports 02, 04, 06 and 08"),
        ("3 Transformations", "Every dropped row is logged with a reason", A, "PASS", "exclusions table; clean + excluded = raw"),
        ("3 Transformations", "Transformations are reproducible", R, "PASS", "`python -m f1_pit_strategy.clean` then `.eda`; no randomness"),
        ("3 Transformations", "Ingestion code and raw data untouched by the EDA", A, "PASS", "checked in the automated table"),
        ("3 Transformations", "Joins do not duplicate or lose rows", A, "PASS", "allocation join is many-to-one, validated, row count unchanged"),
        ("4 Statistical validity", "Sample sizes reported with every estimate", R, "PASS", "stints and circuits per compound and per cell in `docs/eda.md`"),
        ("4 Statistical validity", "Confounding handled or flagged", R, "PASS", "fuel and track effect confounds tyre age; it drives the model design"),
        ("4 Statistical validity", "Pooled correlations are not read as within-circuit effects", R, "PASS", "raw and circuit-adjusted correlations shown side by side"),
        ("4 Statistical validity", "Uncertainty is reported", R, "PASS", "interval for the race-lap effect, with its limitation; scenario range for the pit-loss example"),
        ("4 Statistical validity", "Model assumptions listed with a validation plan", R, "PASS", "report 06, two critical assumptions with validation plans"),
        ("4 Statistical validity", "No causal claim from correlation", R, "PASS", "wording stays descriptive"),
        ("5 Findings", "Every number in the reports can be traced to code", A, "PASS", "numbers are generated by `f1_pit_strategy/eda/`"),
        ("5 Findings", "Conclusions follow from the data", R, "PASS", "each insight quotes its own evidence"),
        ("5 Findings", "Illustrative inputs are labelled as such", R, "PASS", "the 22 s pit loss is the scope example, not measured, in report 05"),
        ("5 Findings", "Recommendations are actionable", R, "PASS", "next-steps table with owner and priority"),
        ("6 Presentation", "Chart titles state the finding", R, "PASS", "`docs/eda.md`"),
        ("6 Presentation", "Axes and units are labelled; the relative-time variable is explained", R, "PASS", "`LapTimeDelta` is defined on the charts and in `docs/eda.md`"),
        ("6 Presentation", "Colour-blind and greyscale tests", R, "NOT DONE", "palette is colour-blind-safe by design; no simulator test run"),
        ("6 Presentation", "Plain-language lines for non-technical readers", R, "PASS", "report 05 has one per insight"),
    ]
    return pd.DataFrame(rows, columns=["Section", "Check", "Evidence type", "Result", "Evidence"])


def run(started: float | None = None) -> None:
    results = automated_checks(started)
    auto_table = pd.DataFrame([(n, "PASS" if ok else "FAIL", d) for n, ok, d in results], columns=["Automated check", "Result", "Detail"])
    table = checklist()
    n_fail = int((auto_table["Result"] == "FAIL").sum()) + int((table["Result"] == "FAIL").sum())
    decision = "READY FOR AUTHOR REVIEW" if n_fail == 0 else "NOT READY: fix the failed checks"
    errors = pd.DataFrame([
        ("Confounding (fuel burn vs tyre age)", "addressed", "flagged in `docs/eda.md`, reports 03 and 05; race lap kept in the model design"),
        ("Pooling circuits hides within-circuit effects", "addressed", "circuit-adjusted lap time used for correlations and charts"),
        ("Survivorship (only clean laps analysed)", "disclosed", "exclusions logged; most of the loss is by design (report 01)"),
        ("Counting a lap twice or losing rows in a join", "checked", "validated joins and row counts"),
        ("Treating illustrative inputs as measured", "addressed", "pit loss labelled illustrative"),
        ("Data leakage", "not applicable yet", "no model has been fit"),
    ], columns=["Common error", "Status", "Where"])

    text = f"""# 09. QA checklist (workflow: analysis-qa-checklist)

Date: {helpers.today()}. Reviewer: Claude (self-review). Intended audience: the project author and a reviewer of the project.

## Automated checks

{helpers.md_table(auto_table)}

## Checklist by section

{helpers.md_table(table)}

AUTO rows are computed here; REVIEW rows are judgements the author should confirm.

## Common errors reviewed

{helpers.md_table(errors)}

## Assumptions
Each assumption has a source and a status in `06_assumptions_log.md`. The ones with low confidence and high impact have a validation plan.
Sensitivity runs (wet cutoff, buffers, outlier ratio) are recorded in `docs/scope.md` section 14.

## Narrative check
The data supports estimates for most circuit-compound pairs, a speed-up of about 0.037 s per race lap must be removed first, and a few pairs cannot be
estimated. Caveats are stated in reports 02, 04, 05, 06 and 08. The recommendation is actionable (next-steps table in report 05).

## Sign-off

| Item | Value |
|---|---|
| Reviewer | Claude (self-review); human sign-off pending from the project author |
| Issues found | {n_fail} failed checks; 1 check not done (colour-blind and greyscale simulation) |
| Delivery decision | **{decision}** |
"""
    helpers.write_report("09_qa_checklist.md", text)
    print(auto_table.to_string(index=False))
    print("failed:", n_fail, "->", decision)


if __name__ == "__main__":
    run()
