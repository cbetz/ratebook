# Ratebook — contributor & agent guide

The open rate engine for the electrified home: an openly licensed database of US electricity
tariffs (parsed from utility PDFs by eval-harnessed LLM pipelines), a deterministic
rate-calculation engine, and an MCP server — so any app, device, or agent can answer "what will
this kWh cost me, and when should I charge?"

Status: **pre-release.** See `docs/ROADMAP.md` for what's shipped and what's next.

## Repository layout (uv + pnpm monorepo)

- `packages/ratebook` — the rate engine. Pure, deterministic functions over a `Tariff` data
  model (`estimate_bill`, `estimate_annual`, `cheapest_charge_window`, `supported`). No I/O.
- `packages/ratebook-data` — the data plant: URDB loader, the LLM extraction pipeline
  (`extract.py`), and the golden-set scorecard (`golden.py`).
- `packages/ratebook-mcp` — the MCP server exposing `lookup_tariff`, `estimate_bill`,
  `compare_plans`, `best_charge_window` over the corpus + engine.
- `packages/ratebook-ts` — the TypeScript engine port (`@ratebook/engine`), kept in lockstep
  with the Python engine via shared JSON test vectors.
- `packages/ratebook-homeassistant` — a Home Assistant custom integration (electricity-price +
  cheapest-charge-window sensors) over the engine.

## Development

```sh
uv sync                    # install all workspace packages + dev tools
uv run pytest              # Python tests
uv run ruff check .        # lint
uv run ratebook-data urdb  # download URDB bulk CSV → data/raw/, load into data/ratebook.duckdb
uv run ratebook-mcp        # run the MCP server (stdio)

pnpm -C packages/ratebook-ts install && pnpm -C packages/ratebook-ts test   # TS engine + vectors
```

LLM extraction (`ratebook-data`'s `extract` extra) additionally needs the `anthropic` SDK and an
API key; the engine, MCP, and HA paths never require it.

## Conventions

- Python 3.12+, uv workspace, pytest (+ hypothesis for the engine's property tests), ruff.
  TypeScript: pnpm, vitest.
- **The rate engine is pure functions, deterministic, boring, and bulletproof.** Correctness
  bugs here are customer-facing "your app lied about my bill" failures — every change is
  property-tested and the engine is cross-validated against NREL's PySAM `utilityrate5`.
- **The two engines must never diverge.** Both reproduce
  `packages/ratebook/tests/vectors/v0_bills.json` byte-for-byte; regenerate with
  `uv run python packages/ratebook/tests/generate_vectors.py`.
- **Honesty about uncertainty is the brand.** Every record should carry its source PDF URL,
  effective date, extraction confidence, and last-verified date. Never claim coverage or
  accuracy that hasn't been eval'd; "unknown" is a first-class answer. The accuracy scorecard is
  published content, not a marketing surface.
- Keep `docs/ROADMAP.md` current at the end of each working session: what shipped, what's next,
  open questions.

## Data sources (all free, self-serve, no gatekeepers)

- URDB bulk download (`usurdb.csv.gz`) — CC0, no key; the seed corpus and the eval golden set.
- NLR/OpenEI API — free key at developer.nlr.gov.
- EIA API + Form 861 — free key; the authoritative universe of US utilities + customer counts.
- Utility tariff books + state PUC e-filing systems (CPUC, NYPSC, PUCT…) — public records.
- PySAM (`pip install nrel-pysam`) — reference bill calculator for engine validation.

## License

Code is Apache-2.0 (`LICENSE`); published datasets are CC0-1.0 (`LICENSE-DATA`), matching the
URDB seed corpus. See `CONTRIBUTING.md` for how to contribute — the highest-value contribution
is a tariff correction.
