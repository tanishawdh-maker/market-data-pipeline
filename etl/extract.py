"""Extract: download daily stock prices from Yahoo Finance."""
import yfinance as yf
import pandas as pd
pd.set_option("display.width", 200)


def fetch_prices(symbol, period="1mo"):
    """Download daily price bars for one stock and return them as a pandas DataFrame."""
    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period, auto_adjust=False)
    if df.empty:
        raise ValueError(f"No price data returned for '{symbol}'. It may be misspelled or delisted.")
    return df


if __name__ == "__main__":
    prices = fetch_prices("AAPL")

    print("Shape (rows, columns):", prices.shape)
    print("\nColumns:", list(prices.columns))
    print("\nFirst 5 rows:")
    print(prices.head())