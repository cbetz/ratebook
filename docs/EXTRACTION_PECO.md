# First extraction: PECO Rate R — and what one PDF can and can't tell you

The plan: parse PECO's residential tariff PDF with an LLM, run the result through the engine, and
see how close we get to a real bill. We built the pipeline and ran it. The extraction worked on
the first pass — and the bill-match revealed something more important than a passing demo, which
is the whole reason this project exists.

## What we ran

The pipeline (`ratebook_data.extract`) is two steps:

1. **Extractor** — Claude with structured output (`output_config.format`, the
   `EXTRACTION_SCHEMA`) reads the PECO Rate R tariff sheet natively (Supplement 21, eff.
   2026-01-01; source on the URDB record) and returns a schema-shaped record.
2. **Converter + validator** — a *deterministic* pass (`extracted_to_tariff`,
   `grade_extraction`) turns the record into a priceable `Tariff` and checks it for arithmetic
   and structural consistency, reusing the engine's own `ratebook.validate` checks. "Valid"
   therefore means the same thing to the eval harness and to the rate engine.

The validator is plain code, not a second model — it checks the engine-relevant invariants
(tier boundaries partition, charges are well-formed, the priced numbers match a golden record
when one is supplied). A separate model-based grading pass that *re-reads the source PDF* is a
planned addition, not what the committed pipeline does today.

## What the extractor got right

From the PECO Rate R sheet, verbatim:

| Field | Extracted | On the sheet |
|---|---|---|
| Fixed Distribution Service Charge | **$11.30/month** | ✅ |
| Fixed charge, former off-peak meters | $2.19/month (flagged separately) | ✅ |
| Variable Distribution Service Charge | **$0.10276/kWh**, flat, all kWh | ✅ |
| Minimum charge | $11.30/month (= fixed) | ✅ |
| Tiered / TOU | no / no | ✅ |
| Self-assessed confidence | 0.95 | — |

It also classified the **components** correctly: distribution is the only thing priced on this
sheet. Generation ("Energy Supply Charge — refer to the Generation Supply Adjustment,
Procurement Class 1") and transmission ("Transmission Service Charge shall apply") are *named
but priced in separate documents*. And it captured all nine riders that apply with no number on
the sheet (State Tax Adjustment Clause, DSIC, Nuclear Decommissioning, Universal Service Fund,
Non-Bypassable Transmission, Energy Efficiency & Conservation, Fiber Affiliate Revenue
Surcharge, COVID-19 Uncollectible, Consumer Education). We verified that component split by hand
against the PDF.

## The finding: a rate sheet is not a bill

PECO Rate R, the actual filed tariff, prices the **distribution** component only:
`$0.10276/kWh + $11.30/month`. At 600 kWh that is **$72.96**.

URDB's record for the same plan carries a single bundled rate of `$0.21884/kWh`
(`0.20513 + 0.01371`). At 600 kWh that is **$142.60**.

The difference is **$69.65 — the filed sheet sits 48.8% below URDB's bundled figure** — and that
gap is exactly the generation + transmission + riders the rate sheet does not price (the actual
bill below confirms the ~50/50 split directly). URDB's number is an all-in snapshot
from some past quarter, with distribution, generation, and transmission summed into one figure
that goes stale the moment PECO's quarterly Price to Compare changes. This is the "your app lied
about my bill / riders live in prose" thesis, made concrete on a single real plan.

To reproduce a real PECO bill, you need four things, and the rate sheet is one:

1. **Distribution** — `$0.10276/kWh + $11.30/mo` ✅ (extracted here, engine-priced, exact).
2. **Generation** — the residential Price to Compare set by the Generation Supply Adjustment,
   Procurement Class 1 (a separate PECO filing, separate cadence), or the customer's competitive
   supplier rate if they shop. **The single largest missing line item.**
3. **Transmission** — the Transmission Service Charge (default-service customers).
4. **Riders** — per-unit values for the nine listed surcharges, each from its own filing.
   Individually small; collectively enough to blow a 2% match.

The schema captures this decomposition on purpose (`components_priced`,
`components_referenced_only`, `riders`), so the engine prices what is on the sheet and the caller
stays honest about what is still missing — rather than collapsing the bill into one bundled
number that hides which components (about half of it, here) are or aren't included.

## The validator earned its keep on day one

The deterministic validator caught a real defect — not in the extraction, but in our
**converter**: the PECO sheet lists two fixed charges ($11.30 standard, $2.19 for legacy "former
off-peak" meters) that are **mutually exclusive**, and the first converter blindly summed every
fixed charge (it would have billed $13.49). We added an `applies_to: standard | alternative`
field to the schema and a converter guard that drops alternative-meter charges; a regression
test pins it. This is the case for eval-first extraction in miniature: a structured check found a
bug a human skim missed.

## Engine validation: the real bill, reproduced to a fraction of a cent

We then got the actual bill — PECO statement for the 04/28–05/28/2026 service period (30 days,
**1,244 kWh**, **$276.35** total) — and used it to validate the engine end-to-end. It confirmed
the prediction that the rate sheet is about half the bill:

| Bill section | Amount | Share |
|---|---|---|
| PECO Electric **Delivery** (distribution) | $139.27 | 50.4% |
| PECO Electric **Supply** (generation + transmission) | $137.14 | 49.6% |
| Taxes & fees | −$0.06 | — |

The bill's own line items:

| Component | Rate | Charge | Source |
|---|---|---|---|
| Distribution | $0.10276/kWh | $127.83 | **the tariff PDF we extracted** ✅ |
| Customer charge | — | $11.29 | tariff PDF ($11.30 on sheet; bill $11.29 — 1¢) |
| DSIC rider | — | $0.15 | separate filing |
| Generation | $0.10237/kWh | $127.35 | Price to Compare (separate) |
| Transmission | $0.00787/kWh | $9.79 | separate |
| State tax adjustment | — | −$0.06 | separate |

The distribution rate the extractor pulled from the tariff sheet (`$0.10276/kWh`) reproduces the
bill's distribution line **exactly** (1,244 × 0.10276 = $127.83). Feeding **all** components to
the engine over the 30-day, 1,244-kWh period yields **$276.352** against the actual **$276.35** —
a **0.0007% error**, far inside the 2% bar (`test_billmatch_peco.py`; rate/usage facts only, no
account or address committed).

**What this proves and what it doesn't.** It proves the rate engine is correct: given a bill's
components, it reconstructs the total to the penny. It does **not** yet prove end-to-end
extraction — the distribution component came from the extracted tariff PDF, but the
generation/transmission/rider values came from the bill itself. Sourcing those from utility data
(so a bill can be reproduced without already having the bill) is the next data-plant milestone.

## Status

- ✅ PDF → structured extraction → engine, with the distribution component validated against a
  real bill's distribution line.
- ✅ Deterministic converter + validator runs and caught a real bug.
- ✅ Engine bill-match: given all components, reproduces a real bill to a fraction of a cent.
- ⏭️ Next: source generation/transmission/riders from utility documents so bill-match runs from
  extraction alone; add a model-based grading pass that re-reads the source PDF.

The honest headline for an eventual write-up: *we re-parsed PECO's Rate R sheet with an LLM and
discovered the sheet is ~half the bill — here's the other half that every "we have the rates"
dataset silently bundles into one number that's already stale — and our engine reproduces an
actual PECO bill to the penny once it has all the pieces.*
