"""Tests for the REST API. The database is swapped for a fake one, so no database is needed."""
import pytest
from fastapi.testclient import TestClient

import api.main as main

client = TestClient(main.app)

FAKE_TICKER = {"symbol": "AAPL", "name": "Apple Inc.", "sector": "Technology", "exchange": "NASDAQ"}
FAKE_PRICE = {"trade_date": "2026-10-09", "open": 331.7, "high": 338.61, "low": 330.7,
              "close": 336.64, "adj_close": 336.64, "volume": 37855000}


def fake_query(sql, params=()):
    """Stand-in for the real database: returns canned answers based on the SQL it receives."""
    if "FROM tickers WHERE symbol" in sql:          # "does this ticker exist?"
        return [{"exists": 1}] if params[0] == "AAPL" else []
    if "FROM tickers" in sql:
        return [FAKE_TICKER]
    if "FROM daily_prices" in sql:
        return [FAKE_PRICE]
    return [{"ok": 1}]                              # SELECT 1 for the health check


@pytest.fixture(autouse=True)
def fake_database(monkeypatch):
    """Before every test, replace the real query() with fake_query()."""
    monkeypatch.setattr(main, "query", fake_query)


def test_health_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_reports_database_down(monkeypatch):
    def broken_query(sql, params=()):
        raise ConnectionError("database is down")

    monkeypatch.setattr(main, "query", broken_query)
    assert client.get("/health").status_code == 503


def test_root_redirects_to_docs():
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/docs"


def test_tickers_returns_a_list():
    response = client.get("/tickers")
    assert response.status_code == 200
    assert response.json() == [FAKE_TICKER]


def test_prices_accept_lowercase_symbols():
    response = client.get("/prices/aapl")
    assert response.status_code == 200
    assert response.json()[0]["close"] == 336.64


def test_unknown_ticker_returns_404():
    response = client.get("/prices/FAKE999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Ticker 'FAKE999' not found"


def test_start_after_end_returns_400():
    response = client.get("/prices/AAPL?start=2026-10-05&end=2026-09-01")
    assert response.status_code == 400


@pytest.mark.parametrize("url", [
    "/prices/AAPL?limit=0",
    "/prices/AAPL?limit=1001",
    "/prices/AAPL?start=not-a-date",
])
def test_invalid_input_returns_422(url):
    assert client.get(url).status_code == 422