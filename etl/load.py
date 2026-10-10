"""Load: write validated price rows into PostgreSQL with an idempotent upsert."""

UPSERT_SQL = """
    INSERT INTO daily_prices
        (symbol, trade_date, open, high, low, close, adj_close, volume, run_id)
    VALUES
        (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (symbol, trade_date) DO UPDATE SET
        open        = EXCLUDED.open,
        high        = EXCLUDED.high,
        low         = EXCLUDED.low,
        close       = EXCLUDED.close,
        adj_close   = EXCLUDED.adj_close,
        volume      = EXCLUDED.volume,
        run_id      = EXCLUDED.run_id,
        ingested_at = now()
"""

LOAD_COLUMNS = ["symbol", "trade_date", "open", "high", "low", "close", "adj_close", "volume"]


def load_prices(conn, df, run_id=None):
    """Upsert every row of df into daily_prices. Returns the number of rows loaded."""
    clean = df[LOAD_COLUMNS].astype(object)          # numpy numbers -> plain Python numbers
    clean = clean.where(clean.notna(), None)          # NaN -> None, which becomes NULL in SQL

    rows = [tuple(row) + (run_id,) for row in clean.itertuples(index=False)]

    with conn.cursor() as cur:
        cur.executemany(UPSERT_SQL, rows)
    conn.commit()                                     # make the changes permanent
    return len(rows)


if __name__ == "__main__":
    from db import get_connection
    from extract import fetch_prices
    from transform import clean_prices, validate

    raw = fetch_prices("AAPL")
    good, rejected = validate(clean_prices(raw, "AAPL"))

    with get_connection() as conn:
        loaded = load_prices(conn, good)
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM daily_prices WHERE symbol = 'AAPL'")
            total = cur.fetchone()[0]

    print(f"Loaded {loaded} rows. AAPL rows now in the database: {total}")