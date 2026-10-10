# Market Data Pipeline

A daily market data pipeline: Python and Airflow ingest stock prices, validate them, store them in PostgreSQL, compute trading metrics with SQL, and serve everything through a FastAPI REST API, all running in Docker.

## Status

- [x] **Phase 1: Database design** (`sql/`)
- [x] Phase 2: Python ETL (extract → validate → load → metrics)
- [ ] Phase 3: Airflow orchestration
- [ ] Phase 4: FastAPI REST API
- [ ] Phase 5: Docker Compose, tests, polish

## Database schema

| Table | Purpose |
|---|---|
| `tickers` | The 20 stocks being tracked |
| `daily_prices` | One open/high/low/close/volume bar per stock per trading day |
| `daily_metrics` | Daily return, 20-day moving average, and 20-day volatility, computed from `daily_prices` |
| `pipeline_runs` | One row per pipeline run, for auditing |
| `data_quality_log` | Every rejected record, with the reason it was rejected |

Key design choices:
- **Composite primary key `(symbol, trade_date)`** makes duplicate bars impossible and makes loads idempotent through `INSERT ... ON CONFLICT DO UPDATE`.
- **CHECK constraints** (positive prices, `high` is the day's highest value, non-negative volume, weekdays only) reject bad data at the database level, as a second line of defense behind the Python validation.
- **`NUMERIC` instead of `FLOAT`** keeps prices exact.
- **Raw and derived data live in separate tables**, so metrics can be recomputed without re-downloading anything.
- **Rejected records are logged, never silently dropped.**

## Run Phase 1 (Linux / WSL2 terminal)

```bash
# 1. Start PostgreSQL 16 in Docker
docker run -d --name market-pg \
  -e POSTGRES_PASSWORD=dev \
  -p 5432:5432 \
  postgres:16

# 2. Create the schema and seed the tickers
docker exec -i market-pg psql -U postgres < sql/001_schema.sql
docker exec -i market-pg psql -U postgres < sql/002_seed_tickers.sql

# 3. Run the schema tests (all lines should start with PASS)
docker exec -i market-pg psql -U postgres < sql/003_test_schema.sql

# 4. Look around
docker exec -it market-pg psql -U postgres
#   \dt                 list tables
#   \d daily_prices     show columns and constraints
#   \q                  quit
```

The test script runs inside a transaction and rolls back at the end, so it leaves no test data behind.
