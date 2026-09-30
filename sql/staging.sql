-- Staging: the latest snapshot of each series, in its currency's main unit, with every problem flagged, never repaired.

DROP TABLE IF EXISTS stg_price;
CREATE TABLE stg_price AS
WITH latest AS (
    SELECT source, vendor_symbol, MAX(snapshot_date) AS snapshot_date
    FROM raw_price
    GROUP BY 1, 2
),
bars AS (
    SELECT i.security_id, i.role, r.vendor_symbol, r.snapshot_date, r.price_date, r.close, r.volume,
           r.dividends, r.splits, r.reported_unit,
           CASE WHEN i.role = 'index' THEN 1.0
                WHEN r.reported_unit IN ('ZAc', 'GBp') THEN 0.01  -- cents and pence
                WHEN r.reported_unit IN ('ZAR', 'GBP', 'CHF') THEN 1.0 END AS to_value,
           CASE WHEN i.role = 'index' THEN 'points'
                WHEN r.reported_unit IN ('ZAc', 'ZAR') THEN 'ZAR'
                WHEN r.reported_unit IN ('GBp', 'GBP') THEN 'GBP'
                WHEN r.reported_unit = 'CHF' THEN 'CHF' END AS currency,
           COALESCE(c.is_trading_day, 0) AS is_trading_day, r.run_id
    FROM raw_price r
    JOIN latest l USING (source, vendor_symbol, snapshot_date)
    JOIN instrument i ON i.vendor_symbol = r.vendor_symbol
    LEFT JOIN trading_calendar c ON c.cal_date = r.price_date
    WHERE r.close IS NOT NULL
),
neighbours AS (
    SELECT *,
           LAG(close) OVER w AS prev_close,
           LAG(close, 2) OVER w AS prev2_close,
           LEAD(close) OVER w AS next_close,
           CASE WHEN close = LAG(close) OVER w THEN 0 ELSE 1 END AS new_level
    FROM bars
    WINDOW w AS (PARTITION BY vendor_symbol ORDER BY price_date)
),
levels AS (
    SELECT *, SUM(new_level) OVER (PARTITION BY vendor_symbol ORDER BY price_date) AS level_id
    FROM neighbours
)
SELECT security_id, role, vendor_symbol, snapshot_date, price_date, reported_unit, currency,
       close AS close_reported,
       close * to_value AS close_value,  -- rands for JSE series, points for the index, the listing's currency for a proxy
       dividends AS dividend_reported,
       dividends * to_value AS dividend_value,
       volume, splits, is_trading_day,
       -- A 20x move is a unit error, not a market move: one day if it reverses, a step change if it stays
       CASE WHEN close * 20 <= prev_close AND close * 20 <= next_close THEN 'too_small'
            WHEN close >= prev_close * 20 AND close >= next_close * 20 THEN 'too_large'
            WHEN (close * 20 <= prev_close OR close >= prev_close * 20)
                 AND (prev2_close IS NULL OR close * 20 <= prev2_close OR close >= prev2_close * 20)
                 THEN 'step_change' END AS unit_anomaly,  -- the day after a one-day error is a recovery, not a step
       ROW_NUMBER() OVER (PARTITION BY vendor_symbol, level_id ORDER BY price_date) AS stale_days,
       to_value IS NULL AS unit_unknown,
       run_id
FROM levels;

CREATE INDEX ix_stg_price ON stg_price (security_id, price_date);
CREATE INDEX ix_stg_price_symbol ON stg_price (vendor_symbol, dividend_reported);

-- Every distribution as received; a repeat of the same amount within 45 days is flagged on every row of the cluster
DROP TABLE IF EXISTS stg_distribution;
CREATE TABLE stg_distribution AS
SELECT d.security_id, d.vendor_symbol, d.price_date AS vendor_date, d.dividend_reported AS amount_reported,
       d.dividend_value AS amount_value, d.reported_unit,
       (SELECT COUNT(*) FROM stg_price o
        WHERE o.vendor_symbol = d.vendor_symbol AND o.dividend_reported = d.dividend_reported
          AND ABS(julianday(o.price_date) - julianday(d.price_date)) <= 45) AS cluster_size,
       (SELECT MIN(o.price_date) FROM stg_price o
        WHERE o.vendor_symbol = d.vendor_symbol AND o.dividend_reported = d.dividend_reported
          AND ABS(julianday(o.price_date) - julianday(d.price_date)) <= 45) AS cluster_first_date
FROM stg_price d
WHERE d.dividend_reported > 0;

DROP TABLE IF EXISTS stg_rate;
CREATE TABLE stg_rate AS
WITH latest AS (
    SELECT series, MAX(snapshot_date) AS snapshot_date FROM raw_rate GROUP BY 1
)
SELECT r.series, r.snapshot_date, r.period AS rate_date, r.value_pct,
       r.value_pct / 100.0 AS rate,  -- stored as a fraction
       COALESCE(c.is_trading_day, 0) AS is_trading_day
FROM raw_rate r
JOIN latest l USING (series, snapshot_date)
LEFT JOIN trading_calendar c ON c.cal_date = r.period;

-- Benchmark holdings at each year-end, from the statement for that year where there is one, else the next year's
DROP TABLE IF EXISTS stg_benchmark_holding;
CREATE TABLE stg_benchmark_holding AS
WITH chosen AS (
    SELECT as_at_year, MIN(CASE WHEN statement_year = as_at_year THEN 0 ELSE 1 END) AS pref
    FROM raw_statement_total
    GROUP BY 1
),
source AS (
    SELECT t.as_at_year, t.statement_year, t.total_zar
    FROM raw_statement_total t
    JOIN chosen c ON c.as_at_year = t.as_at_year
     AND (CASE WHEN t.statement_year = t.as_at_year THEN 0 ELSE 1 END) = c.pref
)
SELECT h.as_at_year, h.as_at_year || '-12-31' AS as_at_date, h.statement_year, h.satrix_name,
       a.security_id, s.icb_industry, h.shares, h.price_zar, h.fair_value_zar,
       h.fair_value_zar / src.total_zar AS weight,  -- from rands; the printed weight is rounded to 0.1%
       h.weight_printed
FROM raw_statement_holding h
JOIN source src ON src.as_at_year = h.as_at_year AND src.statement_year = h.statement_year
LEFT JOIN security_alias a ON a.satrix_name = h.satrix_name AND h.as_at_year BETWEEN a.from_year AND a.to_year
LEFT JOIN security s ON s.security_id = a.security_id;

-- A proxy's close in rand on every JSE trading day it stands in for; the latest close and rate on or before each day
DROP TABLE IF EXISTS stg_proxy_price;
CREATE TABLE stg_proxy_price AS
WITH days AS MATERIALIZED (
    SELECT sp.security_id, sp.proxy_id, sp.fx_id, c.cal_date AS price_date
    FROM security_proxy sp
    JOIN trading_calendar c ON c.is_trading_day = 1 AND c.cal_date <= sp.until_date
     AND c.cal_date >= (SELECT MIN(price_date) FROM stg_price WHERE security_id = sp.proxy_id)
),
matched AS MATERIALIZED (
    SELECT d.*,
           (SELECT MAX(price_date) FROM stg_price p WHERE p.security_id = d.proxy_id AND p.price_date <= d.price_date) AS proxy_date,
           (SELECT MAX(price_date) FROM stg_price p WHERE p.security_id = d.fx_id AND p.price_date <= d.price_date) AS fx_date
    FROM days d
)
SELECT m.security_id, m.price_date, m.proxy_id, m.proxy_date, p.currency, p.close_value AS close_local,
       m.fx_date, f.close_value AS fx_rate, p.close_value * f.close_value AS close_zar,
       CASE WHEN p.price_date = m.price_date THEN p.dividend_value * f.close_value END AS dividend_zar,  -- gross, before foreign withholding tax
       m.proxy_date < m.price_date AS proxy_carried,  -- the foreign market was closed that day
       m.fx_date < m.price_date AS fx_carried
FROM matched m
JOIN stg_price p ON p.security_id = m.proxy_id AND p.price_date = m.proxy_date
JOIN stg_price f ON f.security_id = m.fx_id AND f.price_date = m.fx_date;
