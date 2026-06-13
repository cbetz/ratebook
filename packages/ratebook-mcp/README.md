# ratebook-mcp

MCP server exposing the Ratebook tariff database and rate engine to apps, devices, and agents.
It answers "what will this kWh cost me, and when should I charge?" over the loaded corpus
(`data/ratebook.duckdb`) and the deterministic `ratebook` engine.

## Tools

| Tool | What it does |
|---|---|
| `lookup_tariff(query, sector, active_only, limit)` | Find tariffs by utility name, EIA id, or label — freshest first, with provenance (source URL, effective date, last update) and whether the engine can fully price each. |
| `estimate_bill(label, start_date, days, total_kwh \| hourly_kwh)` | Price one tariff over a billing window. `total_kwh` suffices for flat/tiered/seasonal plans; time-of-use plans need `hourly_kwh` (length `days*24`). Returns the full result, with a typed `refusal` when it can't be priced. |
| `compare_plans(labels, start_date, days, total_kwh \| hourly_kwh)` | Price several tariffs over the same usage and rank cheapest-first; unpriceable plans are listed with their refusal. |
| `best_charge_window(label, start_date, days, charge_hours, kwh_to_add)` | The cheapest contiguous block to add load (e.g. EV charging), using the tariff's time-of-use marginal price signal. |

Every Decimal is returned as a string (the engine's canonical wire form), so responses are
directly JSON-serializable. "Unknown" is a first-class answer: an unpriceable plan returns a
typed refusal, never a wrong number.

## Run

```sh
uv run ratebook-data urdb     # build data/ratebook.duckdb first (once)
uv run ratebook-mcp           # stdio MCP server
```

Set `RATEBOOK_DB` to point at a corpus elsewhere. Register with an MCP client (e.g. Claude
Desktop / Code) as a stdio server running `ratebook-mcp` from a directory containing the DB:

```json
{
  "mcpServers": {
    "ratebook": { "command": "uv", "args": ["run", "ratebook-mcp"], "cwd": "/path/to/ratebook" }
  }
}
```

The logic lives in `ratebook_mcp.service` (unit-testable without a running server); `server.py`
is the thin FastMCP binding.
