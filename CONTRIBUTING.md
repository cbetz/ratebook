# Contributing to Ratebook

Thanks for being here. Ratebook is an open rate engine for the electrified home: an openly
licensed database of US electricity tariffs, a deterministic rate-calculation engine, and an MCP
server, so any app, device, or agent can answer *"what will this kWh cost me, and when should I
charge?"*

The most valuable thing you can contribute is **a tariff correction** — telling us where a rate in
the corpus is wrong or stale, with the evidence to prove it. That path is documented in full below.
But fixes to the engine, the data plant, the MCP server, the TypeScript port, and the Home Assistant
integration are all welcome too.

This guide is practical and assumes nothing. If a step here is wrong or unclear, that itself is worth
a PR.

## Ground rules

- **Be excellent to each other.** Assume good faith, keep it about the work.
- **Correctness is the product.** This engine answers "what will my bill be?" A wrong answer is a
  user being told their power bill is something it isn't. Every change is held to that bar.
- **Small, focused PRs.** One logical change per pull request. A 40-line PR gets reviewed today; a
  900-line PR waits for a quiet weekend.

## Local setup

You need **Python 3.12+**, [uv](https://docs.astral.sh/uv/), and (for the TypeScript engine)
[pnpm](https://pnpm.io/).

```sh
git clone https://github.com/cbetz/ratebook
cd ratebook

uv sync                    # install all workspace packages + dev tools into .venv
```

That single `uv sync` gives you the whole Python side: the rate engine (`packages/ratebook`), the
data plant (`packages/ratebook-data`), and the MCP server (`packages/ratebook-mcp`).

The TypeScript engine port (`packages/ratebook-ts`) is a separate pnpm package — it is intentionally
excluded from the uv workspace:

```sh
pnpm -C packages/ratebook-ts install
```

A few commands you'll use constantly:

```sh
uv run ratebook-data urdb  # download the URDB bulk CSV → data/raw/, load into data/ratebook.duckdb
uv run ratebook-mcp        # run the MCP server (stdio)
```

## Running the tests and linter

Run all of these before you open a PR. CI runs the same set, so checking locally first saves a round
trip.

```sh
uv run pytest              # Python tests (engine, data plant, MCP)
uv run ruff check .        # lint

pnpm -C packages/ratebook-ts test   # TypeScript engine + cross-engine vectors
```

Notes:

- The rate engine is validated against [NREL PySAM](https://github.com/NREL/pysam)'s `utilityrate5`
  as an oracle. PySAM is a test-only dependency — those tests skip cleanly if it isn't installed, so
  a plain `uv sync` + `uv run pytest` works without it. To run the oracle checks yourself, install
  the validation group: `uv sync --group validation`.
- The engine is also property-tested with [Hypothesis](https://hypothesis.readthedocs.io/). If a
  Hypothesis run finds a falsifying example, please include it (Hypothesis prints a reproducer) in
  your issue or PR.

## The highest-value contribution: a tariff correction

Ratebook is only as trustworthy as its tariffs. Utilities re-file rates constantly, and the seed
corpus (derived from the CC0 [U.S. Utility Rate Database](https://apps.openei.org/USURDB/)) goes
stale the moment a tariff sheet is reissued. **Reporting a wrong or stale rate is the single most
useful thing you can do here.** You don't need to write any code to do it.

Open an issue titled `tariff correction: <utility> — <plan>` and include:

1. **Utility** — the name as it appears in the corpus (e.g. `Pacific Gas & Electric Co`).
2. **Plan / rate code** — the schedule identifier (e.g. `E-TOU-C`, `Residential Service (R)`).
3. **Source PDF URL** — a link to the utility's *official* filed tariff sheet that establishes the
   correct value. A direct PDF link is ideal; this is the document a reviewer will check against, so
   it has to be authoritative (the utility's own tariff book, a PUC filing), not a summary or a
   third-party rate-comparison site.
4. **Observed vs. expected** — what Ratebook currently produces and what the source PDF says it
   should be. Be specific: the field, the wrong value, the correct value (e.g. *"fixed charge shows
   `0.79343`/day; the Jan 1 2026 sheet, p. 3, lists `0.85100`/day"*). If it's a calculated bill that
   came out wrong, give the inputs (usage kWh, billing window) and both totals.
5. **Effective date**, if the correction is a re-filing rather than an extraction error — when the
   new rate took effect.

### Make it stick: add a golden-set / test addition

A correction is good. A correction *with a test* is permanent — it can never silently regress.

The data plant carries a **golden set**: tariffs paired with their authoritative source PDF and a
hand-checked `ground_truth` record (`packages/ratebook-data/golden/manifest.json`). The fields you'd
include in your correction issue — utility, plan name, source URL, and the corrected structural
values (sector, tiered/TOU, period and tier counts, fixed charge, energy rate) — are exactly the
shape of a golden entry. If you can add or fix the matching golden record alongside your report,
that's the gold standard: it turns "this one rate is wrong" into "the engine is now checked against
the right answer forever."

For an engine bug specifically (a tariff that *is* in the corpus but bills wrong), the convention is
to add a focused regression test that fails before your fix and passes after. See
`packages/ratebook/tests/test_review_regressions.py` for the pattern: a short comment naming the bug,
a minimal tariff that reproduces it, and an assertion on the exact corrected number.

We'd genuinely rather receive a plain, well-evidenced issue than nothing because you weren't sure how
to write the test. Report it; we'll help land the golden/test addition.

## The two engines must never diverge

This is the most important invariant in the repo.

There are two implementations of the rate engine — Python (`packages/ratebook`) and TypeScript
(`packages/ratebook-ts`) — and **they must produce byte-for-byte identical results**. Both read the
*same* golden JSON vectors and must reproduce every expected bill exactly:

```
packages/ratebook/tests/vectors/v0_bills.json
```

The vectors are generated by the Python side and checked by both:

- Python: `packages/ratebook/tests/test_vectors.py`
- TypeScript: `packages/ratebook-ts/test/vectors.test.ts`

The discipline that makes this hold across two languages: money and energy are exact decimals
(`Decimal` in Python, `decimal.js` in TS) — **never** floating-point `number` — and they serialize to
the identical canonical string form. If you find yourself reaching for a `float`, stop; that's how
the engines drift apart.

### Regenerating the vectors

Any change to the engine's behavior (a fix, a new charge type, a new test case) means the shared
vectors have to be regenerated from the Python side and committed:

```sh
uv run python packages/ratebook/tests/generate_vectors.py
```

Then run **both** test suites and commit the updated `v0_bills.json`:

```sh
uv run pytest
pnpm -C packages/ratebook-ts test
```

If you change the Python engine and the TypeScript vector test goes red, that is the invariant doing
its job — port the same change to TypeScript (or fix the divergence) before you open the PR. A PR
that updates one engine's output without the other will be asked to reconcile them.

## Code style

- **Python 3.12+.** Modern syntax is fine and encouraged (`X | None`, `match`, etc.); the codebase
  targets `py312`.
- **Ruff is the linter and formatter of record.** Config lives in the root `pyproject.toml`
  (line length 100; rule sets `E, W, F, I, UP, B, SIM, RUF`). Run `uv run ruff check .` and fix what
  it flags. `uv run ruff format .` will format.
- **The engine is pure and deterministic.** `packages/ratebook` does no I/O, has no runtime
  dependencies, and given the same inputs always returns the same outputs. Keep it that way: no
  network, no clock reads, no randomness, no `float`. Side effects and data fetching belong in the
  data plant (`packages/ratebook-data`), not the engine.
- **Type hints** on public functions, and a `py.typed` marker is shipped — keep the packages
  type-clean.
- Prefer clear names and small functions over comments; when a comment earns its place, explain
  *why*, not *what*.

## Pull request conventions

- **Keep PRs small and single-purpose.** Split unrelated changes.
- **Tests are required** for any behavior change — and for engine changes, that includes regenerated
  vectors (see above). A bug fix should come with a regression test that fails without the fix.
- **Green before review.** `uv run pytest`, `uv run ruff check .`, and the TS suite should all pass.
- **Write a useful description.** What changed, why, and how you verified it. Link the issue you're
  closing.
- **Commit messages, conventional-ish.** A short imperative subject prefixed by type is plenty:
  `fix: …`, `feat: …`, `data: …`, `docs: …`, `test: …`, `refactor: …`. Example:
  `fix(engine): apply seasonal tier reset at billing-window boundary`.

### Developer Certificate of Origin (DCO)

Contributions are accepted under the project's licenses ([Apache-2.0](LICENSE) for code,
[CC0-1.0](LICENSE-DATA) for published data). By contributing, you certify that you wrote the change
or otherwise have the right to submit it under those terms — i.e. you agree to the
[Developer Certificate of Origin](https://developercertificate.org/).

Sign off every commit with the `-s` flag, which appends a `Signed-off-by` line:

```sh
git commit -s -m "fix(engine): apply seasonal tier reset at billing-window boundary"
```

The `Signed-off-by` line is generated from your configured `git` identity, so make sure your
`user.name` and `user.email` are set the way you want them to appear:

```
Signed-off-by: Your Name <your git identity>
```

(Forgot to sign off? `git commit --amend -s` fixes the last commit; for a series, rebase and re-sign.)

## Reporting a security issue

Please **do not** open a public issue for security vulnerabilities. Report them privately via GitHub:
go to the repository's **Security** tab and choose **Report a vulnerability** (Private Vulnerability
Reporting). That keeps the details confidential while we work on a fix.

## Questions

Open a [GitHub Discussion or issue](https://github.com/cbetz/ratebook). Maintained by
[@cbetz](https://github.com/cbetz). Welcome aboard.
