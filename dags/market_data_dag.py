"""
Market Data Pipeline DAG.

Runs every weekday at 5:30 PM New York time, after the US stock market closes:
start_run -> get_symbols -> process_ticker (one task per stock) -> compute_metrics -> finish_run
"""
from datetime import timedelta

import pendulum
from airflow.sdk import Param, dag, get_current_context, task
from airflow.sdk.exceptions import AirflowFailException

default_args = {
    "owner": "tanisha",
    "retries": 2,                          # retry a failed task twice...
    "retry_delay": timedelta(minutes=5),   # ...waiting 5 minutes between attempts
}


@dag(
    dag_id="market_data_pipeline",
    schedule="30 17 * * 1-5",              # minute 30, hour 17, any day, any month, Monday-Friday
    start_date=pendulum.datetime(2026, 10, 1, tz="America/New_York"),
    catchup=False,                         # don't go back and run for every missed past day
    max_active_runs=1,                     # never run two copies at once; extra runs wait in a queue
    default_args=default_args,
    tags=["market-data", "etl"],
    params={
        # Shown as a form when you trigger the DAG by hand. Scheduled runs use the default.
        "period": Param("1mo", type="string", enum=["5d", "1mo", "3mo", "6mo", "1y", "2y"],
                        description="How much price history to download (use 1y for a backfill)"),
    },
    doc_md=__doc__,
)
def market_data_pipeline():

    @task
    def start_run():
        """Create a pipeline_runs row and pass its ID to the other tasks."""
        from db import get_connection
        from load import start_run as db_start_run

        with get_connection() as conn:
            return db_start_run(conn)

    @task
    def get_symbols():
        """Read the list of active tickers from the database."""
        from db import get_connection
        from pipeline import get_active_symbols

        with get_connection() as conn:
            return get_active_symbols(conn)

    @task(max_active_tis_per_dagrun=4)     # at most 4 stocks at once, to be polite to Yahoo
    def process_ticker(symbol, pipeline_run_id):
        """Extract, validate, and load one stock."""
        from db import get_connection
        from extract import fetch_prices
        from load import load_prices, log_rejections
        from transform import clean_prices, validate

        period = get_current_context()["params"]["period"]
        raw = fetch_prices(symbol, period)
        good, rejected = validate(clean_prices(raw, symbol))

        with get_connection() as conn:
            loaded = load_prices(conn, good, pipeline_run_id)
            log_rejections(conn, pipeline_run_id, rejected)

        print(f"{symbol}: {loaded} rows loaded, {len(rejected)} rejected")
        return {
            "symbol": symbol,
            "loaded": loaded,
            "rejected": len(rejected),
            "rejected_rows": len({(r["symbol"], r["trade_date"]) for r in rejected}),
        }

    @task(trigger_rule="all_done")         # run even if some stocks failed
    def compute_metrics():
        """Recompute returns, moving averages, and volatility."""
        from db import get_connection
        from metrics import compute_metrics as db_compute_metrics

        with get_connection() as conn:
            written = db_compute_metrics(conn)
        print(f"Metrics computed for {written} rows")

    @task(trigger_rule="all_done")         # always record how the run ended
    def finish_run(pipeline_run_id, symbols, results):
        """Record the run's results, and fail loudly if any stock failed."""
        from db import get_connection
        from load import finish_run as db_finish_run

        results = [r for r in results if r]                # failed stocks send back no result
        loaded = sum(r["loaded"] for r in results)
        rejected = sum(r["rejected"] for r in results)
        extracted = loaded + sum(r["rejected_rows"] for r in results)

        failed = sorted(set(symbols) - {r["symbol"] for r in results})
        status = "failed" if failed else "success"
        error_message = f"Failed tickers: {', '.join(failed)}" if failed else None

        with get_connection() as conn:
            db_finish_run(conn, pipeline_run_id, status, extracted, loaded, rejected, error_message)

        print(f"Run {pipeline_run_id} {status}: {loaded} loaded, {rejected} rejected, {len(failed)} failed")
        if failed:
            raise AirflowFailException(error_message)   # mark the Airflow run as failed, no retries

    pipeline_run_id = start_run()
    symbols = get_symbols()
    results = process_ticker.partial(pipeline_run_id=pipeline_run_id).expand(symbol=symbols)
    metrics = compute_metrics()

    results >> metrics >> finish_run(pipeline_run_id, symbols, results)


market_data_pipeline()