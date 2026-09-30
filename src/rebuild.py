"""Rebuild the warehouse from every landed file, re-checking each one against its fingerprint."""

import io
import sqlite3
import sys

import pandas as pd

from src import config, db, landing, trading_calendar
from src.sources import sarb, satrix, yahoo


def load_instruments(conn: sqlite3.Connection) -> None:
    rows = [(i["security_id"], i["vendor_symbol"], i["name"], i.get("role", "share")) for i in config.instruments()]
    with conn:
        conn.execute("DELETE FROM instrument")
        conn.executemany("INSERT INTO instrument VALUES (?, ?, ?, ?)", rows)


def load_securities(conn: sqlite3.Connection) -> None:
    listed = config.securities()
    aliases = [(a["name"], s["security_id"], a.get("from", 1900), a.get("to", 9999))
               for s in listed for a in s["satrix_names"]]
    with conn:
        conn.execute("DELETE FROM security_alias")
        conn.execute("DELETE FROM security_proxy")
        conn.execute("DELETE FROM security")
        conn.executemany("INSERT INTO security VALUES (?, ?, ?, ?, ?)",
                         [(s["security_id"], s["name"], s.get("vendor_symbol"), s["icb_industry"], s.get("note"))
                          for s in listed])
        conn.executemany("INSERT INTO security_alias VALUES (?, ?, ?, ?)", aliases)
        conn.executemany("INSERT INTO security_proxy VALUES (?, ?, ?, ?, ?)",
                         [(s["security_id"], s["proxy"]["instrument"], s["proxy"]["fx"], str(s["proxy"]["until"]),
                           s["proxy"]["compare_with"]) for s in listed if s.get("proxy")])


def load_statement(conn: sqlite3.Connection, payload: bytes, run_id: str) -> int:
    parsed = satrix.parse(payload)
    year = parsed["year"]
    conn.executemany("INSERT INTO raw_statement_holding VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                     [(year, h["year"], h["name"], h["shares"], h["price"], h["fair_value"], h["weight"], run_id)
                      for h in parsed["holdings"]])
    conn.executemany("INSERT INTO raw_statement_total VALUES (?, ?, ?, ?)",
                     [(year, as_at, total, run_id) for as_at, total in parsed["totals"].items()])
    conn.executemany("INSERT INTO raw_statement_industry VALUES (?, ?, ?, ?, ?)",
                     [(year, as_at, industry, value, run_id)
                      for industry, by_year in parsed["sectors"].items() for as_at, value in by_year.items()])
    return len(parsed["holdings"])


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
        elif source == "satrix":
            rows = load_statement(conn, payload, run_id)
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
    load_securities(conn)
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
