# Golden-set extraction scorecard

Snapshot: `usurdb-2026-06-13`. The golden set pairs URDB structured records (the reference) with
their source tariff PDFs. Each PDF was extracted by a Claude structured-output pass and the
result graded against the URDB record. This is the per-utility accuracy scorecard the project
publishes as content.

> **Provenance / reproducibility (read this first).** The numbers below come from an eval run
> over the `usurdb-2026-06-13` snapshot, and the per-pair graded results are committed at
> `packages/ratebook-data/golden/results.json`. The aggregate table regenerates from that data —
> run `uv run ratebook-data scorecard` — and a test
> (`test_committed_results_reproduce_documented_scorecard`) asserts the headline figures here
> match the committed results, so they can't silently drift. What is **not** yet a one-command
> step is re-running the *extraction* from the source PDFs (that needs the `extract` extra +
> network); regenerating the recorded grades live is the remaining roadmap item. Treat the
> figures as a committed, test-checked recorded result.

**Graded 18 of 20 selected pairs** — 2 unfetchable (LIPA 403, AEP Ohio 404; link rot). 0
extraction failures.

## Headline

| Metric | Score |
|---|---|
| Sector | 100% |
| Tiered (yes/no) | 100% |
| Time-of-use (yes/no) | 89% |
| Fixed charge amount | 78% |
| Arithmetic consistency | 100% |
| **Overall structural** | **92%** |

Verdicts: **7 pass, 11 pass-with-notes, 0 fail.**

But the raw "92%" undersells it, because the grading re-checked every extraction against its
source — and **every fixed-charge disagreement is the freshly-extracted PDF being correct and
URDB being stale or mislinked**, not an extraction error:

| Utility | Extracted (verified vs PDF) | URDB record | What's going on |
|---|---|---|---|
| DTE Electric | **$8.50** customer charge | $9.75 | URDB is pre-rate-case stale; `$9.75` appears nowhere in the current tariff book |
| Pepco | **$18.09** (Rate Year 2, eff. 2026-01-01) | $17.09 | URDB is one rate-year behind (RY1, eff. 2025) |
| Nevada Power | **$18.50** basic service charge | $18.00 | URDB stale; $18.50 matches both ORS-TOU and the parent RS schedule |
| Alabama Power | **$14.50** base charge | $16.00 | URDB reflects a different vintage |
| PacifiCorp UT | $12.00 + $0.16 Lifeline | $12.16 | both components extracted; URDB folds them into one — a presentation diff, not an error |

Two time-of-use disagreements:

- **PECO "Rate R - TOU"** — URDB says TOU; the extractor read the linked PDF and (correctly)
  said not-TOU, because **URDB's source URL for the TOU plan points at the non-TOU Rate R
  sheet**. The eval surfaced a URDB metadata-linking bug, not an extraction miss.
- **PacifiCorp UT** — the extractor flagged TOU because Schedule 1 carries an *optional* TOU
  rider; URDB correctly classifies the base schedule as non-TOU. A genuine (minor) extractor
  over-flag — the one disagreement that is actually the extractor's.

Net: of the field-level disagreements, **four are URDB being stale, one is a URDB source-linking
bug, one is a presentation difference, and one is a real extractor over-flag.** Read against the
source documents, the fresh extraction is *more* current than the reference it's graded
against — which is the entire disruption thesis, demonstrated across 18 utilities.

## The distribution-vs-bundled split generalizes

The PECO finding (a rate sheet prices distribution only; URDB carries a stale bundled number) is
not a one-off. Energy-rate relationship to the URDB record across the 18:

- **`distribution_only_vs_bundled`: 7** — PECO (×2), ComEd, DTE, Dominion, LADWP, PacifiCorp.
  These are restructured/retail-choice states where the sheet prices the wires component and
  generation lives in a separate Price-to-Compare document.
- **`matches`: 8** — mostly vertically-integrated utilities (PG&E, Duke, APS, SRP, Alabama,
  Nevada, We Energies) whose sheets are genuinely bundled, so the URDB bundled rate lines up.
- **`diverges`: 3** — Alabama, Eversource CT, Pepco — bundled-vs-bundled but a vintage/rider gap.

This is the map of where a single bundled number is safe (vertically integrated) versus where it
silently misstates the bill by ~half (restructured states) — exactly the coverage Ratebook
exists to fix.

## Per-utility detail

| Utility | Plan | Sec | Tier | TOU | Fixed | Rate vs URDB | Verdict |
|---|---|:--:|:--:|:--:|:--:|---|---|
| Pacific Gas & Electric | E-1 Residential Baseline | ✅ | ✅ | ✅ | ✅ | matches | pass |
| Pacific Gas & Electric | E-TOU-C Residential TOU | ✅ | ✅ | ✅ | ✅ | matches | pass-with-notes |
| PECO Energy Co | Residential Service (R) | ✅ | ✅ | ✅ | ✅ | distribution_only_vs_bundled | pass |
| PECO Energy Co | Residential Service (R) - TOU | ✅ | ✅ | ❌¹ | ✅ | distribution_only_vs_bundled | pass-with-notes |
| Commonwealth Edison | BES Residential | ✅ | ✅ | ✅ | ✅ | distribution_only_vs_bundled | pass-with-notes |
| DTE Electric | Residential D1 Full Service | ✅ | ✅ | ✅ | ❌² | distribution_only_vs_bundled | pass-with-notes |
| Duke Energy Carolinas | RS Residential | ✅ | ✅ | ✅ | ✅ | matches | pass-with-notes |
| Duke Energy Indiana | RS Residential | ✅ | ✅ | ✅ | ✅ | matches | pass |
| Alabama Power | Family Dwelling Service | ✅ | ✅ | ✅ | ❌² | diverges | pass-with-notes |
| Arizona Public Service | R-TOU-E 4–7pm | ✅ | ✅ | ✅ | ✅ | matches | pass |
| Salt River Project | E-23 Basic | ✅ | ✅ | ✅ | ✅ | matches | pass |
| Virginia Electric (Dominion) | Residential Schedule 1 | ✅ | ✅ | ✅ | ✅ | distribution_only_vs_bundled | pass-with-notes |
| LADWP | Residential R1A Zone 1 | ✅ | ✅ | ✅ | ✅ | distribution_only_vs_bundled | pass |
| Eversource CT (CL&P) | Rate 1 Residential | ✅ | ✅ | ✅ | ✅ | diverges | pass-with-notes |
| Pepco | Residential Schedule R | ✅ | ✅ | ✅ | ❌² | diverges | pass-with-notes |
| Nevada Power | ORS-TOU | ✅ | ✅ | ✅ | ❌² | matches | pass-with-notes |
| PacifiCorp (Utah) | Schedule 1 Residential | ✅ | ✅ | ❌³ | ✅⁴ | distribution_only_vs_bundled | pass-with-notes |
| Wisconsin Electric | Residential Rg 1 | ✅ | ✅ | ✅ | ✅ | matches | pass |

¹ URDB source URL mislinked to the non-TOU sheet. ² Extracted value is current; URDB is stale.
³ Optional TOU rider; extractor over-flagged. ⁴ $12.00 + $0.16 Lifeline; URDB folds to $12.16.

## How this was produced (and how it should be)

`packages/ratebook-data/golden/manifest.json` defines the pairs (label → source URL + URDB ground truth).
A one-time eval run extracted each PDF with `ratebook_data.extract` and recorded a structured
grade per pair (`sector_match`, `tiered_match`, `tou_match`, `fixed_charge_match`,
`arithmetic_consistent`, `rate_relationship`, `verdict`). Those grades are committed at
`packages/ratebook-data/golden/results.json`; `ratebook_data.golden.build_scorecard` /
`render_scorecard_md` aggregate them into the headline table (run `uv run ratebook-data
scorecard`). PDFs are not committed (re-fetchable utility documents).

**Remaining for a live freshness signal:** re-running the *extraction* from source PDFs on each
monthly snapshot (the `extract` extra + network) to regenerate `results.json` automatically — a
tracked roadmap item. The aggregate scorecard itself is already reproducible and test-checked
from the committed grades.
