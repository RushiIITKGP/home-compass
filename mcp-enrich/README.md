# mcp-enrich

Demographics + Crime MCP server — wraps the US Census ACS API and the
FBI Crime Data API, caching results in Postgres. See A-03, A-06, A-08.

Both are niche enough that no pre-built MCP server wraps them (unlike
amenities — see `mcp-amenities/`), so these are hand-written, ~40-line
tools each.

## Tools

- **`get_neighborhood_demographics(zip_code)`** — median household
  income and median age (Census ACS 5-Year estimates)
- **`get_safety_stats(zip_code, state)`** — violent/property crime
  estimates. **Note:** crime is reported by police agency, not ZIP
  code, so this is a statewide estimate used as a practical proxy —
  see the `note` field every result includes.

Both cache in Postgres (`demographics` / `crime_stats`) on first fetch
per ZIP — this data only updates annually, so repeat lookups are a
cache hit, not a fresh API call.

## Setup

Both APIs need a free key:
- Census: https://api.census.gov/data/key_signup.html
- FBI (via api.data.gov): https://api.data.gov/signup

Fill `CENSUS_API_KEY`, `FBI_API_KEY`, and `DATABASE_URL` into the
repo-root `.env` — `server.py` loads it automatically, no `export`
needed:

```
pip install -r requirements.txt -r ../requirements.txt

npx @modelcontextprotocol/inspector python server.py
```

## Running in Docker

```
docker compose up mcp-enrich
```
