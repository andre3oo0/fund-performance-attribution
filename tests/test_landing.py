"""Landing: files are stored as received, never silently replaced, and a changed file is refused."""

from datetime import datetime

from src import landing
from tests.helpers import EVENING, WarehouseTest, bar, prices_payload


class LandingTest(WarehouseTest):
    def test_second_landing_on_the_same_day_is_refused(self):
        self.land_prices([bar("FUND.JO", "2022-12-29", 100.0)])
        with self.assertRaises(landing.AlreadyLanded):
            self.land_prices([bar("FUND.JO", "2022-12-29", 999.0)])

    def test_refetch_replaces_and_rehashes(self):
        self.land_prices([bar("FUND.JO", "2022-12-29", 100.0)])
        _, manifest = landing.write("yahoo", "2022-12-30", "prices.csv.gz",
                                    prices_payload([bar("FUND.JO", "2022-12-29", 101.0)]),
                                    {"rows": 1, "symbols": []}, refetch=True, now=EVENING)
        payload, reread = landing.read(landing.landing_dir("yahoo", "2022-12-30") / landing.MANIFEST_FILE)
        self.assertIn(b"101.0", payload)
        self.assertEqual(manifest["sha256"], reread["sha256"])

    def test_changed_file_is_refused(self):
        data_path, _ = landing.write("yahoo", "2022-12-30", "prices.csv.gz",
                                     prices_payload([bar("FUND.JO", "2022-12-29", 100.0)]),
                                     {"rows": 1, "symbols": []}, now=EVENING)
        data_path.write_bytes(data_path.read_bytes() + b"\x00")
        with self.assertRaises(landing.TamperedLanding):
            landing.read(data_path.parent / landing.MANIFEST_FILE)

    def test_identical_content_gives_an_identical_hash(self):
        payload = prices_payload([bar("FUND.JO", "2022-12-29", 100.0)])
        first, _ = landing.write("yahoo", "2022-12-30", "prices.csv.gz", payload, {}, now=EVENING)
        second, _ = landing.write("yahoo", "2022-12-31", "prices.csv.gz", payload, {}, now=EVENING)
        self.assertEqual(landing.sha256(first), landing.sha256(second))

    def test_a_fetch_before_the_close_excludes_that_day(self):
        afternoon = datetime(2022, 12, 30, 16, 0, tzinfo=landing.SAST)
        self.assertEqual(landing.session_cutoff("2022-12-30", afternoon), "2022-12-29")
        self.assertEqual(landing.session_cutoff("2022-12-30", EVENING), "2022-12-30")
