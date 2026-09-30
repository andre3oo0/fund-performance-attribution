"""Rebuild the warehouse from every landed file, re-checking each one against its fingerprint."""

import io
import sqlite3
import sys

import pandas as pd

from src import config, db, landing, trading_calendar
from src.sources import sarb, yahoo


def load_instruments(conn: sqlite3.Connection) -> None:
    rows = [(i["security_id"], i["vendor_symbol"], i["name"], i.get("role", "share")) for i in config.instruments()]
    with conn:
        conn.execute("DELETE FROM instrument")
        conn.executemany("INSERT INTO instrument VALUES (?, ?, ?, ?)", rows)


def record_run(conn: sqlite3.Connection, manifest: dict, rows: int, path) -> None:
    conn.execute(
        "INSERT INTO ingest_run VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (manifest["run_id"], manifest["source"], manifest["snapshot_date"], manifest["fetched_at"],
         manifest["session_cutoff"], rows, path.relative_to(config.DATA_DIR).as_posix(), manifest["sha256"]),
    )


def load_file(conn: sqlite3.Connection, manifest_path) -> int:
    payload, manifest = landing.read(manifest_path)
    source, snap, run_id = manifest["source"], manifest["snapshot_date"], manifest["run_id"]
    with conn:
        if source == "yahoo":
            prices = pd.read_csv(io.BytesIO(payload), dtype={"vendor_symbol": str, "price_date": str})[yahoo.COLUMNS]
            prices = prices.assign(source=source, snapshot_date=snap, run_id=run_id)
            prices = prices.astype(object).where(prices.notna(), None)
            cols = ["source", "snapshot_date", *yahoo.COLUMNS, "run_id"]
            conn.executemany(f"INSERT INTO raw_price ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                             prices[cols].itertuples(index=False, name=None))
            conn.executemany(
                "INSERT INTO ingest_symbol_status VALUES (?, ?, ?, ?, ?, ?)",
                [(run_id, s["vendor_symbol"], s["status"], s["row_count"], s["reported_unit"], s["error"])
                 for s in manifest["symbols"]],
            )
            rows = len(prices)
        elif source == "sarb":
            obs = sarb.observations(payload)
            conn.executemany("INSERT INTO raw_rate VALUES (?, ?, ?, ?, ?, ?)",
                             [(source, snap, manifest["series"], o["period"], o["value"], run_id) for o in obs])
            rows = len(obs)
        else:
            raise ValueError(f"No loader for source {source!r} in {manifest_path}")
        record_run(conn, manifest, rows, manifest_path.parent / manifest["file"])
    return rows


def build_derived(conn: sqlite3.Connection) -> None:
    db.run_sql(conn, "staging.sql")
    db.run_sql(conn, "dq.sql")


def rebuild(conn: sqlite3.Connection) -> int:
    db.apply_schema(conn)
    trading_calendar.load(conn)
    load_instruments(conn)
    found = landing.manifests()
    total = sum(load_file(conn, m) for m in found)
    build_derived(conn)
    print(f"{len(found)} landed files, {total:,} rows loaded into {config.DB_PATH.name}")
    return len(found)


def main() -> int:
    if not config.LANDING_DIR.exists():
        print(f"No landed files under {config.LANDING_DIR}", file=sys.stderr)
        return 1
    config.DB_PATH.unlink(missing_ok=True)  # derived, so always rebuilt from scratch
    conn = db.connect()
    rebuild(conn)
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
