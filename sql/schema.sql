-- Raw layer: what each landed file said, loaded unchanged; everything else is derived from it.
PRAGMA user_version = 2;

CREATE TABLE IF NOT EXISTS ingest_run (
    run_id          TEXT PRIMARY KEY,
    source          TEXT NOT NULL,
    snapshot_date   TEXT NOT NULL,
    fetched_at      TEXT NOT NULL,
    session_cutoff  TEXT NOT NULL,
    rows_landed     INTEGER NOT NULL,
    landing_path    TEXT NOT NULL,
    landing_sha256  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ingest_symbol_status (
    run_id          TEXT NOT NULL REFERENCES ingest_run (run_id),
    vendor_symbol   TEXT NOT NULL,
    status          TEXT NOT NULL,
    row_count       INTEGER NOT NULL,
    reported_unit   TEXT,
    error           TEXT
);

CREATE TABLE IF NOT EXISTS instrument (
    security_id     TEXT PRIMARY KEY,
    vendor_symbol   TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL,
    role            TEXT NOT NULL CHECK (role IN ('benchmark', 'index', 'share'))
);

-- No primary key: a vendor's duplicate rows must reach the checks, not vanish on load
CREATE TABLE IF NOT EXISTS raw_price (
    source          TEXT NOT NULL,
    snapshot_date   TEXT NOT NULL,
    vendor_symbol   TEXT NOT NULL,
    price_date      TEXT NOT NULL,
    open            REAL,
    high            REAL,
    low             REAL,
    close           REAL,
    adj_close       REAL,
    volume          REAL,
    dividends       REAL,
    splits          REAL,
    reported_unit   TEXT,
    run_id          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS raw_rate (
    source          TEXT NOT NULL,
    snapshot_date   TEXT NOT NULL,
    series          TEXT NOT NULL,
    period          TEXT NOT NULL,
    value_pct       REAL,
    run_id          TEXT NOT NULL
);

-- Every Top 40 member in Satrix's statements, priced or not, and the names Satrix prints for it
CREATE TABLE IF NOT EXISTS security (
    security_id     TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    vendor_symbol   TEXT,
    icb_industry    TEXT NOT NULL,
    note            TEXT
);

CREATE TABLE IF NOT EXISTS security_alias (
    satrix_name     TEXT NOT NULL,
    security_id     TEXT NOT NULL REFERENCES security (security_id),
    from_year       INTEGER NOT NULL,
    to_year         INTEGER NOT NULL
);

-- Satrix 40's annual financial statements as printed: each gives its own year-end and the one before
CREATE TABLE IF NOT EXISTS raw_statement_holding (
    statement_year  INTEGER NOT NULL,
    as_at_year      INTEGER NOT NULL,
    satrix_name     TEXT NOT NULL,
    shares          REAL NOT NULL,
    price_zar       REAL NOT NULL,
    fair_value_zar  REAL NOT NULL,
    weight_printed  REAL NOT NULL,
    run_id          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS raw_statement_total (
    statement_year  INTEGER NOT NULL,
    as_at_year      INTEGER NOT NULL,
    total_zar       REAL NOT NULL,
    run_id          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS raw_statement_industry (
    statement_year  INTEGER NOT NULL,
    as_at_year      INTEGER NOT NULL,
    industry_printed TEXT NOT NULL,
    fair_value_zar  REAL NOT NULL,
    run_id          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trading_calendar (
    cal_date        TEXT PRIMARY KEY,
    is_trading_day  INTEGER NOT NULL,
    reason          TEXT
);
