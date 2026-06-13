"""Download the URDB bulk CSV and load it into DuckDB.

The bulk file (CC0, no API key) is both the seed corpus and the source of the eval
golden set. Downloads are kept verbatim under the raw directory, one snapshot per day,
each with a ``.meta.json`` provenance sidecar. The DuckDB ``raw.urdb`` table is
all-VARCHAR: the URDB CSV has ~600 sparse columns and inference-at-ingest is how silent
type drift gets in, so typing is deferred to transformations.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb
import httpx

URDB_URL = "https://apps.openei.org/USURDB/download/usurdb.csv.gz"
RAW_TABLE = "raw.urdb"
INGESTS_TABLE = "raw.ingests"


@dataclass(frozen=True)
class DownloadResult:
    path: Path
    meta_path: Path
    sha256: str
    size_bytes: int
    reused: bool


@dataclass(frozen=True)
class LoadResult:
    db_path: Path
    table: str
    row_count: int
    column_count: int


def snapshot_filename(snapshot_date: date) -> str:
    return f"usurdb-{snapshot_date.isoformat()}.csv.gz"


def download_urdb(
    raw_dir: Path,
    url: str = URDB_URL,
    *,
    force: bool = False,
    snapshot_date: date | None = None,
) -> DownloadResult:
    """Fetch the bulk CSV into ``raw_dir``, reusing today's snapshot unless ``force``."""
    snapshot_date = snapshot_date or datetime.now(UTC).date()
    raw_dir.mkdir(parents=True, exist_ok=True)
    dest = raw_dir / snapshot_filename(snapshot_date)
    meta_path = dest.with_name(dest.name + ".meta.json")

    if dest.exists() and not force:
        return DownloadResult(
            path=dest,
            meta_path=meta_path,
            sha256=_sha256(dest),
            size_bytes=dest.stat().st_size,
            reused=True,
        )

    digest = hashlib.sha256()
    part = dest.with_name(dest.name + ".part")
    with httpx.stream("GET", url, follow_redirects=True, timeout=300.0) as response:
        response.raise_for_status()
        headers = response.headers
        with part.open("wb") as out:
            for chunk in response.iter_bytes():
                out.write(chunk)
                digest.update(chunk)
    part.replace(dest)

    meta = {
        "source_url": url,
        "downloaded_at": datetime.now(UTC).isoformat(),
        "sha256": digest.hexdigest(),
        "size_bytes": dest.stat().st_size,
        "etag": headers.get("etag"),
        "last_modified": headers.get("last-modified"),
    }
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")

    return DownloadResult(
        path=dest,
        meta_path=meta_path,
        sha256=meta["sha256"],
        size_bytes=meta["size_bytes"],
        reused=False,
    )


def load_urdb(csv_gz: Path, db_path: Path, *, source_meta: dict | None = None) -> LoadResult:
    """(Re)load the bulk CSV into ``raw.urdb`` and append a provenance row to ``raw.ingests``."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    try:
        con.execute("CREATE SCHEMA IF NOT EXISTS raw")
        con.execute(
            f"CREATE OR REPLACE TABLE {RAW_TABLE} AS "
            "SELECT * FROM read_csv(?, header := true, all_varchar := true, sample_size := -1)",
            [str(csv_gz)],
        )
        row_count = con.execute(f"SELECT count(*) FROM {RAW_TABLE}").fetchone()[0]
        column_count = len(con.execute(f"DESCRIBE {RAW_TABLE}").fetchall())
        _record_ingest(con, csv_gz, row_count, source_meta or {})
    finally:
        con.close()
    return LoadResult(
        db_path=db_path,
        table=RAW_TABLE,
        row_count=row_count,
        column_count=column_count,
    )


def _record_ingest(
    con: duckdb.DuckDBPyConnection, csv_gz: Path, row_count: int, meta: dict
) -> None:
    con.execute(
        f"CREATE TABLE IF NOT EXISTS {INGESTS_TABLE} ("
        " ingested_at TIMESTAMPTZ,"
        " source VARCHAR,"
        " file VARCHAR,"
        " sha256 VARCHAR,"
        " source_url VARCHAR,"
        " source_last_modified VARCHAR,"
        " row_count BIGINT)"
    )
    con.execute(
        f"INSERT INTO {INGESTS_TABLE} VALUES (now(), 'urdb', ?, ?, ?, ?, ?)",
        [
            csv_gz.name,
            meta.get("sha256"),
            meta.get("source_url"),
            meta.get("last_modified"),
            row_count,
        ],
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()
