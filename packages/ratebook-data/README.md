# ratebook-data

The Ratebook data plant: source ingestion, DuckDB warehouse, and (eventually) versioned
Parquet/JSON dataset releases with full per-record provenance.

```sh
uv run ratebook-data urdb   # download usurdb.csv.gz → data/raw/, load into data/ratebook.duckdb
```

Every download is kept verbatim under `data/raw/` with a `.meta.json` provenance sidecar
(source URL, sha256, ETag, Last-Modified). The DuckDB `raw` schema is all-VARCHAR; typing
happens in transformations, never at ingest.
