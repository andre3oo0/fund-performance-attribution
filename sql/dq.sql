-- Data quality checks: one view per check, each row a problem to explain before the data is used.

DROP VIEW IF EXISTS dq_repeated_distribution;
CREATE VIEW dq_repeated_distribution AS
SELECT security_id, vendor_date, amount_reported, reported_unit, cluster_size, cluster_first_date
FROM stg_distribution
WHERE cluster_size > 1;

DROP VIEW IF EXISTS dq_unit_anomaly;
CREATE VIEW dq_unit_anomaly AS
SELECT security_id, price_date, close_reported, reported_unit, unit_anomaly
FROM stg_price
WHERE unit_anomaly IS NOT NULL;

DROP VIEW IF EXISTS dq_unknown_unit;
CREATE VIEW dq_unknown_unit AS
SELECT security_id, reported_unit, COUNT(*) AS bars
FROM stg_price
WHERE unit_unknown
GROUP BY 1, 2;

DROP VIEW IF EXISTS dq_closed_day_bar;
CREATE VIEW dq_closed_day_bar AS
SELECT p.security_id, p.price_date, p.close_reported, c.reason
FROM stg_price p
LEFT JOIN trading_calendar c ON c.cal_date = p.price_date
WHERE p.is_trading_day = 0 AND p.role NOT IN ('proxy', 'fx');  -- foreign markets keep their own calendars

-- Trading days inside a series' own date range with no bar
DROP VIEW IF EXISTS dq_missing_session;
CREATE VIEW dq_missing_session AS
WITH span AS (
    SELECT security_id, MIN(price_date) AS first_date, MAX(price_date) AS last_date
    FROM stg_price
    WHERE role NOT IN ('proxy', 'fx')  -- their gaps on JSE days are carried and flagged in stg_proxy_price
    GROUP BY 1
)
SELECT s.security_id, c.cal_date AS missing_date
FROM span s
JOIN trading_calendar c ON c.cal_date BETWEEN s.first_date AND s.last_date AND c.is_trading_day = 1
LEFT JOIN stg_price p ON p.security_id = s.security_id AND p.price_date = c.cal_date
WHERE p.price_date IS NULL;

-- Five or more sessions at exactly the same close; one row per run, at the day it reached five
DROP VIEW IF EXISTS dq_stale_price;
CREATE VIEW dq_stale_price AS
SELECT security_id, price_date AS fifth_session, close_reported
FROM stg_price
WHERE stale_days = 5 AND is_trading_day = 1;

-- Gaps of more than ten days between published rates, and rates outside a plausible range
DROP VIEW IF EXISTS dq_rate;
CREATE VIEW dq_rate AS
WITH ordered AS (
    SELECT series, rate_date, value_pct, LAG(rate_date) OVER (PARTITION BY series ORDER BY rate_date) AS prev_date
    FROM stg_rate
)
SELECT series, rate_date, value_pct, prev_date,
       CASE WHEN julianday(rate_date) - julianday(prev_date) > 10 THEN 'gap'
            WHEN value_pct IS NULL OR value_pct <= 0 OR value_pct >= 30 THEN 'out_of_range' END AS problem
FROM ordered
WHERE julianday(rate_date) - julianday(prev_date) > 10 OR value_pct IS NULL OR value_pct <= 0 OR value_pct >= 30;

-- Satrix statement checks; R5 allows for Satrix rounding each figure to the rand
DROP VIEW IF EXISTS dq_statement_unmapped;
CREATE VIEW dq_statement_unmapped AS
SELECT as_at_year, statement_year, satrix_name, fair_value_zar
FROM stg_benchmark_holding
WHERE security_id IS NULL;

DROP VIEW IF EXISTS dq_statement_total;
CREATE VIEW dq_statement_total AS
SELECT t.statement_year, t.as_at_year, t.total_zar, SUM(h.fair_value_zar) AS holdings_zar,
       SUM(h.fair_value_zar) - t.total_zar AS difference_zar
FROM raw_statement_total t
LEFT JOIN raw_statement_holding h ON h.statement_year = t.statement_year AND h.as_at_year = t.as_at_year
GROUP BY 1, 2, 3
HAVING ABS(COALESCE(SUM(h.fair_value_zar), 0) - t.total_zar) > 5;

-- Each company's industry, proven against Satrix's rand totals; before 2021 Satrix printed the old ICB structure
DROP VIEW IF EXISTS dq_statement_industry;
CREATE VIEW dq_statement_industry AS
WITH printed AS (
    SELECT statement_year, as_at_year,
           CASE industry_printed WHEN 'Consumer Discretion' THEN 'Consumer Discretionary' ELSE industry_printed END AS icb_industry,
           fair_value_zar
    FROM raw_statement_industry
    WHERE as_at_year >= 2021
),
mapped AS (
    SELECT h.statement_year, h.as_at_year, s.icb_industry, SUM(h.fair_value_zar) AS fair_value_zar
    FROM raw_statement_holding h
    JOIN security_alias a ON a.satrix_name = h.satrix_name AND h.as_at_year BETWEEN a.from_year AND a.to_year
    JOIN security s ON s.security_id = a.security_id
    WHERE h.as_at_year >= 2021
    GROUP BY 1, 2, 3
),
keys AS (
    SELECT statement_year, as_at_year, icb_industry FROM printed
    UNION
    SELECT statement_year, as_at_year, icb_industry FROM mapped
)
SELECT k.statement_year, k.as_at_year, k.icb_industry, p.fair_value_zar AS printed_zar, m.fair_value_zar AS mapped_zar,
       COALESCE(m.fair_value_zar, 0) - COALESCE(p.fair_value_zar, 0) AS difference_zar
FROM keys k
LEFT JOIN printed p USING (statement_year, as_at_year, icb_industry)
LEFT JOIN mapped m USING (statement_year, as_at_year, icb_industry)
WHERE ABS(COALESCE(m.fair_value_zar, 0) - COALESCE(p.fair_value_zar, 0)) > 5;

-- The same year-end printed differently in two statements
DROP VIEW IF EXISTS dq_statement_restated;
CREATE VIEW dq_statement_restated AS
SELECT a.as_at_year, a.satrix_name, a.statement_year AS first_statement, b.statement_year AS later_statement,
       a.shares AS first_shares, b.shares AS later_shares, a.fair_value_zar AS first_zar, b.fair_value_zar AS later_zar
FROM raw_statement_holding a
JOIN raw_statement_holding b ON b.as_at_year = a.as_at_year AND b.satrix_name = a.satrix_name
 AND b.statement_year > a.statement_year
WHERE a.shares <> b.shares OR ABS(a.fair_value_zar - b.fair_value_zar) > 5;

-- Satrix's year-end price against Yahoo's close on the last trading day of the year; 0.1% allows for rounding
DROP VIEW IF EXISTS dq_statement_price;
CREATE VIEW dq_statement_price AS
WITH last_day AS (
    SELECT substr(cal_date, 1, 4) AS year, MAX(cal_date) AS price_date
    FROM trading_calendar
    WHERE is_trading_day = 1 AND substr(cal_date, 6) <= '12-31'
    GROUP BY 1
)
SELECT h.as_at_year, h.security_id, h.satrix_name, d.price_date, h.price_zar AS satrix_price_zar,
       p.close_value AS yahoo_close_zar, p.close_value / h.price_zar - 1 AS difference,
       CASE WHEN p.close_value IS NULL THEN 'no_price' ELSE 'different' END AS problem
FROM stg_benchmark_holding h
JOIN last_day d ON d.year = CAST(h.as_at_year AS TEXT)
LEFT JOIN stg_price p ON p.security_id = h.security_id AND p.price_date = d.price_date
WHERE p.close_value IS NULL OR ABS(p.close_value / h.price_zar - 1) > 0.001;

-- A proxy's rand return between two Satrix year-ends against Satrix's own prices; 2% allows for closing-time differences
DROP VIEW IF EXISTS v_proxy_year_end;
CREATE VIEW v_proxy_year_end AS
WITH ends AS (
    SELECT h.security_id, h.as_at_year, h.price_zar,
           (SELECT MAX(price_date) FROM stg_proxy_price x WHERE x.security_id = h.security_id
             AND x.price_date <= h.as_at_date) AS price_date
    FROM stg_benchmark_holding h
    JOIN security_proxy sp ON sp.security_id = h.security_id
    WHERE (SELECT MAX(cal_date) FROM trading_calendar WHERE is_trading_day = 1 AND cal_date <= h.as_at_date) <= sp.until_date
),
priced AS (
    SELECT e.*, x.close_zar FROM ends e JOIN stg_proxy_price x USING (security_id, price_date)
)
SELECT b.security_id, a.as_at_year AS from_year, b.as_at_year AS to_year,
       b.price_zar / a.price_zar - 1 AS satrix_return, b.close_zar / a.close_zar - 1 AS proxy_return,
       (b.close_zar / a.close_zar) - (b.price_zar / a.price_zar) AS difference
FROM priced a
JOIN priced b ON b.security_id = a.security_id AND b.as_at_year = a.as_at_year + 1;

DROP VIEW IF EXISTS dq_proxy_year_end;
CREATE VIEW dq_proxy_year_end AS
SELECT * FROM v_proxy_year_end WHERE ABS(difference) > 0.02;

-- Where the JSE series and the proxy both exist, their monthly returns side by side: the evidence the proxy tracks
DROP VIEW IF EXISTS v_proxy_overlap;
CREATE VIEW v_proxy_overlap AS
WITH month_end AS (
    SELECT sp.security_id, substr(c.cal_date, 1, 7) AS month, MAX(c.cal_date) AS price_date
    FROM security_proxy sp
    JOIN trading_calendar c ON c.is_trading_day = 1
    GROUP BY 1, 2
),
both_prices AS (
    SELECT m.security_id, m.month, m.price_date, j.close_value AS jse_zar,
           (SELECT p.close_value * f.close_value
            FROM stg_price p, stg_price f
            WHERE p.security_id = sp.proxy_id AND f.security_id = sp.fx_id
              AND p.price_date = (SELECT MAX(price_date) FROM stg_price WHERE security_id = sp.proxy_id AND price_date <= m.price_date)
              AND f.price_date = (SELECT MAX(price_date) FROM stg_price WHERE security_id = sp.fx_id AND price_date <= m.price_date)) AS proxy_zar
    FROM month_end m
    JOIN security_proxy sp ON sp.security_id = m.security_id
    JOIN stg_price j ON j.security_id = sp.compare_with AND j.price_date = m.price_date
),
returns AS (
    SELECT security_id, month,
           jse_zar / LAG(jse_zar) OVER w - 1 AS jse_return,
           proxy_zar / LAG(proxy_zar) OVER w - 1 AS proxy_return
    FROM both_prices
    WINDOW w AS (PARTITION BY security_id ORDER BY month)
)
SELECT security_id, month, jse_return, proxy_return, proxy_return - jse_return AS difference
FROM returns
WHERE jse_return IS NOT NULL;
