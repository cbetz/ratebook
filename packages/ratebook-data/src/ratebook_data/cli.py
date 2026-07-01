"""Command-line entry point for the data plant."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ratebook_data import urdb


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ratebook-data", description="Ratebook data plant commands."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    urdb_parser = sub.add_parser("urdb", help="Download the URDB bulk CSV and load it into DuckDB.")
    urdb_parser.add_argument(
        "--raw-dir",
        type=Path,
        default=Path("data/raw"),
        help="Directory for verbatim source downloads (default: data/raw).",
    )
    urdb_parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/ratebook.duckdb"),
        help="DuckDB database file to load into (default: data/ratebook.duckdb).",
    )
    urdb_parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if today's snapshot already exists.",
    )

    sub.add_parser(
        "scorecard",
        help="Render the golden-set accuracy scorecard from the recorded results.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "urdb":
        download = urdb.download_urdb(args.raw_dir, force=args.force)
        verb = "reused existing" if download.reused else "downloaded"
        print(
            f"{verb} {download.path} ({download.size_bytes:,} bytes, sha256={download.sha256[:12]})"
        )

        if download.meta_path.exists():
            meta = json.loads(download.meta_path.read_text())
        else:
            meta = {"sha256": download.sha256, "source_url": urdb.URDB_URL}
        loaded = urdb.load_urdb(download.path, args.db, source_meta=meta)
        print(
            f"loaded {loaded.row_count:,} rows x {loaded.column_count} columns "
            f"into {loaded.table} ({loaded.db_path})"
        )
    elif args.command == "scorecard":
        from ratebook_data.golden import load_results, render_scorecard_md

        print(render_scorecard_md(load_results(), snapshot="usurdb-2026-06-13", n_total=20), end="")
    return 0
