# First extraction: PECO Rate R — and what one PDF can and can't tell you

Sprint 0 item 4 (and the honest write-up, item 6). The plan was: parse PECO's residential
tariff PDF with an LLM, run it through the engine, reproduce a real bill within 2%. We built
the pipeline and ran it. The extraction worked on the first pass. The bill-match revealed
something more important than a passing demo — and it's the whole reason this project exists.

## What we ran

A two-pass, eval-harnessed pipeline (`ratebook_data.extract`):

1. **Extractor** — Claude with structured output (`output_config.format`, the
   `EXTRACTION_SCHEMA`) reads the PECO Rate R tariff sheet (Supplement 21, eff. 2026-01-01;
   `data/pdfs/peco_rate_r_2026-01-01.pdf`, source on the URDB record).
2. **Grader** — an *independent* Claude pass that re-reads the source and checks the
   extraction for arithmetic consistency, correct component classification, and whether a full
   bill can even be reproduced from this document.

The deterministic converter (`extracted_to_tariff`) and grader (`grade_extraction`) reuse the
engine's own `ratebook.validate` checks, so "valid" means the same thing to the extractor's
grader and to the rate engine.

## What the extractor got right

From the PECO Rate R sheet, verbatim:

| Field | Extracted | On the sheet |
|---|---|---|
| Fixed Distribution Service Charge | **$11.30/month** | ✅ |
| Fixed charge, former off-peak meters | $2.19/month (flagged separately) | ✅ |
| Variable Distribution Service Charge | **$0.10276/kWh**, flat, all kWh | ✅ |
| Minimum charge | $11.30/month (= fixed) | ✅ |
| Tiered / TOU | no / no | ✅ |
| Confidence | 0.95 | — |

It also correctly classified the **components**: distribution is the only thing priced on this
sheet. Generation ("Energy Supply Charge — refer to the Generation Supply Adjustment,
Procurement Class 1") and transmission ("Transmission Service Charge shall apply") are *named
but priced in separate documents*. And it captured all nine riders that apply with no number
on the sheet (State Tax Adjustment Clause, DSIC, Nuclear Decommissioning, Universal Service
Fund, Non-Bypassable Transmission, Energy Efficiency & Conservation, Fiber Affiliate Revenue
Surcharge, COVID-19 Uncollectible, Consumer Education).

The independent grader confirmed all of this — `arithmetic_consistent: true`,
`component_classification_correct: true` — and returned `sufficient_for_full_bill: false`.

## The finding: a rate sheet is not a bill

PECO Rate R, the actual filed tariff, prices the **distribution** component only:
`$0.10276/kWh + $11.30/month`. At 600 kWh that is **$72.96**.

URDB's record for the same plan carries a single bundled rate of `$0.21884/kWh`
(`0.20513 + 0.01371`). At 600 kWh that is **$142.60**.

The difference is **$69.65 — 48.8% of the bill** — and it is exactly the generation +
transmission + riders that the rate sheet does not price. URDB's number is someone's
all-in snapshot from some past quarter, with distribution, generation, and transmission summed
into one figure that goes stale the moment PECO's quarterly Price to Compare changes. This is
the "your app lied about my bill / riders live in prose" thesis, made concrete and quantified
on the founder's own utility.

To reproduce a real PECO bill within 2%, you need four things, and the rate sheet is one:

1. **Distribution** — `$0.10276/kWh + $11.30/mo` ✅ (extracted here, engine-priced, exact).
2. **Generation** — the residential Price to Compare set by the Generation Supply Adjustment,
   Procurement Class 1 (a separate PECO filing, separate cadence), or the customer's
   competitive supplier rate if they shop. **The single largest missing line item.**
3. **Transmission** — the Transmission Service Charge (default-service customers).
4. **Riders** — per-unit values for the nine listed surcharges, each from its own filing.
   Individually small; collectively enough to blow a 2% match.

The schema captures this decomposition on purpose (`components_priced`,
`components_referenced_only`, `riders`), so the engine prices what is on the sheet and the
caller stays honest about what is still missing — rather than quietly serving a 49%-low number
the way a single bundled rate would.

## The eval harness earned its keep on day one

The independent grader caught a real defect — not in the extraction, but in our **converter**:
the PECO sheet lists two fixed charges ($11.30 standard, $2.19 for legacy "former off-peak"
meters) that are **mutually exclusive**, and the first converter blindly summed every fixed
charge (it would have billed $13.49). The grader flagged the exact failure and recommended a
structured qualifier. We added an `applies_to: standard | alternative` field to the schema and
a converter guard that drops alternative-meter charges; a regression test pins it. This is the
case for eval-first extraction in miniature: the second pass found a bug the first pass and a
human skim both missed.

## Status

- ✅ PDF → structured extraction → engine, validated end-to-end. The distribution component is
  exact (`$0.10276/kWh + $11.30/mo`), and the PECO Rate R record round-trips from the corpus
  through the engine (cross-checked against PySAM elsewhere).
- ✅ Two-pass pipeline (extractor + independent grader) runs and grades honestly.
- ⬜ **Literal "reproduce Chris's bill within 2%"** needs three inputs the rate sheet doesn't
  contain: the current residential Price to Compare, the transmission charge, and the rider
  values — plus Chris's actual last-month kWh and total. With those, the engine already has
  everything it needs (`estimate_bill` on the summed-component tariff); it's a data-gathering
  step, not an engine step.

The honest headline for the launch post writes itself: *we re-parsed PECO's Rate R sheet with
an LLM, the eval passed, and we discovered the sheet is 51% of the bill — here's the other
49% that every "we have the rates" dataset silently bundled into one number that's already
stale.*
