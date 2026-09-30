"""Print the data quality checks: how many problems each found, with examples to investigate."""

import sqlite3
import sys

from src import db

CHECKS = [
    ("dq_repeated_distribution", "Distributions repeated within 45 days (same amount)"),
    ("dq_unit_anomaly", "Prices 20x or more off for one day (unit errors)"),
    ("dq_unknown_unit", "Series with a unit that cannot be converted"),
    ("dq_closed_day_bar", "Prices dated on days the JSE was closed"),
    ("dq_missing_session", "Trading days with no price"),
    ("dq_stale_price", "Prices unchanged for five sessions or more"),
    ("dq_rate", "Gaps or implausible values in the T-bill rate"),
    ("dq_statement_unmapped", "Satrix holdings with no JSE code mapped"),
    ("dq_statement_total", "Satrix statements whose holdings do not add up to the stated total"),
    ("dq_statement_industry", "ICB industry totals that differ from Satrix's (2021 onwards)"),
    ("dq_statement_restated", "Year-end holdings printed differently in two statements"),
    ("dq_statement_price", "Satrix year-end prices that Yahoo's close does not match"),
]


def counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {view: conn.execute(f"SELECT COUNT(*) FROM {view}").fetchone()[0] for view, _ in CHECKS}


def report(conn: sqlite3.Connection, examples: int = 5) -> list[str]:
    out = []
    for view, label in CHECKS:
        cur = conn.execute(f"SELECT * FROM {view} LIMIT {examples}")
        rows = cur.fetchall()
        total = conn.execute(f"SELECT COUNT(*) FROM {view}").fetchone()[0]
        out.append(f"{label}: {total:,}")
        if rows:
            out.append("   " + " | ".join(c[0] for c in cur.description))
            out.extend("   " + " | ".join("" if v is None else str(v) for v in row) for row in rows)
    return out


def main() -> int:
    conn = db.connect()
    print("\n".join(report(conn)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
