-- =====================================================================
-- Market Data Pipeline: database schema (Phase 1)
-- PostgreSQL 16
--
-- Five tables:
--   tickers           what we track (one row per stock)
--   daily_prices      raw daily price bars from the data source
--   daily_metrics     values we compute from daily_prices
--   pipeline_runs     one row per pipeline execution (audit trail)
--   data_quality_log  every record we rejected, and why
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. tickers
-- The "dimension" table: descriptive info about each stock.
-- symbol is a natural primary key: it is short, unique, and it is what
-- every API call and every data source already uses.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tickers (
    symbol      VARCHAR(10)  PRIMARY KEY,
    name        TEXT         NOT NULL,
    sector      TEXT,
    exchange    TEXT,
    is_active   BOOLEAN      NOT NULL DEFAULT TRUE,   -- stop ingesting without deleting history
    added_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),

    -- Keep symbols in one consistent format, so 'aapl' and 'AAPL' can never both exist.
    CONSTRAINT symbol_is_uppercase CHECK (symbol = UPPER(symbol))
);

-- ---------------------------------------------------------------------
-- 2. pipeline_runs
-- One row per run of the pipeline. Every price row and every rejected
-- record points back to the run that produced it, so any number can be
-- traced to when and how it was loaded.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id          BIGSERIAL    PRIMARY KEY,
    airflow_run_id  TEXT,                              -- filled in once Airflow runs the pipeline (Phase 3)
    started_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ,
    status          TEXT         NOT NULL DEFAULT 'running',
    rows_extracted  INTEGER      NOT NULL DEFAULT 0,
    rows_loaded     INTEGER      NOT NULL DEFAULT 0,
    rows_rejected   INTEGER      NOT NULL DEFAULT 0,
    error_message   TEXT,

    CONSTRAINT valid_status   CHECK (status IN ('running', 'success', 'failed')),
    CONSTRAINT finish_after_start CHECK (finished_at IS NULL OR finished_at >= started_at),
    CONSTRAINT counts_non_negative CHECK (rows_extracted >= 0 AND rows_loaded >= 0 AND rows_rejected >= 0)
);

-- ---------------------------------------------------------------------
-- 3. daily_prices
-- The "fact" table: one row per stock per trading day (an OHLCV bar).
--
-- Composite primary key (symbol, trade_date) makes duplicate bars
-- impossible. It is also what makes the load step idempotent: the
-- upsert in Phase 2 uses ON CONFLICT (symbol, trade_date).
--
-- NUMERIC instead of FLOAT: money values must be exact. FLOAT can turn
-- 187.21 into 187.20999999.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS daily_prices (
    symbol       VARCHAR(10)    NOT NULL REFERENCES tickers(symbol),
    trade_date   DATE           NOT NULL,
    open         NUMERIC(14,4)  NOT NULL,
    high         NUMERIC(14,4)  NOT NULL,
    low          NUMERIC(14,4)  NOT NULL,
    close        NUMERIC(14,4)  NOT NULL,
    adj_close    NUMERIC(14,4),                       -- close adjusted for splits and dividends
    volume       BIGINT         NOT NULL,              -- BIGINT: volumes can exceed 2.1 billion
    source       TEXT           NOT NULL DEFAULT 'yfinance',
    run_id       BIGINT         REFERENCES pipeline_runs(run_id),
    ingested_at  TIMESTAMPTZ    NOT NULL DEFAULT now(),

    PRIMARY KEY (symbol, trade_date),

    -- The database itself refuses impossible price bars, even if a bug
    -- slips past the Python validation in Phase 2 (defense in depth).
    CONSTRAINT prices_positive    CHECK (open > 0 AND high > 0 AND low > 0 AND close > 0),
    CONSTRAINT high_is_highest    CHECK (high >= GREATEST(open, close, low)),
    CONSTRAINT low_is_lowest      CHECK (low  <= LEAST(open, close, high)),
    CONSTRAINT volume_non_negative CHECK (volume >= 0),
    CONSTRAINT no_weekend_bars    CHECK (EXTRACT(ISODOW FROM trade_date) BETWEEN 1 AND 5)
);

-- The primary key already serves queries that filter by symbol first
-- ("AAPL between two dates"). This index serves queries that filter by
-- date first ("every stock on 2026-10-08"), which the daily metrics
-- step and market-wide reports need.
CREATE INDEX IF NOT EXISTS idx_daily_prices_trade_date ON daily_prices (trade_date);

-- ---------------------------------------------------------------------
-- 4. daily_metrics
-- Derived values, kept separate from raw prices. Raw data stays
-- untouched, and metrics can be dropped and recomputed at any time
-- (for example after fixing a formula) without re-downloading anything.
--
-- The foreign key points at daily_prices, so a metric can never exist
-- for a bar that does not exist. ON DELETE CASCADE removes a bar's
-- metrics if the bar itself is deleted.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS daily_metrics (
    symbol          VARCHAR(10)    NOT NULL,
    trade_date      DATE           NOT NULL,
    daily_return    NUMERIC(12,8),                   -- NULL on the first day (no previous close)
    ma_20           NUMERIC(14,4),                   -- 20-day moving average of close
    volatility_20   NUMERIC(12,8),                   -- std. dev. of the last 20 daily returns
    computed_at     TIMESTAMPTZ    NOT NULL DEFAULT now(),

    PRIMARY KEY (symbol, trade_date),
    FOREIGN KEY (symbol, trade_date)
        REFERENCES daily_prices (symbol, trade_date) ON DELETE CASCADE,

    CONSTRAINT volatility_non_negative CHECK (volatility_20 IS NULL OR volatility_20 >= 0)
);

-- ---------------------------------------------------------------------
-- 5. data_quality_log
-- Bad records are logged here instead of being silently dropped.
-- raw_record keeps the original row exactly as received (JSONB), so a
-- rejected row can be inspected or replayed later.
-- symbol is deliberately NOT a foreign key: a bad record might carry
-- an unknown or misspelled symbol, and we still want to log it.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS data_quality_log (
    log_id      BIGSERIAL    PRIMARY KEY,
    run_id      BIGINT       REFERENCES pipeline_runs(run_id),
    symbol      VARCHAR(10),
    trade_date  DATE,
    check_name  TEXT         NOT NULL,                -- e.g. 'high_below_low', 'missing_close'
    details     TEXT,
    raw_record  JSONB,
    logged_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_dq_log_run ON data_quality_log (run_id);
