import gzip
from datetime import date
from pathlib import Path

import duckdb
from ratebook_data.urdb import download_urdb, load_urdb, snapshot_filename

URDB_ISH_CSV = """\
label,utility,sector,startdate,energyratestructure/period0/tier0rate
539f6e_x,PECO,Residential,2026-01-01,0.12
539f6e_y,PG&E,Commercial,,0.31
"""


def _write_csv_gz(path: Path) -> Path:
    with gzip.open(path, "wt") as f:
        f.write(URDB_ISH_CSV)
    return path


def test_snapshot_filename() -> None:
    assert snapshot_filename(date(2026, 6, 12)) == "usurdb-2026-06-12.csv.gz"


def test_download_reuses_existing_snapshot_without_network(tmp_path: Path) -> None:
    snap_date = date(2026, 6, 12)
    dest = tmp_path / snapshot_filename(snap_date)
    dest.write_bytes(b"placeholder bytes")

    # An unreachable URL proves the early return: reuse must not touch the network.
    result = download_urdb(tmp_path, url="http://127.0.0.1:9/unreachable", snapshot_date=snap_date)

    assert result.reused is True
    assert result.path == dest
    assert result.size_bytes == len(b"placeholder bytes")


def test_load_urdb_all_varchar_with_provenance(tmp_path: Path) -> None:
    csv_gz = _write_csv_gz(tmp_path / "usurdb-2026-01-01.csv.gz")
    db_path = tmp_path / "test.duckdb"

    result = load_urdb(csv_gz, db_path, source_meta={"sha256": "abc", "source_url": "http://x"})

    assert result.row_count == 2
    assert result.column_count == 5
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        types = {row[1] for row in con.execute("DESCRIBE raw.urdb").fetchall()}
        assert types == {"VARCHAR"}
        ingest = con.execute(
            "SELECT source, file, sha256, row_count FROM raw.ingests"
        ).fetchall()
        assert ingest == [("urdb", csv_gz.name, "abc", 2)]
    finally:
        con.close()


def test_load_urdb_is_idempotent_and_appends_ingest_log(tmp_path: Path) -> None:
    csv_gz = _write_csv_gz(tmp_path / "usurdb-2026-01-01.csv.gz")
    db_path = tmp_path / "test.duckdb"

    load_urdb(csv_gz, db_path)
    result = load_urdb(csv_gz, db_path)

    assert result.row_count == 2
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        assert con.execute("SELECT count(*) FROM raw.urdb").fetchone()[0] == 2
        assert con.execute("SELECT count(*) FROM raw.ingests").fetchone()[0] == 2
    finally:
        con.close()
