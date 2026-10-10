"""Test the transform step with deliberately bad data."""
import pandas as pd

from transform import clean_prices, validate

# A fake DataFrame shaped exactly like yfinance output, with 5 bad rows planted in it.
dates = pd.to_datetime([
    "2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17",
    "2026-09-18", "2026-09-19", "2026-09-21", "2026-09-21",
]).tz_localize("America/New_York")

raw = pd.DataFrame({
    "Open":         [100.0,   101.0, 102.0,  103.0, 104.0, 105.0, 106.0, 106.0],
    "High":         [102.123456, 103.0, 101.0,  105.0, 106.0, 107.0, 108.0, 108.0],
    "Low":          [99.0,    100.0, 101.5,  102.0, 103.0, 104.0, 105.0, 105.0],
    "Close":        [101.0,   102.0, 101.8,  None,  105.0, 106.0, 107.0, 107.0],
    "Adj Close":    [101.0,   102.0, 101.8,  104.0, 105.0, 106.0, 107.0, 107.0],
    "Volume":       [1000,    1100,  1200,   1300,  -50,   1500,  1600,  1600],
    "Dividends":    [0.0] * 8,
    "Stock Splits": [0.0] * 8,
}, index=pd.DatetimeIndex(dates, name="Date"))

# Planted problems:
#   2026-09-16  high (101.0) is below open (102.0)   -> high_not_highest
#   2026-09-17  close is missing                     -> missing_values
#   2026-09-18  volume is negative                   -> negative_volume
#   2026-09-19  is a Saturday                        -> weekend_date
#   2026-09-21  appears twice                        -> duplicate_date

clean = clean_prices(raw, "aapl")
print("Cleaned columns:", list(clean.columns))
print(clean.head(2), "\n")

good, rejected = validate(clean)
print(f"Good rows: {len(good)}   Rejected: {len(rejected)}\n")
for r in rejected:
    print(f"  REJECTED  {r['trade_date']}  {r['check_name']}")

print("\nGood rows that would be loaded:")
print(good)