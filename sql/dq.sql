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
WHERE p.is_trading_day = 0;

-- Trading days inside a series' own date range with no bar
DROP VIEW IF EXISTS dq_missing_session;
CREATE VIEW dq_missing_session AS
WITH span AS (
    SELECT security_id, MIN(price_date) AS first_date, MAX(price_date) AS last_date
    FROM stg_price
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
