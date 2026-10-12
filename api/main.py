"""REST API: serve stock prices, metrics, and pipeline status from PostgreSQL."""
from datetime import date, datetime

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import RedirectResponse
from psycopg.rows import dict_row
from pydantic import BaseModel

from db import get_connection

app = FastAPI(
    title="Market Data API",
    description="Daily prices, trading metrics, and pipeline run history for 20 US stocks.",
    version="1.0.0",
)


# ---------- Response models: the exact shape of each answer ----------

class Ticker(BaseModel):
    symbol: str
    name: str
    sector: str | None
    exchange: str | None


class PriceBar(BaseModel):
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    adj_close: float | None
    volume: int


class Metric(BaseModel):
    trade_date: date
    close: float
    daily_return: float | None
    ma_20: float | None
    volatility_20: float | None


class PipelineRun(BaseModel):
    run_id: int
    status: str
    started_at: datetime
    finished_at: datetime | None
    rows_loaded: int
    rows_rejected: int
    error_message: str | None


# ---------- Helpers ----------

def query(sql, params=()):
    """Run a SELECT and return the rows as a list of dictionaries."""
    with get_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def require_ticker(symbol):
    """Return the symbol in uppercase, or answer 404 if we don't track it."""
    symbol = symbol.upper()
    if not query("SELECT 1 FROM tickers WHERE symbol = %s", (symbol,)):
        raise HTTPException(status_code=404, detail=f"Ticker '{symbol}' not found")
    return symbol


# ---------- Endpoints ----------
@app.get("/", include_in_schema=False)
def root():
    """Send visitors who open the bare address to the interactive docs."""
    return RedirectResponse(url="/docs")
@app.get("/health")
def health():
    """Check that the API is up and can reach the database."""
    try:
        query("SELECT 1")
    except Exception:
        raise HTTPException(status_code=503, detail="Database unavailable")
    return {"status": "ok"}


@app.get("/tickers", response_model=list[Ticker])
def list_tickers():
    """List every active ticker."""
    return query(
        "SELECT symbol, name, sector, exchange FROM tickers WHERE is_active ORDER BY symbol"
    )


@app.get("/prices/{symbol}", response_model=list[PriceBar])
def get_prices(
    symbol: str,
    start: date | None = Query(None, description="First date to include (YYYY-MM-DD)"),
    end: date | None = Query(None, description="Last date to include (YYYY-MM-DD)"),
    limit: int = Query(30, ge=1, le=1000, description="Maximum number of rows"),
):
    """Daily price bars for one stock, newest first."""
    symbol = require_ticker(symbol)
    if start and end and start > end:
        raise HTTPException(status_code=400, detail="start must be on or before end")

    return query(
        """
        SELECT trade_date, open, high, low, close, adj_close, volume
        FROM daily_prices
        WHERE symbol = %s
          AND (%s::date IS NULL OR trade_date >= %s::date)
          AND (%s::date IS NULL OR trade_date <= %s::date)
        ORDER BY trade_date DESC
        LIMIT %s
        """,
        (symbol, start, start, end, end, limit),
    )


@app.get("/metrics/{symbol}", response_model=list[Metric])
def get_metrics(symbol: str, limit: int = Query(30, ge=1, le=1000)):
    """Daily return, 20-day moving average, and 20-day volatility for one stock, newest first."""
    symbol = require_ticker(symbol)
    return query(
        """
        SELECT m.trade_date, p.close, m.daily_return, m.ma_20, m.volatility_20
        FROM daily_metrics m
        JOIN daily_prices p USING (symbol, trade_date)
        WHERE m.symbol = %s
        ORDER BY m.trade_date DESC
        LIMIT %s
        """,
        (symbol, limit),
    )


@app.get("/runs", response_model=list[PipelineRun])
def list_runs(limit: int = Query(10, ge=1, le=100)):
    """The most recent pipeline runs, newest first."""
    return query(
        """
        SELECT run_id, status, started_at, finished_at, rows_loaded, rows_rejected, error_message
        FROM pipeline_runs
        ORDER BY run_id DESC
        LIMIT %s
        """,
        (limit,),
    )