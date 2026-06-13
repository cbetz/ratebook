# Ratebook

The open rate engine for the electrified home — an openly licensed database of US electricity tariffs, an open-source rate-calculation engine, and an MCP server, so any app, device, or agent can answer "what will this kWh cost me, and when should I charge?"

> Status: pre-release. See `docs/ROADMAP.md` for the plan.

## Development

Python 3.12+, [uv](https://docs.astral.sh/uv/) workspace with three packages:
`packages/ratebook` (rate engine), `packages/ratebook-data` (data plant),
`packages/ratebook-mcp` (MCP server). Plus `packages/ratebook-ts` — the TypeScript engine port
(pnpm + vitest), held to the Python engine via shared JSON test vectors.

```sh
uv sync                    # install all workspace packages + dev tools
uv run pytest              # Python tests
uv run ruff check .        # lint
uv run ratebook-data urdb  # download URDB bulk CSV → data/raw/, load into data/ratebook.duckdb
uv run ratebook-mcp        # run the MCP server (stdio)

pnpm -C packages/ratebook-ts install && pnpm -C packages/ratebook-ts test   # TS engine + cross-engine vectors
```

The two engines must never diverge: both reproduce
`packages/ratebook/tests/vectors/v0_bills.json` byte-for-byte. Regenerate it with
`uv run python packages/ratebook/tests/generate_vectors.py`.

## License

Code is licensed under [Apache-2.0](LICENSE). Published datasets are dedicated to the
public domain under [CC0-1.0](LICENSE-DATA). The seed corpus derives from the
[U.S. Utility Rate Database](https://apps.openei.org/USURDB/) (CC0).
