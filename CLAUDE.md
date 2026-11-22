# F1 Tyre Degradation & Pit Strategy: instructions for Claude Code

## The project
**Question:** at a given circuit, under dry green-flag conditions, when does a two-stop
strategy beat a one-stop? Output is a per-circuit decision rule with a threshold
(two stops win when degradation beta > 12P / N^2), not a gallery of charts.

**Read `docs/scope.md` before doing anything.** It holds the locked scope, hypotheses
(H1-H5), variables, filter decisions, modelling approach, validation plan and the
amendments made after scope lock. **Read `docs/PROJECT_LOG.md` for current status and
next steps.**

## How to work on this project
- Python: pandas, statsmodels, scipy, matplotlib (data access through the FastF1 library; DuckDB was planned but is not used). All code, comments and docs in English.
- The author reads Python comfortably but is still building the habit of writing it
  unaided. Write code that can be defended line by line in an interview: small readable
  functions, the idiomatic pattern explained briefly with why it was chosen, and a note
  where a common alternative exists. Build independence; do not just hand over code.
- Rigor over complexity: avoid data leakage, check model assumptions, report uncertainty.
- Scope discipline: one narrow question. Side questions go in `docs/scope.md` section 13
  (future work), not into the code. Push back when the question starts to widen.
- Be direct and challenge weak ideas.
- Findings are framed around the decision they inform and its impact. Methods belong in
  an appendix.
- Keep the repo clean: clear structure, `requirements.txt`, reproducible runs.
- EDA and data-quality checks follow the workflows of [data-analytics-skills](https://github.com/nimrodfisher/data-analytics-skills), a collection of 31 reusable data-analyst workflows (EDA, data-quality audit, chart design, insight writing, documentation, QA), written as step-by-step instructions for AI assistants. Every chart is explained with a business and a statistical conclusion.

## Running the pipeline
```bash
source .venv/bin/activate
python -m f1_pit_strategy.ingest --round 1     # single round, test first
python -m f1_pit_strategy.ingest               # all completed rounds, skips existing
python -m f1_pit_strategy.inspect_raw          # validation report on data/raw
python -m f1_pit_strategy.clean                # clean laps + exclusions audit table
python -m f1_pit_strategy.eda                  # data-quality audit, EDA, charts, reports (docs/eda.md)
python -m f1_pit_strategy.pit_loss             # pit-lane loss P per circuit
python -m f1_pit_strategy.degradation          # degradation rate per circuit and compound
python -m f1_pit_strategy.decision             # one-stop or two-stop call, table and chart (docs/decision.md)
python -m f1_pit_strategy.validate             # calls vs real stop counts (docs/validation.md)
python -m f1_pit_strategy.metrics              # fit and residual metrics (docs/model_metrics.md)
```
Data access needs FastF1 >= 3.9 and an F1TV login. FastF1 stores its own login token
locally; it lasts about four days. Fallback source if that fails: OpenF1 (see scope.md
section 14).

## Hard rules
- **Never write credentials or tokens into any file in this repo, and never print them.**
  This repo is published on GitHub.
- Do not commit, push or `git init` unless asked.
- `data/raw/` and `cache/` are reproducible and gitignored; never edit them by hand.
- Every row excluded in cleaning is written to an audit table with a reason. No silent drops.
- Cleaning thresholds live in `f1_pit_strategy/config.py`, not inline.

## Keeping context in sync
At the end of each session, append an entry to `docs/PROJECT_LOG.md` (what was done,
decisions and why, what is next). If scope, data source or hypotheses change, update
`docs/scope.md` section 14 in the same session. The claude.ai Project "Personal Portfolio"
holds a copy of the scope doc; the author syncs it from a claude.ai chat.
