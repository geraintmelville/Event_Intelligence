# UK Event Intelligence

Data-backed view of live event density across the UK — by category, geography, and time window — to inform brand campaign sponsorship strategy.

## Project Structure

```
event-intelligence/
├── app.py                      # Main Streamlit dashboard (Event Density Forecast)
├── pages/
│   └── voronoi_dashboard.py    # Second dashboard page (Sponsorship Territory Map)
├── get_data.py                 # Data ingestion pipeline
├── models.py                   # Pydantic validation model (EventRecord)
├── insights.py                 # Helper functions (top 20 cities metric)
├── sunburst.py                 # Sunburst chart (segment → genre → sub_genre)
├── voronoi_dashboard.py        # Voronoi map rendering logic
├── voronoi_utils.py            # Voronoi diagram construction & GeoJSON export
├── territory_breakdown.py      # Territory click → event histogram breakdown
├── uk_boundary.geojson         # UK coastline polygon for Voronoi clipping
├── data/
│   ├── events.csv              # Cleaned event dataset (pipeline output)
│   ├── proximity_df.csv        # Event proximity/clustering data
│   └── choices_df.csv          # Sponsorship choices (set-covering output)
├── .env                        # API_KEY for Ticketmaster Discovery API
└── event-intelligence/         # Python virtual environment
```

## Quick Start

### Run the ingestion pipeline

```bash
python get_data.py
```

Requires a `API_KEY` in `.env` (Ticketmaster Discovery API key).

### Run the dashboard

```bash
streamlit run app.py
```

The dashboard has two pages accessible via the sidebar:
1. **UK Event Density — Yearly Forecast** (main page)
2. **Sponsorship Territory Map** (Voronoi territories)

## Pipeline Overview

`get_data.py` orchestrates the full ingestion in `run_pipeline()`:

```
build_date_windows → fetch_events → flatten_event → get_venue_capacity
→ validate_event → write_csv → clean_events_data → correct_types
→ add_london_borough → clean_auxiliary_csvs
```

### Pipeline Functions

| Function | Purpose |
|----------|---------|
| `build_date_windows` | Splits the next 12 months into monthly windows to stay within the API's 10,000-result cap per query. |
| `fetch_events` | Paginates through a single date window, deduplicates against previously-seen event IDs, handles rate limiting (429) and end-of-results (400). |
| `flatten_event` | Extracts relevant fields from a raw Ticketmaster event object into a flat dictionary. |
| `get_venue_capacity` | Looks up venue capacity from a static table of ~95 major UK arenas, stadiums, and theatres. Returns `None` for unlisted venues. |
| `validate_event` | Validates a flattened event dict against the `EventRecord` Pydantic model. Returns `None` for invalid records. |
| `write_csv` | Writes all collected records to `data/events.csv`. |
| `normalise_city` | Standardises city names — strips whitespace, removes postcodes, applies title-case. |
| `clean_events_data` | Row-level cleaning: removes ticketed attractions, drops out-of-bounds coordinates, removes undefined segments and null times. |
| `correct_types` | Casts columns to appropriate types (datetime, time, int, category). |
| `add_london_borough` | Spatial join against GLA borough boundaries to tag London events with their borough name. |
| `clean_auxiliary_csvs` | Removes excluded attractions from `proximity_df.csv` and `choices_df.csv`. |

### Key Constants

| Constant | Description |
|----------|-------------|
| `VENUE_CAPACITY_TABLE` | Static lookup of ~95 major UK venues and their capacities (arenas, stadiums, West End theatres). |
| `EXCLUDED_VENUES` | Ticketed attractions (museums, theme parks, aquariums) excluded from all datasets. |
| `BOROUGH_GEOJSON_URL` | GeoJSON source for London borough polygons used in the spatial join. |

## Output Schema (`data/events.csv`)

| Column | Type | Description |
|--------|------|-------------|
| `event_id` | str | Ticketmaster event ID |
| `name` | str | Event name |
| `date` | date | Event date (YYYY-MM-DD) |
| `time` | time | Event start time (HH:MM:SS) |
| `multi_day_event` | bool | Whether the event spans multiple days |
| `city` | str | Normalised city name |
| `longitude` | float | Venue longitude |
| `latitude` | float | Venue latitude |
| `venue` | str | Venue name |
| `capacity` | int | Venue capacity (-1 if unknown) |
| `segment` | str | Event segment (Music, Sports, Arts & Theatre, etc.) |
| `genre` | str | Event genre within segment |
| `sub_genre` | str | Event sub-genre within genre |
| `london_borough` | str | London borough name (NaN for non-London events) |

## Dashboard Features

### Page 1: Event Density Forecast (`app.py`)

- **Summary metrics** — total events, London events, unique venues, cities covered
- **Top 20 areas bar chart** — treats London boroughs as individual areas; click a bar to filter the map and show a sunburst breakdown
- **Monthly volume chart** — total events per month; click a bar to filter the map to that month
- **Interactive venue map** — filterable by segment, genre, date range, and city; shows scatter points coloured by segment
- **City drill-down** — when a city is selected, the map zooms in and a sunburst + metrics panel appears alongside showing the segment/genre/sub-genre breakdown
- **Segment filter** — when a segment is applied without a city, a geographic sunburst (city → area) shows where those events concentrate

### Page 2: Sponsorship Territory Map (`pages/voronoi_dashboard.py`)

- **Voronoi territory map** — each event gets a polygon territory clipped to the UK coastline, coloured by segment
- **Sponsorship highlighting** — chosen sponsorships have bold borders; the best pick per city gets a pulsing gold marker
- **Click interaction** — click a territory to see a time-series histogram of the events it covers, stacked by segment
- **Month filter** — switch between months to see how territories shift

## Colour Palette

| Role | Hex | Usage |
|------|-----|-------|
| Primary | `#1A3A8F` | Deep navy — dominant structural colour |
| Secondary | `#6B35C8` | Mid purple — gradient midpoint |
| Accent | `#00B4C8` | Teal/cyan — highlights |
| Dark | `#0D1F5C` | Near-black navy — shadows/depth |
| Light | `#C8B8F0` | Pale lavender — subtle fills |
| Neutral | `#F4F4F6` | Off-white — page background |
