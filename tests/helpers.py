"""Test helpers: a throwaway landing folder and warehouse, filled with synthetic vendor files."""

import json
import shutil
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest import mock

from src import config, db, landing, rebuild, trading_calendar
from src.sources import satrix, satrix_sens

TEST_INSTRUMENTS = [
    {"security_id": "FUND", "vendor_symbol": "FUND.JO", "role": "benchmark", "name": "Test fund"},
    {"security_id": "IDX", "vendor_symbol": "^IDX.JO", "role": "index", "name": "Test index"},
    {"security_id": "SHR", "vendor_symbol": "SHR.JO", "role": "share", "name": "Test share"},
    {"security_id": "RET_SW", "vendor_symbol": "RET.SW", "role": "proxy", "name": "Retailer abroad"},
    {"security_id": "CHFZAR", "vendor_symbol": "CHFZAR=X", "role": "fx", "name": "Swiss franc in rand"},
]
TEST_SECURITIES = [
    {"security_id": "SHR", "vendor_symbol": "SHR.JO", "name": "Test share", "icb_industry": "Financials",
     "satrix_names": [{"name": "Share Holdings Ltd"}]},
    {"security_id": "OLD", "name": "Old line", "icb_industry": "Basic Materials", "satrix_names": [{"name": "Mining plc", "to": 2021}]},
    {"security_id": "NEW", "name": "New line", "icb_industry": "Basic Materials", "satrix_names": [{"name": "Mining plc", "from": 2022}]},
    {"security_id": "RET", "name": "Retailer", "icb_industry": "Consumer Discretionary", "satrix_names": [{"name": "Retail Group Ltd"}], "jse_codes": ["RTL", "RET"],
     "proxy": {"instrument": "RET_SW", "fx": "CHFZAR", "until": "2022-12-30", "compare_with": "SHR"}},
]
EVENING = datetime(2022, 12, 30, 19, 0, tzinfo=landing.SAST)
HEADER = "vendor_symbol,price_date,open,high,low,close,adj_close,volume,dividends,splits,reported_unit"


def trading_days(start: date, end: date) -> list[str]:
    return [d for d, open_, _ in trading_calendar.build(start, end) if open_]


def bar(symbol: str, day: str, close: float, dividend: float = 0.0, unit: str = "ZAc") -> str:
    return f"{symbol},{day},{close},{close},{close},{close},{close},1000,{dividend},0.0,{unit}"


def prices_payload(lines: list[str]) -> bytes:
    return ("\n".join([HEADER, *lines]) + "\n").encode("utf-8")


def rates_payload(rows: list[tuple[str, float]]) -> bytes:
    return json.dumps([{"Period": f"{d}T00:00:00", "Timeseries": "Test T-bill", "Value": v} for d, v in rows]).encode()


class WarehouseTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.statements = {}
        self.notices = {}
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        for patch in (
            mock.patch.object(config, "LANDING_DIR", self.tmp / "landing"),
            mock.patch.object(config, "DB_PATH", self.tmp / "warehouse.db"),
            mock.patch.object(config, "DATA_DIR", self.tmp),
            mock.patch.object(config, "instruments", lambda: TEST_INSTRUMENTS),
            mock.patch.object(config, "securities", lambda: TEST_SECURITIES),
            mock.patch.object(satrix, "extract", lambda pdf: self.statements[pdf]),
            mock.patch.object(satrix_sens, "extract", lambda pdf: self.notices[pdf]),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def land_prices(self, lines: list[str], snapshot_date: str = "2022-12-30") -> None:
        landing.write("yahoo", snapshot_date, "prices.csv.gz", prices_payload(lines),
                      {"rows": len(lines), "symbols": []}, now=EVENING)

    def land_rates(self, rows: list[tuple[str, float]], snapshot_date: str = "2022-12-30") -> None:
        landing.write("sarb", snapshot_date, "TEST.json.gz", rates_payload(rows),
                      {"series": "TEST", "rows": len(rows)}, now=EVENING)

    def notice_pdf(self, text: str) -> bytes:
        payload = f"%PDF synthetic notice {len(self.notices)}".encode()
        self.notices[payload] = text
        return payload

    def land_notice(self, sens_date: str, sens_id: str, effective: str, rows: list) -> None:
        payload = self.notice_pdf(notice_text(effective, rows))
        landing.write("satrix_sens", f"{sens_date}_{sens_id}", "notice.pdf.gz", payload,
                      {"sens_id": sens_id, "sens_date": sens_date, "rows": len(rows)}, now=EVENING)

    def land_statement(self, year: int, holdings: list, totals: dict, industries: dict) -> None:
        payload = f"%PDF synthetic statement {year}".encode()
        self.statements[payload] = statement_text(year, holdings, totals, industries)
        landing.write("satrix", f"{year}-12-31", "statement.pdf.gz", payload, {"rows": 1}, now=EVENING)

    def build(self):
        conn = db.connect()
        self.addCleanup(conn.close)
        rebuild.rebuild(conn)
        return conn

    @staticmethod
    def rows(conn, sql: str) -> list[tuple]:
        return conn.execute(sql).fetchall()


def series(symbol: str, days: list[str], start: float = 1000.0, step: float = 1.0) -> dict[str, float]:
    return {d: start + i * step for i, d in enumerate(days)}


def lines_for(symbol: str, closes: dict[str, float], dividends: dict[str, float] | None = None,
              unit: str = "ZAc") -> list[str]:
    dividends = dividends or {}
    return [bar(symbol, d, c, dividends.get(d, 0.0), unit) for d, c in closes.items()]


def shift(day: str, days: int) -> str:
    return (date.fromisoformat(day) + timedelta(days=days)).isoformat()


def spaced(value: float) -> str:
    return f"{value:,.0f}".replace(",", " ")


def figures(held: tuple | None) -> str:
    if held is None:
        return " " * 60
    shares, price, value, weight = held
    return f"{spaced(shares):>15}{f'{price:,.2f}':>12}{spaced(value):>20}{f'{weight:.1%}':>10}"


def statement_text(year: int, holdings: list, totals: dict, industries: dict) -> tuple[str, list[str]]:
    # Mirrors Satrix's layout: current year's four columns, then the prior year's, each (shares, price, value, weight)
    header = f"{'Name of company':<45}{'No. of shares':>15}{'':>42}{'No. of shares':>15}"
    rows = [f"{name:<45}{figures(current)}{figures(prior)}".rstrip() for name, current, prior in holdings]
    layout = "\n".join([f"for the year ended 31 December {year}", header, *rows])
    lines = [f"{name}{spaced(b):>18}" if a is None else f"{name}{spaced(a):>18}     {'-' if b is None else spaced(b)}"
             for name, (a, b) in industries.items()]
    plain = "\n".join([f"for the year ended 31 December {year}", *rows,
                        f"  {spaced(totals[year])}     {spaced(totals[year - 1])}", *lines])
    return plain, [layout]


def notice_text(effective: str, rows: list, jse_code: str = "STX40", total: float | None = None) -> str:
    # Mirrors a Satrix notice: rows of (code, name, previous %, new %), the totals, then the added and removed lists
    day = date.fromisoformat(effective)
    table = [f"{code:<9}{name:<38}{prev:>6.2f}%{new:>11.2f}%" for code, name, prev, new in rows]
    added = [line for line, (_, _, prev, _) in zip(table, rows) if prev == 0]
    return "\n".join([
        "SATRIX COLLECTIVE INVESTMENT SCHEME", f"JSE Code: {jse_code}", "REBALANCING OF THE PORTFOLIO",
        "Code     Share                                 Weight      Weight", *table,
        f"{'':<47}{sum(r[2] for r in rows):>6.2f}%{total if total is not None else sum(r[3] for r in rows):>11.2f}%",
        "The following constituents have been added:", *added,
        "These changes were applied after the close of business on Friday,",
        f"{(day - timedelta(days=3)).day} {(day - timedelta(days=3)):%B %Y} and are effective from Monday, {day.day} {day:%B %Y}.",
    ])
