"""Tests for the transform step: cleaning raw data and validating it."""
import datetime

import pandas as pd
import pytest

from transform import clean_prices, validate

# One healthy row, shaped exactly like yfinance output.
GOOD_ROW = {
    "Open": 100.0, "High": 102.0, "Low": 99.0, "Close": 101.0, "Adj Close": 101.0,
    "Volume": 1000, "Dividends": 0.0, "Stock Splits": 0.0,
}


def make_raw(*rows):
    """Build fake yfinance data. Each row is (date, {column: new_value}) applied to a good row."""
    records = [{**GOOD_ROW, **changes} for _, changes in rows]
    index = pd.DatetimeIndex([date for date, _ in rows], name="Date").tz_localize("America/New_York")
    return pd.DataFrame(records, index=index)


def run_transform(*rows):
    """Clean and validate fake rows, the same way the pipeline does."""
    return validate(clean_prices(make_raw(*rows), "aapl"))


def test_clean_prices_matches_the_database_table():
    clean = clean_prices(make_raw(("2026-09-14", {"High": 102.123456})), "aapl")

    assert list(clean.columns) == [
        "symbol", "trade_date", "open", "high", "low", "close", "adj_close", "volume",
    ]
    assert clean.loc[0, "symbol"] == "AAPL"                          # uppercased
    assert clean.loc[0, "trade_date"] == datetime.date(2026, 9, 14)  # time and timezone removed
    assert clean.loc[0, "high"] == 102.1235                          # rounded to 4 decimals


def test_good_rows_pass_validation():
    good, rejected = run_transform(("2026-09-14", {}), ("2026-09-15", {}))

    assert len(good) == 2
    assert rejected == []


@pytest.mark.parametrize(
    "date, changes, expected_check",
    [
        ("2026-09-14", {"Close": None}, "missing_values"),
        ("2026-09-14", {"Open": -5.0, "Low": -5.0}, "non_positive_price"),
        ("2026-09-14", {"High": 98.0}, "high_not_highest"),
        ("2026-09-14", {"Low": 101.5}, "low_not_lowest"),
        ("2026-09-14", {"Volume": -1}, "negative_volume"),
        ("2026-09-19", {}, "weekend_date"),                          # a Saturday
    ],
)
def test_each_rule_rejects_bad_data(date, changes, expected_check):
    good, rejected = run_transform((date, changes))

    assert len(good) == 0
    assert expected_check in {r["check_name"] for r in rejected}


def test_duplicate_date_keeps_the_first_copy():
    good, rejected = run_transform(("2026-09-14", {}), ("2026-09-14", {"Close": 101.5}))

    assert len(good) == 1
    assert good.iloc[0]["close"] == 101.0
    assert [r["check_name"] for r in rejected] == ["duplicate_date"]


def test_one_bad_row_does_not_block_the_good_rows():
    good, rejected = run_transform(
        ("2026-09-14", {}), ("2026-09-15", {"Volume": -1}), ("2026-09-16", {}),
    )

    assert len(good) == 2
    assert len(rejected) == 1


def test_dividend_only_row_is_rejected():
    """Regression test for the real CME bug: yfinance sent a row with no prices, only a dividend."""
    no_prices = {"Open": None, "High": None, "Low": None, "Close": None, "Adj Close": None,
                 "Volume": 0, "Dividends": 1.3}
    good, rejected = run_transform(("2026-09-09", no_prices), ("2026-09-10", {}))

    assert len(good) == 1
    assert good.iloc[0]["trade_date"] == datetime.date(2026, 9, 10)
    assert rejected[0]["check_name"] == "missing_values"