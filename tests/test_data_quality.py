"""Planted errors each check must find, and traps that must not raise a false alarm."""

from datetime import date

from tests.helpers import WarehouseTest, lines_for, series, trading_days

DAYS = trading_days(date(2022, 1, 3), date(2022, 12, 30))


class DataQualityTest(WarehouseTest):
    def build_with(self, fund=None, index=None, share=None, rates=None):
        lines = []
        lines += lines_for("FUND.JO", **(fund or {"closes": series("FUND.JO", DAYS)}))
        lines += lines_for("^IDX.JO", **(index or {"closes": series("^IDX.JO", DAYS, 70000.0, 10.0), "unit": "ZAR"}))
        lines += lines_for("SHR.JO", **(share or {"closes": series("SHR.JO", DAYS, 5000.0)}))
        self.land_prices(lines)
        self.land_rates(rates or [(d, 5.0) for d in DAYS])
        return self.build()

    def test_clean_data_raises_no_alarm(self):
        conn = self.build_with()
        for view in ("dq_repeated_distribution", "dq_unit_anomaly", "dq_unknown_unit", "dq_closed_day_bar",
                     "dq_missing_session", "dq_stale_price", "dq_rate"):
            self.assertEqual(self.rows(conn, f"SELECT COUNT(*) FROM {view}")[0][0], 0, view)

    def test_cents_become_rands_and_index_points_are_untouched(self):
        conn = self.build_with()
        fund, index = self.rows(conn, "SELECT security_id, close_value FROM stg_price WHERE price_date = '2022-01-03' "
                                      "AND security_id IN ('FUND', 'IDX') ORDER BY security_id")
        self.assertAlmostEqual(fund[1], 10.0)
        self.assertAlmostEqual(index[1], 70000.0)

    def test_distribution_listed_three_times_is_flagged_on_every_row(self):
        repeated = {"2022-03-31": 69.48, "2022-04-20": 69.48, "2022-04-22": 69.48}
        conn = self.build_with(fund={"closes": series("FUND.JO", DAYS), "dividends": repeated})
        flagged = self.rows(conn, "SELECT vendor_date, cluster_size FROM dq_repeated_distribution ORDER BY 1")
        self.assertEqual(flagged, [("2022-03-31", 3), ("2022-04-20", 3), ("2022-04-22", 3)])

    def test_same_amount_a_quarter_apart_is_not_a_repeat(self):
        quarterly = {"2022-01-19": 50.0, "2022-04-20": 50.0, "2022-07-20": 50.0}
        conn = self.build_with(fund={"closes": series("FUND.JO", DAYS), "dividends": quarterly})
        self.assertEqual(self.rows(conn, "SELECT COUNT(*) FROM dq_repeated_distribution")[0][0], 0)

    def test_one_day_price_a_hundred_times_too_small_is_flagged(self):
        closes = series("FUND.JO", DAYS, 8400.0)
        closes["2022-04-25"] = closes["2022-04-25"] / 100
        conn = self.build_with(fund={"closes": closes})
        self.assertEqual(self.rows(conn, "SELECT security_id, price_date, unit_anomaly FROM dq_unit_anomaly"),
                         [("FUND", "2022-04-25", "too_small")])

    def test_vendor_switching_units_for_good_is_a_step_change(self):
        closes = {d: (84.0 if d >= "2022-09-01" else 8400.0) for d in DAYS}
        closes = {d: c + i * 0.01 for i, (d, c) in enumerate(closes.items())}
        conn = self.build_with(fund={"closes": closes})
        self.assertEqual(self.rows(conn, "SELECT price_date, unit_anomaly FROM dq_unit_anomaly"),
                         [("2022-09-01", "step_change")])

    def test_share_split_that_stays_is_not_a_unit_error(self):
        closes = {d: (5000.0 if d < "2022-06-01" else 2500.0) + i for i, d in enumerate(DAYS)}
        conn = self.build_with(share={"closes": closes})
        self.assertEqual(self.rows(conn, "SELECT COUNT(*) FROM dq_unit_anomaly")[0][0], 0)

    def test_missing_trading_day_is_flagged_but_a_holiday_is_not(self):
        closes = series("SHR.JO", DAYS, 5000.0)
        del closes["2022-05-03"]
        conn = self.build_with(share={"closes": closes})
        missing = self.rows(conn, "SELECT security_id, missing_date FROM dq_missing_session")
        self.assertEqual(missing, [("SHR", "2022-05-03")])
        self.assertNotIn("2022-04-27", DAYS)  # Freedom Day: absent from the data and correctly not reported

    def test_price_on_a_public_holiday_is_flagged(self):
        closes = series("SHR.JO", DAYS, 5000.0)
        closes["2022-06-16"] = 5100.0
        conn = self.build_with(share={"closes": dict(sorted(closes.items()))})
        self.assertEqual(self.rows(conn, "SELECT security_id, price_date, reason FROM dq_closed_day_bar"),
                         [("SHR", "2022-06-16", "Youth Day")])

    def test_price_frozen_for_five_sessions_is_flagged_but_four_is_not(self):
        closes = series("SHR.JO", DAYS, 5000.0)
        for d in DAYS[20:25]:
            closes[d] = 4999.0
        for d in DAYS[100:104]:
            closes[d] = 4998.0
        conn = self.build_with(share={"closes": closes})
        self.assertEqual(self.rows(conn, "SELECT security_id, fifth_session FROM dq_stale_price"), [("SHR", DAYS[24])])

    def test_zero_rate_and_a_long_gap_are_flagged_but_a_weekend_is_not(self):
        rates = [(d, 5.0) for d in DAYS if not ("2022-08-01" <= d <= "2022-08-19")]
        rates = [(d, 0.0 if d == "2022-02-18" else v) for d, v in rates]
        conn = self.build_with(rates=rates)
        problems = self.rows(conn, "SELECT rate_date, problem FROM dq_rate ORDER BY 1")
        self.assertEqual(problems, [("2022-02-18", "out_of_range"), ("2022-08-22", "gap")])
