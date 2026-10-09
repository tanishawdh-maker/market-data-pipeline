-- =====================================================================
-- Schema tests: run AFTER 001_schema.sql and 002_seed_tickers.sql.
--   psql -h localhost -U postgres -f sql/003_test_schema.sql
--
-- Everything runs inside one transaction that is rolled back at the
-- end, so no test data is left behind.
-- =====================================================================
\set ON_ERROR_STOP on
BEGIN;

-- ---------------------------------------------------------------------
-- Helper: run a statement that SHOULD fail, and report whether the
-- database rejected it.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION pg_temp.expect_rejected(test_name TEXT, stmt TEXT)
RETURNS TEXT AS $$
BEGIN
    EXECUTE stmt;
    RETURN 'FAIL  ' || test_name || '  (bad row was accepted!)';
EXCEPTION WHEN check_violation OR foreign_key_violation
               OR unique_violation OR not_null_violation THEN
    RETURN 'PASS  ' || test_name || '  -> ' || SQLERRM;
END;
$$ LANGUAGE plpgsql;

-- A pipeline run for the test rows to belong to.
INSERT INTO pipeline_runs (status) VALUES ('running');

-- ---------------------------------------------------------------------
-- Test 1: good rows load. 25 consecutive weekdays of AAPL, so the
-- 20-day window metrics below have enough history.
-- ---------------------------------------------------------------------
INSERT INTO daily_prices (symbol, trade_date, open, high, low, close, adj_close, volume, run_id)
SELECT 'AAPL',
       d::date,
       200 + n,              -- open
       200 + n + 3,          -- high
       200 + n - 2,          -- low
       200 + n + 1,          -- close
       200 + n + 1,          -- adj_close
       50000000 + n * 1000,  -- volume
       currval('pipeline_runs_run_id_seq')
FROM (
    SELECT d, ROW_NUMBER() OVER (ORDER BY d) AS n
    FROM generate_series('2026-09-01'::date, '2026-10-09'::date, interval '1 day') AS d
    WHERE EXTRACT(ISODOW FROM d) BETWEEN 1 AND 5
) days
LIMIT 25;

SELECT 'PASS  good rows loaded: ' || COUNT(*) AS result FROM daily_prices WHERE symbol = 'AAPL';

-- ---------------------------------------------------------------------
-- Test 2: the database rejects bad data on its own.
-- ---------------------------------------------------------------------
SELECT pg_temp.expect_rejected('duplicate bar (same symbol + date)',
  $q$INSERT INTO daily_prices (symbol, trade_date, open, high, low, close, volume)
     VALUES ('AAPL', '2026-09-01', 200, 203, 198, 201, 1000)$q$) AS result
UNION ALL
SELECT pg_temp.expect_rejected('high below low',
  $q$INSERT INTO daily_prices (symbol, trade_date, open, high, low, close, volume)
     VALUES ('MSFT', '2026-09-01', 400, 390, 395, 398, 1000)$q$)
UNION ALL
SELECT pg_temp.expect_rejected('negative price',
  $q$INSERT INTO daily_prices (symbol, trade_date, open, high, low, close, volume)
     VALUES ('MSFT', '2026-09-02', -5, 10, -5, 8, 1000)$q$)
UNION ALL
SELECT pg_temp.expect_rejected('negative volume',
  $q$INSERT INTO daily_prices (symbol, trade_date, open, high, low, close, volume)
     VALUES ('MSFT', '2026-09-03', 400, 405, 398, 401, -1)$q$)
UNION ALL
SELECT pg_temp.expect_rejected('weekend bar (Saturday)',
  $q$INSERT INTO daily_prices (symbol, trade_date, open, high, low, close, volume)
     VALUES ('MSFT', '2026-09-05', 400, 405, 398, 401, 1000)$q$)
UNION ALL
SELECT pg_temp.expect_rejected('unknown ticker',
  $q$INSERT INTO daily_prices (symbol, trade_date, open, high, low, close, volume)
     VALUES ('FAKE', '2026-09-01', 10, 11, 9, 10, 1000)$q$)
UNION ALL
SELECT pg_temp.expect_rejected('lowercase symbol',
  $q$INSERT INTO tickers (symbol, name) VALUES ('aapl', 'Apple lowercase')$q$)
UNION ALL
SELECT pg_temp.expect_rejected('metric for a bar that does not exist',
  $q$INSERT INTO daily_metrics (symbol, trade_date, daily_return)
     VALUES ('MSFT', '2026-09-01', 0.01)$q$);

-- ---------------------------------------------------------------------
-- Test 3: the upsert is idempotent. Running the same load twice must
-- not create duplicates, and corrected data must replace old data.
-- This is the exact pattern the Phase 2 load step will use.
-- ---------------------------------------------------------------------
INSERT INTO daily_prices (symbol, trade_date, open, high, low, close, adj_close, volume)
VALUES ('AAPL', '2026-09-01', 201, 204, 199, 202.50, 202.50, 51000000)
ON CONFLICT (symbol, trade_date) DO UPDATE SET
    open        = EXCLUDED.open,
    high        = EXCLUDED.high,
    low         = EXCLUDED.low,
    close       = EXCLUDED.close,
    adj_close   = EXCLUDED.adj_close,
    volume      = EXCLUDED.volume,
    ingested_at = now();

SELECT CASE WHEN COUNT(*) = 25 AND MAX(close) FILTER (WHERE trade_date = '2026-09-01') = 202.50
            THEN 'PASS  upsert updated the existing row without creating a duplicate'
            ELSE 'FAIL  upsert' END AS result
FROM daily_prices WHERE symbol = 'AAPL';

-- ---------------------------------------------------------------------
-- Test 4: preview of the Phase 2 metrics step, using window functions.
--   LAG()                   previous day's close  -> daily return
--   AVG() OVER 20 rows      20-day moving average
--   STDDEV_SAMP() OVER      20-day volatility of returns
-- Windows with fewer than 20 days of history return NULL instead of a
-- misleading partial value.
-- ---------------------------------------------------------------------
WITH returns AS (
    SELECT symbol, trade_date, close,
           close / LAG(close) OVER w - 1 AS daily_return
    FROM daily_prices
    WINDOW w AS (PARTITION BY symbol ORDER BY trade_date)
),
windowed AS (
    SELECT symbol, trade_date, daily_return,
           AVG(close)                 OVER w20 AS ma_20,
           STDDEV_SAMP(daily_return)  OVER w20 AS volatility_20,
           COUNT(*)                   OVER w20 AS days_in_window,
           COUNT(daily_return)        OVER w20 AS returns_in_window
    FROM returns
    WINDOW w20 AS (PARTITION BY symbol ORDER BY trade_date
                   ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)
)
INSERT INTO daily_metrics (symbol, trade_date, daily_return, ma_20, volatility_20)
SELECT symbol, trade_date, daily_return,
       CASE WHEN days_in_window    = 20 THEN ma_20         END,
       CASE WHEN returns_in_window = 20 THEN volatility_20 END
FROM windowed
ON CONFLICT (symbol, trade_date) DO UPDATE SET
    daily_return  = EXCLUDED.daily_return,
    ma_20         = EXCLUDED.ma_20,
    volatility_20 = EXCLUDED.volatility_20,
    computed_at   = now();

SELECT trade_date,
       ROUND(daily_return, 5)  AS daily_return,
       ROUND(ma_20, 2)         AS ma_20,
       ROUND(volatility_20, 5) AS volatility_20
FROM daily_metrics
WHERE symbol = 'AAPL'
ORDER BY trade_date DESC
LIMIT 6;

ROLLBACK;  -- remove all test data
