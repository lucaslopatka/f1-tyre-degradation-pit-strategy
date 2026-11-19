"""Run the whole EDA in order:  python -m f1_pit_strategy.eda

Reads data/raw and data/processed (never writes them). Writes reports/figures/,
reports/analysis/ and docs/eda.md.
"""

from __future__ import annotations

import time

from f1_pit_strategy.eda import assumptions, audit, insights, methodology, profile, qa, reconcile, visuals

STEPS = [
    ("cleaning reconciliation", reconcile.run),
    ("data-quality audit", audit.run),
    ("EDA profile and checklist", profile.run),
    ("charts and docs/eda.md", visuals.run),
    ("insight brief", insights.run),
    ("assumptions log and data catalog", assumptions.run),
    ("methodology", methodology.run),
]


def main() -> None:
    started = time.time()
    for name, step in STEPS:
        print(f"\n=== {name} ===", flush=True)
        step()
    print("\n=== QA gate ===", flush=True)
    qa.run(started)


if __name__ == "__main__":
    main()
