# UK Event Intelligence — Data Ingestion Pipeline

Fetches upcoming UK events from the Ticketmaster Discovery API, enriches them with venue capacity, validates and cleans the data, then writes a final CSV to `data/events.csv`.

## Usage

```bash
python get_data.py
```

Requires an `API_KEY` in `.env` (Ticketmaster Discovery API key).

## Pipeline Overview

`run_pipeline()` orchestrates the following steps in order:

```
build_date_windows → fetch_events → flatten_event → get_venue_capacity → validate_event → write_csv → clean_events_data → correct_types → add_london_borough
```

## Functions

| Function | Purpose |
|----------|---------|
| `build_date_windows` | Splits the next 12 months into bi-monthly windows to stay within the API's 10,000-result cap per query. |
| `fetch_events` | Paginates through a single date window, deduplicates against previously-seen event IDs, handles rate limiting. |
| `flatten_event` | Extracts relevant fields from a raw Ticketmaster event object into a flat dictionary. |
| `get_venue_capacity` | Looks up venue capacity from a static table of major UK arenas, stadiums, and theatres. Results are cached in memory. |
| `validate_event` | Validates a flattened event dict against the `EventRecord` Pydantic model. Returns `None` for invalid records. |
| `write_csv` | Writes all collected records to `data/events.csv`. |
| `normalise_city` | Standardises city names — strips whitespace, removes postcodes, applies title-case. |
| `clean_events_data` | Row-level cleaning: normalises cities, removes attractions/museums, drops out-of-bounds coordinates, removes undefined segments and null times. |
| `correct_types` | Casts columns to appropriate types (datetime, time, int, category). |
| `add_london_borough` | Spatial join against GLA borough boundaries to tag London events with their borough name. |

## Key Constants

| Constant | Description |
|----------|-------------|
| `VENUE_CAPACITY_TABLE` | Static lookup of ~70 major UK venues and their capacities. |
| `EXCLUDED_VENUES` | Ticketed attractions (museums, theme parks) excluded from the dataset. |
| `BOROUGH_GEOJSON_URL` | GeoJSON source for London borough polygons used in the spatial join. |

## Output Schema

The final CSV contains these columns:

`event_id`, `name`, `date`, `time`, `multi_day_event`, `city`, `longitude`, `latitude`, `venue`, `capacity`, `segment`, `genre`, `sub_genre`, `london_borough`
