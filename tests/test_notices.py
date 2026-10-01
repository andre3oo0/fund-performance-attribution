"""Satrix 40 notices: parsed exactly, landed only for STX40, and checked for gaps, totals and membership against the audited holdings."""

import unittest
from datetime import datetime
from pathlib import Path

from src import ingest, landing
from src.sources import satrix_sens
from tests.helpers import EVENING, WarehouseTest, notice_text

MEMBERS = [("SHR", "SHARE HOLDINGS", 60.0, 60.0), ("NEW", "MINING PLC", 30.0, 30.0), ("RET", "RETAIL GROUP", 10.0, 10.0)]


class ParserTest(unittest.TestCase):
    def test_every_constituent_and_date_is_read_and_the_added_list_is_not_counted_twice(self):
        rows = [("AGL", "ANGLO", 12.38, 10.73), ("AMS", "ANGLOPLAT", 0.00, 3.26), ("EXX", "EXXARO RESOURCES LTD", 2.39, 0.00),
                ("GFI", "GOLDFIELDS LTD", 85.23, 86.01)]
        notice = satrix_sens.parse_text(notice_text("2025-03-24", rows))
        self.assertEqual([(c["code"], c["previous"], c["new"]) for c in notice["constituents"]],
                         [("AGL", 0.1238, 0.1073), ("AMS", 0.0, 0.0326), ("EXX", 0.0239, 0.0), ("GFI", 0.8523, 0.8601)])
        self.assertEqual((notice["effective_date"], notice["applied_after"]), ("2025-03-24", "2025-03-21"))
        self.assertEqual(notice["printed_totals"], (1.0, 1.0))

    def test_the_real_layout_quirks_are_read(self):
        # From the September 2023 and September 2024 notices: a row wrapped over three lines, lower-case
        # "JSE code", a date broken across a line, and Satrix's misplaced comma
        text = "\n".join([
            "JSE code: STX40", "Code Share", "   ", "  New Weight", "Previous", "Weight",
            "ABG Barclays Africa (ABSA) 2.40% 2.61%", "PRX Prosus N.V          ", "3.99% ", "      ", "3.85% ",
            "HAR Harmony Gold Mining 0.00% 0.84%", "WHL Woolworths Holdings Ltd  93.61% 92.70% ", "  100.00% 100.00% ",
            "HAR Harmony Gold Mining 0.00% 0.84%",
            "These changes were applied after the close of business on Friday, 20 ",
            "September 2024 and are effective from , Thursday 26 September 2024. ",
        ])
        notice = satrix_sens.parse_text(text)
        self.assertEqual([(c["code"], c["previous"], c["new"]) for c in notice["constituents"]],
                         [("ABG", 0.024, 0.0261), ("PRX", 0.0399, 0.0385), ("HAR", 0.0, 0.0084), ("WHL", 0.9361, 0.927)])
        self.assertEqual((notice["effective_date"], notice["applied_after"]), ("2024-09-26", "2024-09-20"))

    def test_another_satrix_funds_notice_is_refused(self):
        with self.assertRaises(satrix_sens.NotSatrix40):
            satrix_sens.parse_text(notice_text("2025-03-24", MEMBERS, jse_code="STXSWX"))

    def test_the_file_name_gives_the_sens_date_and_number(self):
        self.assertEqual(satrix_sens.identify(Path("SENS_20220323_S458916.pdf")), ("2022-03-23", "S458916"))
        with self.assertRaises(satrix_sens.UnparsedNotice):
            satrix_sens.identify(Path("notice (1).pdf"))


class LandingTest(WarehouseTest):
    def test_only_satrix_40_notices_are_landed_unchanged(self):
        folder = self.tmp / "inbox"
        folder.mkdir()
        mine = self.notice_pdf(notice_text("2022-03-22", MEMBERS))
        (folder / "SENS_20220323_S458916.pdf").write_bytes(mine)
        (folder / "SENS_20220323_S458917.pdf").write_bytes(self.notice_pdf(notice_text("2022-03-22", MEMBERS, "STXSWX")))
        result = ingest.land_satrix_sens(folder, refetch=False, now=EVENING)
        self.assertEqual(result["rows"], 1)
        payload, manifest = landing.read(landing.landing_dir("satrix_sens", "2022-03-23_S458916") / landing.MANIFEST_FILE)
        self.assertEqual(payload, mine)
        self.assertEqual((manifest["sens_id"], manifest["effective_date"]), ("S458916", "2022-03-22"))
        self.assertFalse(landing.landing_dir("satrix_sens", "2022-03-23_S458917").exists())
        self.assertEqual(ingest.land_satrix_sens(folder, refetch=False, now=EVENING)["rows"], 0)  # never landed twice


class NoticeCheckTest(WarehouseTest):
    def count(self, conn, view, where="1"):
        return self.rows(conn, f"SELECT COUNT(*) FROM {view} WHERE {where}")[0][0]

    def test_consistent_notices_raise_no_membership_alarm_and_codes_map(self):
        self.land_notice("2022-03-23", "S1", "2022-03-22", [("SHR", "S", 60.0, 55.0), ("NEW", "M", 40.0, 35.0), ("RTL", "R", 0.0, 10.0)])
        self.land_notice("2022-06-22", "S2", "2022-06-20", [("SHR", "S", 50.0, 50.0), ("NEW", "M", 38.0, 40.0), ("RET", "R", 12.0, 10.0)])
        conn = self.build()
        self.assertEqual(self.count(conn, "dq_notice_membership"), 0)
        self.assertEqual(self.count(conn, "dq_notice_unmapped"), 0)  # RTL and RET are both the retailer
        self.assertEqual(self.count(conn, "dq_notice_total"), 0)

    def test_a_member_appearing_between_notices_is_flagged(self):
        self.land_notice("2022-03-23", "S1", "2022-03-22", [("SHR", "S", 60.0, 60.0), ("NEW", "M", 40.0, 40.0)])
        self.land_notice("2022-06-22", "S2", "2022-06-20", [("SHR", "S", 50.0, 50.0), ("NEW", "M", 38.0, 40.0), ("RET", "R", 12.0, 10.0)])
        conn = self.build()
        self.assertEqual(self.rows(conn, "SELECT sens_id, code, problem FROM dq_notice_membership"),
                         [("S2", "RET", "in this notice only")])

    def test_an_unknown_code_and_a_short_table_are_flagged(self):
        self.land_notice("2022-03-23", "S1", "2022-03-22", [("SHR", "S", 60.0, 60.0), ("XYZ", "UNKNOWN", 39.0, 39.0)])
        conn = self.build()
        self.assertEqual(self.rows(conn, "SELECT code FROM dq_notice_unmapped"), [("XYZ",)])
        self.assertEqual(self.count(conn, "dq_notice_total"), 1)  # 99% printed, so not a whole portfolio

    def test_a_missing_quarter_and_a_duplicate_are_flagged(self):
        self.land_notice("2022-03-23", "S1", "2022-03-22", MEMBERS)
        self.land_notice("2022-06-22", "S2", "2022-06-20", MEMBERS)
        self.land_notice("2022-06-23", "S3", "2022-06-20", MEMBERS)
        conn = self.build()
        found = dict(self.rows(conn, "SELECT review_month, problem FROM dq_notice_coverage WHERE review_month <= '2022-09'"))
        self.assertEqual(found, {"2022-06": "duplicate", "2022-09": "missing"})

    def test_year_end_members_are_checked_against_the_audited_holdings(self):
        audited = [("Share Holdings Ltd", (1, 50.0, 600_000_000, 0.6), (1, 50.0, 500_000_000, 0.5)),
                   ("Mining plc", (1, 50.0, 300_000_000, 0.3), (1, 50.0, 400_000_000, 0.4)),
                   ("Retail Group Ltd", (1, 50.0, 100_000_000, 0.1), (1, 50.0, 100_000_000, 0.1))]
        self.land_statement(2022, audited, {2022: 1_000_000_000, 2021: 1_000_000_000},
                            {"Financials": (600_000_000, 500_000_000), "Basic Materials": (300_000_000, 400_000_000),
                             "Consumer Discretion": (100_000_000, 100_000_000)})
        self.land_notice("2022-12-19", "S1", "2022-12-19", [("SHR", "S", 60.0, 60.0), ("NEW", "M", 40.0, 30.0), ("RET", "R", 0.0, 10.0)])
        clean = self.build()
        self.assertEqual(self.count(clean, "dq_notice_year_end"), 0)
        clean.close()

    def test_a_year_end_member_missing_from_the_notices_is_flagged(self):
        audited = [("Share Holdings Ltd", (1, 50.0, 700_000_000, 0.7), (1, 50.0, 500_000_000, 0.5)),
                   ("Mining plc", (1, 50.0, 300_000_000, 0.3), (1, 50.0, 500_000_000, 0.5))]
        self.land_statement(2022, audited, {2022: 1_000_000_000, 2021: 1_000_000_000},
                            {"Financials": (700_000_000, 500_000_000), "Basic Materials": (300_000_000, 500_000_000)})
        self.land_notice("2022-12-19", "S1", "2022-12-19", [("SHR", "S", 60.0, 70.0), ("RET", "R", 40.0, 30.0)])
        conn = self.build()
        self.assertEqual(self.rows(conn, "SELECT security_id, problem FROM dq_notice_year_end ORDER BY 1"),
                         [("NEW", "in the audited holdings only"), ("RET", "in the notice only")])
