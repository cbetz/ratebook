"""Read tariffs back out of the loaded DuckDB corpus.

Bridges the raw warehouse (``raw.urdb``) to the typed engine model: fetch a flat CSV row by
URDB label, un-flatten it to v8 JSON, and import it as a :class:`~ratebook.schema.Tariff`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
from ratebook.schema import Tariff
from ratebook.urdb import tariff_from_v8

from .v8 import row_to_v8

DEFAULT_DB = Path("data/ratebook.duckdb")


def fetch_row(label: str, db_path: Path = DEFAULT_DB) -> dict[str, Any]:
    """Return the ``raw.urdb`` row for ``label`` as a column->value dict (empty strings kept)."""
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        cur = con.execute("SELECT * FROM raw.urdb WHERE label = ?", [label])
        columns = [c[0] for c in cur.description]
        row = cur.fetchone()
    finally:
        con.close()
    if row is None:
        raise KeyError(f"no raw.urdb row with label {label!r}")
    return dict(zip(columns, row, strict=True))


def tariff_from_row(row: dict[str, Any]) -> Tariff:
    return tariff_from_v8(row_to_v8(row))


def load_tariff(label: str, db_path: Path = DEFAULT_DB) -> Tariff:
    return tariff_from_row(fetch_row(label, db_path))


def search_tariffs(
    query: str,
    *,
    db_path: Path = DEFAULT_DB,
    sector: str | None = "Residential",
    active_only: bool = True,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Search ``raw.urdb`` for tariffs matching ``query`` (utility name, eiaid, or exact label).

    Returns lightweight metadata rows (no full structure) for typeahead/lookup, freshest first.
    """
    clauses = ["(utility ILIKE ? OR eiaid = ? OR label = ?)"]
    params: list[Any] = [f"%{query}%", query, query]
    if sector:
        clauses.append("sector = ?")
        params.append(sector)
    if active_only:
        clauses.append("(enddate IS NULL OR enddate = '')")
    where = " AND ".join(clauses)
    cols = (
        "label",
        "eiaid",
        "utility",
        "name",
        "sector",
        "startdate",
        "enddate",
        "latest_update",
        "source",
    )
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            f"SELECT {', '.join(cols)} FROM raw.urdb WHERE {where} "
            f"ORDER BY TRY_CAST(latest_update AS TIMESTAMP) DESC NULLS LAST LIMIT ?",
            [*params, limit],
        ).fetchall()
    finally:
        con.close()
    return [dict(zip(cols, r, strict=True)) for r in rows]
