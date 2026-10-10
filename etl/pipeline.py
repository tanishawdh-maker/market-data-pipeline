"""Run the full ETL pipeline (extract -> transform -> load) for every active ticker.

Usage:
    python etl/pipeline.py          # last month of prices
    python etl/pipeline.py 1y       # last year (a backfill)
"""
import sys

from db import get_connection
from extract import fetch_prices
from load import finish_run, load_prices, log_rejections, start_run
from metrics import compute_metrics
from transform import clean_prices, validate


def get_active_symbols(conn):
    """Return the list of tickers the pipeline should process."""
    with conn.cursor() as cur:
        cur.execute("SELECT symbol FROM tickers WHERE is_active ORDER BY symbol")
        return [row[0] for row in cur.fetchall()]


def run_pipeline(period="1mo"):
    """Process every active ticker. Returns True if every ticker succeeded."""
    with get_connection() as conn:
        run_id = start_run(conn)
        symbols = get_active_symbols(conn)
        print(f"Run {run_id}: processing {len(symbols)} tickers (period={period})\n")

        extracted = loaded = rejected_count = 0
        failed = []

        for symbol in symbols:
            try:
                raw = fetch_prices(symbol, period)
                clean = clean_prices(raw, symbol)
                good, rejected = validate(clean)

                rows_loaded = load_prices(conn, good, run_id)
                log_rejections(conn, run_id, rejected)

                extracted += len(clean)
                loaded += rows_loaded
                rejected_count += len(rejected)
                print(f"  OK    {symbol:6} {rows_loaded:4} loaded, {len(rejected)} rejected")

            except Exception as error:
                conn.rollback()            # undo this ticker's half-finished work
                failed.append(symbol)
                print(f"  FAIL  {symbol:6} {error}")
        metric_rows = compute_metrics(conn)
        print(f"\n  Metrics computed for {metric_rows} rows")
        status = "success" if not failed else "failed"
        error_message = f"Failed tickers: {', '.join(failed)}" if failed else None
        finish_run(conn, run_id, status, extracted, loaded, rejected_count, error_message)

    print(f"\nRun {run_id} {status.upper()}: {loaded} rows loaded, "
          f"{rejected_count} rejected, {len(failed)} tickers failed")
    return not failed


if __name__ == "__main__":
    period = sys.argv[1] if len(sys.argv) > 1 else "1mo"
    succeeded = run_pipeline(period)
    sys.exit(0 if succeeded else 1)    # exit code 1 tells schedulers like Airflow the run failed