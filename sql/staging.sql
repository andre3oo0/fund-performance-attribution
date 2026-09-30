-- Staging: the latest snapshot of each series, in rands (or index points), with every problem flagged, never repaired.

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
                WHEN r.reported_unit = 'ZAc' THEN 0.01
                WHEN r.reported_unit = 'ZAR' THEN 1.0 END AS to_value,
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
SELECT security_id, role, vendor_symbol, snapshot_date, price_date, reported_unit,
       close AS close_reported,
       close * to_value AS close_value,  -- rands for shares and funds, points for the index
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
