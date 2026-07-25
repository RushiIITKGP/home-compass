# mcp-market

Market Data MCP server — serves Realtor.com Data Library and Redfin
Data Center stats, batch-ingested into `market_stats`. See A-06, A-08.

Two pieces:
- **`ingest_market_data.py`** — batch ETL, run whenever you download a
  fresh file (weekly/monthly per A-06's update-cadence notes; the
  recurring cron job for this is Phase 7)
- **`server.py`** — the MCP server, exposing `get_market_trends`,
  which only reads what's already been ingested

## Ingest data

Download a file, then load it — `DATABASE_URL` comes from the
repo-root `.env` automatically, no `export` needed:

```
pip install -r requirements.txt -r ../requirements.txt

python ingest_market_data.py --source redfin --file data/zip_code_market_tracker.tsv000.gz
python ingest_market_data.py --source realtor --file data/RDC_Inventory_Core_Metrics_Zip_History.csv
```

- Redfin: https://www.redfin.com/news/data-center — "Zip Code" market tracker
- Realtor.com: https://www.realtor.com/research/data/ — "Zip Code" inventory history

Both sources have changed their exact column names before — if a file
fails to parse, check its header row against `COLUMN`-mapping logic at
the top of `ingest_market_data.py` and adjust, same pattern as
`ingest-worker/seed_kaggle.py` uses for the Kaggle dataset.

## Serve it

```
npx @modelcontextprotocol/inspector python server.py
```

Call `get_market_trends` with a ZIP you just ingested data for.

## Running in Docker

```
docker compose up mcp-market
```
