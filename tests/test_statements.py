"""Satrix statements: the parser reads both years correctly, and each check finds its planted error without false alarms."""

import unittest
from datetime import date

from src.sources import satrix
from tests.helpers import WarehouseTest, lines_for, statement_text, trading_days

BILLION = 1_000_000_000


class ParserTest(unittest.TestCase):
    def parse(self, holdings, industries=None):
        totals = {2023: 3 * BILLION, 2022: 2 * BILLION}
        return satrix.parse_text(*statement_text(2023, holdings, totals, industries or {}))

    def test_each_figure_lands_in_the_year_of_its_column(self):
        parsed = self.parse([
            ("Both Years Ltd", (1_083_830, 1816.77, 1_969_111_111, 0.656), (971_017, 119.86, 116_386_098, 0.058)),
            ("New Member Ltd", (500_000, 20.0, 10_000_000, 0.003), None),
            ("Left Last Year Ltd", None, (690_747, 71.60, 49_457_485, 0.025)),
        ])
        found = sorted((h["name"], h["year"], h["fair_value"]) for h in parsed["holdings"])
        self.assertEqual(found, [("Both Years Ltd", 2022, 116_386_098), ("Both Years Ltd", 2023, 1_969_111_111),
                                 ("Left Last Year Ltd", 2022, 49_457_485), ("New Member Ltd", 2023, 10_000_000)])
        both = next(h for h in parsed["holdings"] if h["name"] == "Both Years Ltd" and h["year"] == 2023)
        self.assertEqual((both["shares"], both["price"]), (1_083_830, 1816.77))
        self.assertAlmostEqual(both["weight"], 0.656)
        self.assertEqual(parsed["totals"], {2023: 3 * BILLION, 2022: 2 * BILLION})

    def test_thousands_separated_by_single_spaces_are_one_figure(self):
        parsed = self.parse([("A Ltd", (1, 1.0, 1, 0.001), None)],
                            {"Financials": (1_908_829_174, 1_473_869_476), "Real Estate": (153_302_845, None),
                             "Consumer Goods": (None, 1_100_041_507)})
        self.assertEqual(parsed["sectors"]["Financials"], {2023: 1_908_829_174, 2022: 1_473_869_476})
        self.assertEqual(parsed["sectors"]["Real Estate"], {2023: 153_302_845, 2022: 0.0})
        self.assertEqual(parsed["sectors"]["Consumer Goods"], {2023: 0.0, 2022: 1_100_041_507})

    def test_a_document_without_holdings_is_refused(self):
        with self.assertRaises(satrix.UnparsedStatement):
            satrix.parse_text("for the year ended 31 December 2023\n 3 000 000 000     2 000 000 000", ["no table"])


M = 1_000_000  # the test fund is R1 billion, so figures print like Satrix's


def held(value: float, price: float = 100.0, total: float = 1000.0) -> tuple:
    return (value * M / price, price, value * M, value / total)


def book(industries: dict) -> dict:
    return {k: tuple(None if v is None else v * M for v in pair) for k, pair in industries.items()}


def rands(totals: dict) -> dict:
    return {k: v * M for k, v in totals.items()}


# A clean pair of statements: 2022 is printed in both, so the restatement check has something to compare
CLEAN_2022 = [("Share Holdings Ltd", held(600.0, 50.0), held(500.0, 45.0)), ("Mining plc", held(300.0), held(400.0)),
              ("Retail Group Ltd", held(100.0), held(100.0))]
CLEAN_2023 = [("Share Holdings Ltd", held(700.0, 55.0), held(600.0, 50.0)), ("Mining plc", held(200.0), held(300.0)),
              ("Retail Group Ltd", held(100.0), held(100.0))]
INDUSTRIES_2022 = {"Financials": (600.0, 500.0), "Basic Materials": (300.0, 400.0), "Consumer Discretion": (100.0, 100.0)}
INDUSTRIES_2023 = {"Financials": (700.0, 600.0), "Basic Materials": (200.0, 300.0), "Consumer Discretion": (100.0, 100.0)}
DAYS = trading_days(date(2021, 12, 1), date(2023, 12, 29))


def closes(y2021: float, y2022: float, y2023: float) -> dict[str, float]:
    return {d: y2021 if d < "2022-06-01" else y2022 if d < "2023-06-01" else y2023 for d in DAYS}


class StatementCheckTest(WarehouseTest):
    def build_with(self, s2022=CLEAN_2022, s2023=CLEAN_2023, i2022=INDUSTRIES_2022, i2023=INDUSTRIES_2023,
                   totals_2023=None, share_closes=None):
        self.land_statement(2022, s2022, rands({2022: 1000.0, 2021: 1000.0}), book(i2022))
        self.land_statement(2023, s2023, rands(totals_2023 or {2023: 1000.0, 2022: 1000.0}), book(i2023))
        # 31 Dec 2022 is a Saturday, so the year-end price is Friday 30 December's
        self.land_prices(lines_for("SHR.JO", share_closes or closes(4500.0, 5000.0, 5500.0)))
        return self.build()

    def count(self, conn, view):
        return self.rows(conn, f"SELECT COUNT(*) FROM {view}")[0][0]

    def test_clean_statements_raise_no_alarm(self):
        conn = self.build_with()
        for view in ("dq_statement_unmapped", "dq_statement_total", "dq_statement_industry", "dq_statement_restated"):
            self.assertEqual(self.count(conn, view), 0, view)
        self.assertEqual(self.rows(conn, "SELECT * FROM dq_statement_price WHERE problem = 'different'"), [])

    def test_a_renamed_line_maps_by_year_and_weights_come_from_rands(self):
        conn = self.build_with()
        rows = self.rows(conn, "SELECT as_at_year, security_id, statement_year, ROUND(weight, 4) FROM stg_benchmark_holding "
                               "WHERE satrix_name = 'Mining plc' ORDER BY 1")
        # 2021 comes only from the 2022 statement; 2022 from its own statement, not the 2023 one
        self.assertEqual(rows, [(2021, "OLD", 2022, 0.4), (2022, "NEW", 2022, 0.3), (2023, "NEW", 2023, 0.2)])

    def test_a_name_with_no_code_is_flagged(self):
        unknown = [*CLEAN_2023[:2], ("Unknown Newcomer Ltd", held(100.0), held(100.0))]
        conn = self.build_with(s2023=unknown)
        # 2022 is taken from its own statement, so only the 2023 statement's own year-end is staged with the new name
        self.assertEqual(self.rows(conn, "SELECT as_at_year, satrix_name FROM dq_statement_unmapped"),
                         [(2023, "Unknown Newcomer Ltd")])

    def test_holdings_that_do_not_add_up_to_the_total_are_flagged(self):
        conn = self.build_with(totals_2023={2023: 1100.0, 2022: 1000.0})
        self.assertEqual(self.rows(conn, "SELECT statement_year, as_at_year, difference_zar FROM dq_statement_total"),
                         [(2023, 2023, -100.0 * M)])

    def test_a_company_in_the_wrong_industry_is_flagged_on_both_sides(self):
        moved = {**INDUSTRIES_2023, "Financials": (600.0, 600.0), "Consumer Discretion": (200.0, 100.0)}
        conn = self.build_with(i2023=moved)
        rows = self.rows(conn, "SELECT as_at_year, icb_industry, difference_zar FROM dq_statement_industry ORDER BY 2")
        self.assertEqual(rows, [(2023, "Consumer Discretionary", -100.0 * M), (2023, "Financials", 100.0 * M)])

    def test_the_old_icb_structure_before_2021_is_not_compared(self):
        # The 2021 statement prints 2020 in the old structure, as Satrix's real one does
        s2021 = [("Share Holdings Ltd", held(500.0, 45.0), held(700.0)), ("Mining plc", held(400.0), held(300.0)),
                 ("Retail Group Ltd", held(100.0), None)]
        self.land_statement(2021, s2021, rands({2021: 1000.0, 2020: 1000.0}),
                            book({"Financials": (500.0, 700.0), "Basic Materials": (400.0, 50.0),
                                  "Consumer Discretion": (100.0, None), "Consumer Goods": (None, 250.0)}))
        conn = self.build_with()
        self.assertEqual(self.count(conn, "dq_statement_industry"), 0)

    def test_a_year_end_printed_differently_in_the_next_statement_is_flagged(self):
        restated = [("Share Holdings Ltd", held(700.0, 55.0), held(650.0, 50.0)), *CLEAN_2023[1:]]
        conn = self.build_with(s2023=restated, i2023={**INDUSTRIES_2023, "Financials": (700.0, 650.0)},
                               totals_2023={2023: 1000.0, 2022: 1050.0})
        self.assertEqual(self.rows(conn, "SELECT as_at_year, satrix_name, first_zar, later_zar FROM dq_statement_restated"),
                         [(2022, "Share Holdings Ltd", 600.0 * M, 650.0 * M)])

    def test_a_vendor_close_that_differs_from_satrix_is_flagged_but_rounding_is_not(self):
        conn = self.build_with(share_closes=closes(4500.0, 5003.0, 6050.0))
        rows = self.rows(conn, "SELECT as_at_year, price_date, ROUND(difference, 4) FROM dq_statement_price "
                               "WHERE security_id = 'SHR'")
        self.assertEqual(rows, [(2023, "2023-12-29", 0.1)])  # 2022's R50.03 against R50.00 is within 0.1%

    def test_a_member_with_no_price_is_reported(self):
        conn = self.build_with()
        missing = self.rows(conn, "SELECT DISTINCT security_id FROM dq_statement_price WHERE problem = 'no_price' ORDER BY 1")
        self.assertEqual(missing, [("NEW",), ("OLD",), ("RET",)])
