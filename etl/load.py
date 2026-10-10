import json
import pandas as pd

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
def start_run(conn):
    """Record the start of a pipeline run. Returns the new run_id."""
    with conn.cursor() as cur:
        cur.execute("INSERT INTO pipeline_runs (status) VALUES ('running') RETURNING run_id")
        run_id = cur.fetchone()[0]
    conn.commit()
    return run_id


def log_rejections(conn, run_id, rejected):
    """Save every rejected row to data_quality_log, so nothing is silently dropped."""
    rows = []
    for r in rejected:
        raw = {k: (None if pd.isna(v) else v) for k, v in r["raw_record"].items()}  # NaN -> null
        rows.append((run_id, r["symbol"], r["trade_date"], r["check_name"], json.dumps(raw, default=str)))

    with conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO data_quality_log (run_id, symbol, trade_date, check_name, raw_record)
               VALUES (%s, %s, %s, %s, %s::jsonb)""",
            rows,
        )
    conn.commit()


def finish_run(conn, run_id, status, extracted, loaded, rejected, error_message=None):
    """Record how a pipeline run ended."""
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE pipeline_runs
               SET status = %s, finished_at = now(), rows_extracted = %s,
                   rows_loaded = %s, rows_rejected = %s, error_message = %s
               WHERE run_id = %s""",
            (status, extracted, loaded, rejected, error_message, run_id),
        )
    conn.commit()


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