"""Foreign-listing proxies: converted to rand on JSE days, carried over foreign holidays, checked against Satrix."""

from datetime import date

from tests.helpers import WarehouseTest, lines_for, trading_days

M = 1_000_000
JSE_DAYS = trading_days(date(2021, 12, 1), date(2023, 3, 31))
HOLDINGS = lambda ret_2022: [("Share Holdings Ltd", (6 * M, 100.0, 600 * M, 0.6), (5 * M, 100.0, 500 * M, 0.5)),
                             ("Retail Group Ltd", (4 * M, ret_2022, 4 * M * ret_2022, 0.4), (5 * M, 100.0, 500 * M, 0.5))]


class ProxyTest(WarehouseTest):
    def build_with(self, proxy=None, fx=None, ret_2022=100.0, share=None, proxy_unit="CHF"):
        total = 600 * M + 4 * M * ret_2022
        self.land_statement(2022, HOLDINGS(ret_2022), {2022: total, 2021: 1000 * M},
                            {"Financials": (600 * M, 500 * M), "Consumer Discretion": (4 * M * ret_2022, 500 * M)})
        lines = lines_for("SHR.JO", share or {d: 10000.0 for d in JSE_DAYS})
        lines += lines_for("RET.SW", proxy or {d: 6.25 for d in JSE_DAYS}, unit=proxy_unit)
        lines += lines_for("CHFZAR=X", fx or {d: 16.0 for d in JSE_DAYS}, unit="ZAR")
        self.land_prices(sorted(lines, key=lambda l: l.split(",")[1]))
        return self.build()

    def test_a_foreign_close_is_converted_to_rand_up_to_the_cut_off(self):
        conn = self.build_with()
        rows = self.rows(conn, "SELECT MIN(price_date), MAX(price_date), MIN(close_zar), MAX(close_zar) FROM stg_proxy_price")
        self.assertEqual(rows, [(JSE_DAYS[0], "2022-12-30", 100.0, 100.0)])

    def test_pence_are_converted_to_pounds_before_the_rate(self):
        conn = self.build_with(proxy={d: 625.0 for d in JSE_DAYS}, proxy_unit="GBp")
        self.assertEqual(self.rows(conn, "SELECT DISTINCT currency, close_local, close_zar FROM stg_proxy_price"),
                         [("GBP", 6.25, 100.0)])

    def test_a_foreign_holiday_carries_the_last_close_and_is_flagged(self):
        proxy = {d: 6.25 for d in JSE_DAYS if d != "2022-05-26"}  # Ascension Day: Zurich closed, the JSE open
        conn = self.build_with(proxy=proxy)
        rows = self.rows(conn, "SELECT price_date, proxy_date, proxy_carried, close_zar FROM stg_proxy_price "
                               "WHERE price_date = '2022-05-26'")
        self.assertEqual(rows, [("2022-05-26", "2022-05-25", 1, 100.0)])

    def test_foreign_trading_on_a_jse_holiday_is_not_a_closed_day_error(self):
        proxy = {**{d: 6.25 for d in JSE_DAYS}, "2022-06-16": 6.30}  # Youth Day
        conn = self.build_with(proxy=dict(sorted(proxy.items())))
        self.assertEqual(self.rows(conn, "SELECT COUNT(*) FROM dq_closed_day_bar")[0][0], 0)
        self.assertEqual(self.rows(conn, "SELECT COUNT(*) FROM stg_proxy_price WHERE price_date = '2022-06-16'")[0][0], 0)

    def test_matching_year_end_returns_raise_no_alarm(self):
        proxy = {d: 6.25 if d < "2022-06-01" else 6.875 for d in JSE_DAYS}  # +10% in francs
        conn = self.build_with(proxy=proxy, ret_2022=110.0)
        self.assertEqual(self.rows(conn, "SELECT from_year, to_year, ROUND(satrix_return, 4), ROUND(proxy_return, 4) "
                                         "FROM v_proxy_year_end"), [(2021, 2022, 0.1, 0.1)])
        self.assertEqual(self.rows(conn, "SELECT COUNT(*) FROM dq_proxy_year_end")[0][0], 0)

    def test_a_rate_move_counts_in_the_rand_return(self):
        fx = {d: 16.0 if d < "2022-06-01" else 17.6 for d in JSE_DAYS}  # the franc 10% stronger, the share flat
        conn = self.build_with(fx=fx, ret_2022=110.0)
        self.assertEqual(self.rows(conn, "SELECT COUNT(*) FROM dq_proxy_year_end")[0][0], 0)

    def test_a_proxy_that_does_not_track_satrix_is_flagged(self):
        conn = self.build_with(ret_2022=110.0)  # Satrix +10%, the proxy flat
        self.assertEqual(self.rows(conn, "SELECT security_id, ROUND(difference, 4) FROM dq_proxy_year_end"),
                         [("RET", -0.1)])

    def test_overlap_months_compare_the_proxy_with_the_jse_series(self):
        share = {d: 10000.0 if d < "2022-03-01" else 10500.0 for d in JSE_DAYS}
        conn = self.build_with(share=share)
        rows = self.rows(conn, "SELECT month, ROUND(jse_return, 4), ROUND(proxy_return, 4) FROM v_proxy_overlap "
                               "WHERE ABS(difference) > 0.0001")
        self.assertEqual(rows, [("2022-03", 0.05, 0.0)])
