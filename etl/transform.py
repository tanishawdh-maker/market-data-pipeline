"""Transform: clean raw yfinance data and validate it before loading."""
import pandas as pd

# yfinance column name -> our database column name
COLUMN_MAP = {
    "Open": "open",
    "High": "high",
    "Low": "low",
    "Close": "close",
    "Adj Close": "adj_close",
    "Volume": "volume",
}
PRICE_COLUMNS = ["open", "high", "low", "close", "adj_close"]
REQUIRED_COLUMNS = ["open", "high", "low", "close", "volume"]


def clean_prices(raw, symbol):
    """Reshape raw yfinance data so it matches the daily_prices table."""
    df = raw.reset_index()                                  # move Date out of the index into a normal column
    df = df.rename(columns={"Date": "trade_date", **COLUMN_MAP})
    df = df[["trade_date"] + list(COLUMN_MAP.values())]    # keep only our columns, by name
    df["trade_date"] = df["trade_date"].dt.date            # 2026-09-10 00:00:00-04:00  ->  2026-09-10
    df[PRICE_COLUMNS] = df[PRICE_COLUMNS].round(4)         # match NUMERIC(14,4)
    df.insert(0, "symbol", symbol.upper())                 # add the symbol as the first column
    return df


def validate(df):
    """Split rows into good rows and rejected rows. Returns (good_df, rejected_list)."""
    checks = {
        "missing_values":     df[REQUIRED_COLUMNS].isna().any(axis=1),
        "non_positive_price": (df[PRICE_COLUMNS] <= 0).any(axis=1),
        "high_not_highest":   df["high"] < df[["open", "close", "low"]].max(axis=1),
        "low_not_lowest":     df["low"] > df[["open", "close", "high"]].min(axis=1),
        "negative_volume":    df["volume"] < 0,
        "weekend_date":       pd.to_datetime(df["trade_date"]).dt.dayofweek >= 5,
        "duplicate_date":     df.duplicated(subset=["symbol", "trade_date"], keep="first"),
    }

    rejected = []
    bad_rows = pd.Series(False, index=df.index)

    for check_name, failed in checks.items():
        for _, row in df[failed].iterrows():
            rejected.append({
                "symbol": row["symbol"],
                "trade_date": row["trade_date"],
                "check_name": check_name,
                "raw_record": row.to_dict(),
            })
        bad_rows = bad_rows | failed

    good = df[~bad_rows].copy()
    good["volume"] = good["volume"].astype("int64")          # volumes are whole numbers
    return good, rejected


if __name__ == "__main__":
    from extract import fetch_prices

    raw = fetch_prices("AAPL")
    clean = clean_prices(raw, "AAPL")
    good, rejected = validate(clean)
    print(f"AAPL: {len(good)} good rows, {len(rejected)} rejected")
    print(good.tail())