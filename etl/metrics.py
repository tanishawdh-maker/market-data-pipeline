"""Metrics: compute daily returns, 20-day moving averages, and volatility with SQL window functions."""

METRICS_SQL = """
WITH returns AS (
    SELECT
        symbol,
        trade_date,
        close,
        COALESCE(adj_close, close)
            / LAG(COALESCE(adj_close, close)) OVER by_day - 1      AS daily_return
    FROM daily_prices
    WINDOW by_day AS (PARTITION BY symbol ORDER BY trade_date)
),
windowed AS (
    SELECT
        symbol,
        trade_date,
        daily_return,
        AVG(close)                OVER last_20 AS ma_20,
        STDDEV_SAMP(daily_return) OVER last_20 AS volatility_20,
        COUNT(*)                  OVER last_20 AS days_in_window,
        COUNT(daily_return)       OVER last_20 AS returns_in_window
    FROM returns
    WINDOW last_20 AS (PARTITION BY symbol ORDER BY trade_date
                       ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)
)
INSERT INTO daily_metrics (symbol, trade_date, daily_return, ma_20, volatility_20)
SELECT
    symbol,
    trade_date,
    daily_return,
    CASE WHEN days_in_window    = 20 THEN ma_20         END,
    CASE WHEN returns_in_window = 20 THEN volatility_20 END
FROM windowed
ON CONFLICT (symbol, trade_date) DO UPDATE SET
    daily_return  = EXCLUDED.daily_return,
    ma_20         = EXCLUDED.ma_20,
    volatility_20 = EXCLUDED.volatility_20,
    computed_at   = now()
"""


def compute_metrics(conn):
    """Recompute metrics for every price row. Returns the number of metric rows written."""
    with conn.cursor() as cur:
        cur.execute(METRICS_SQL)
        written = cur.rowcount
    conn.commit()
    return written


if __name__ == "__main__":
    from db import get_connection

    with get_connection() as conn:
        written = compute_metrics(conn)
    print(f"Computed metrics for {written} rows")