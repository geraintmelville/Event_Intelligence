"""
UK Events Ingestion Pipeline
=============================
Fetches upcoming UK events from the Ticketmaster Discovery API, enriches
each with venue capacity from a static lookup table, validates records with
Pydantic, and writes a clean CSV to data/events.csv.

Usage
-----
    python ingest.py               # full run with capacity lookups
    python ingest.py --no-capacity # skip capacity lookups
"""

import csv
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv
from pydantic import ValidationError
from shapely.geometry import Point

from models import EventRecord

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_KEY  = os.getenv('API_KEY')
BASE_URL = 'https://app.ticketmaster.com/discovery/v2/events.json'

PAGE_SIZE     = 200   # Ticketmaster max per page
MAX_PAGES     = 10    # per date window (200 × 10 = 2,000 events per window)
REQUEST_DELAY = 0.25  # seconds between Ticketmaster page requests

DATA_DIR    = Path('data')
OUTPUT_FILE = DATA_DIR / 'events.csv'

CSV_COLUMNS = [
    'event_id', 'name', 'date', 'time', 'multi_day_event',
    'city', 'longitude', 'latitude',
    'venue', 'capacity',
    'segment', 'genre', 'sub_genre',
]

# ---------------------------------------------------------------------------
# Static venue capacity lookup table
#
# Covers the highest-volume UK venues across arenas, stadiums, and theatres.
#
# Sources:
#   - Arenas:   Wikipedia "List of indoor arenas in the United Kingdom"
#               https://en.wikipedia.org/wiki/List_of_indoor_arenas_in_the_United_Kingdom
#   - Stadiums: Wikipedia "List of stadiums in the United Kingdom by capacity"
#               https://en.wikipedia.org/wiki/List_of_stadiums_in_the_United_Kingdom_by_capacity
#   - Theatres: seatplan.com individual venue pages; official venue websites
#               https://seatplan.com/london/
# ---------------------------------------------------------------------------

VENUE_CAPACITY_TABLE: dict[str, int] = {
    # --- Major indoor arenas ---
    "Co-op Live":                        23500,  # Manchester, opened 2024
    "AO Arena":                          23000,  # Manchester (formerly Manchester Arena)
    "The O2":                            20000,  # London
    "Utilita Arena Birmingham":          15800,  # Birmingham (formerly Arena Birmingham)
    "bp pulse LIVE":                     15685,  # Birmingham (formerly Genting Arena / NEC Arena)
    "OVO Hydro":                         14300,  # Glasgow
    "first direct arena":                13500,  # Leeds
    "Sheffield Arena":                   13600,  # Sheffield (Utilita Arena Sheffield)
    "Utilita Arena Sheffield":           13600,
    "OVO Arena Wembley":                 12500,  # London (formerly SSE Arena Wembley / Wembley Arena)
    "SSE Arena":                         11200,  # Belfast
    "Utilita Arena Newcastle":           11400,  # Newcastle (formerly Metro Radio Arena)
    "Coventry Building Society Arena":   10000,  # Coventry
    "Nottingham Arena":                  10000,  # Nottingham (Motorpoint Arena Nottingham)
    "Motorpoint Arena Nottingham":       10000,
    "P&J Live":                          15000,  # Aberdeen (upper end of 10k–15k range)
    "M&S Bank Arena Liverpool":          11000,  # Liverpool (formerly Echo Arena)
    "Utilita Arena Cardiff":              7500,  # Cardiff (formerly Motorpoint Arena Cardiff)
    "Motorpoint Arena Cardiff":           7500,
    "Bournemouth International Centre":   6500,
    "Brighton Centre":                    5000,
    "Arena MK":                           5000,  # Milton Keynes

    # --- Major outdoor stadiums ---
    "Wembley Stadium":                   90000,
    "Twickenham Stadium":                82000,
    "Allianz Stadium, Twickenham":       82000,  # sponsorship rename
    "Old Trafford":                      74197,  # Manchester United
    "Principality Stadium":              73931,  # Cardiff
    "Murrayfield Stadium":               67144,  # Edinburgh
    "Tottenham Hotspur Stadium":         62850,
    "London Stadium":                    62500,  # West Ham / Olympic Stadium
    "Etihad Stadium":                    61470,  # Manchester City
    "Anfield":                           61276,  # Liverpool
    "Emirates Stadium":                  60704,  # Arsenal
    "Celtic Park":                       60411,  # Glasgow
    "Hampden Park":                      51866,  # Glasgow
    "St James' Park":                    52305,  # Newcastle
    "Villa Park":                        42656,  # Aston Villa
    "Ibrox Stadium":                     50817,  # Rangers
    "Stamford Bridge":                   40341,  # Chelsea
    "Elland Road":                       37890,  # Leeds United
    "Goodison Park":                     39572,  # Everton (to 2025)
    "Selhurst Park":                     25486,  # Crystal Palace
    "Bramall Lane":                      32702,  # Sheffield United
    "Cardiff City Stadium":              33280,  # Cardiff City

    # --- London West End theatres ---
    "London Palladium":                   2325,
    "Apollo Victoria Theatre":            2328,
    "Dominion Theatre":                   2083,
    "Lyceum Theatre":                     2100,
    "Theatre Royal Drury Lane":           2220,
    "Eventim Apollo":                     3500,  # Hammersmith Apollo
    "London Coliseum":                    2358,
    "Royal Albert Hall":                  5272,
    "Barbican Theatre":                   1166,
    "Gillian Lynne Theatre":              1295,
    "Cambridge Theatre":                  1227,
    "His Majesty's Theatre":              1216,
    "Prince of Wales Theatre":            1160,
    "Palace Theatre":                     1743,
    "Playhouse Theatre":                   865,
    "Ambassadors Theatre":                 444,
    "Charing Cross Theatre":               265,
    "The Old Vic":                        1067,
    "Gielgud Theatre":                     986,
    "Wyndham's Theatre":                   759,
    "Noel Coward Theatre":                 942,

    # --- Additional theatres & music venues (found via CSV audit) ---
    "Vaudeville Theatre":                  690,
    "The Theatre at the Hippodrome Casino": 180,
    "Duchess Theatre":                     494,
    "Lyric Theatre":                       967,
    "Savoy Theatre":                      1158,
    "Adelphi Theatre":                    1500,
    "Aldwych Theatre":                    1200,
    "Prince Edward Theatre":              1618,
    "Duke of Yorks Theatre":               640,
    "ABBA Arena":                         3000,
    "Sondheim Theatre":                   1075,
    "Novello Theatre":                    1146,
    "Victoria Palace Theatre":            1550,
    "Garrick Theatre":                     718,
    "Apollo Theatre":                      775,
    "Theatre Royal Haymarket":             888,
    "Jazz Cafe":                           440,
    "Liverpool Empire Theatre":           2350,
    "The Harold Pinter Theatre":           895,
    "Bridge Theatre":                      900,
    "York Barbican":                      1500,
    "NEC":                               15685,  # same complex as bp pulse LIVE
    "Sheffield City Hall Oval Hall":       850
}

# Persists for the duration of the pipeline run so each unique venue
# is only looked up once, regardless of how many events are held there.
_capacity_cache: dict[str, int | None] = {}

# ---------------------------------------------------------------------------
# fetch_events
# ---------------------------------------------------------------------------

def build_date_windows(months: int = 12, window_months: int = 2) -> list[tuple[str, str]]:
    """
    Split the next `months` months into windows of `window_months` each.
    Returns (startDateTime, endDateTime) pairs in Ticketmaster's ISO 8601 format.

    A single countryCode=GB query is capped at 10,000 results. Splitting into
    bi-monthly windows gives up to 6 × 10,000 = 60,000 slots before deduplicating,
    which is more than enough to collect ~20,000 unique events.
    """
    now     = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    end_all = now + timedelta(days=30 * months)
    windows = []

    cursor = now
    while cursor < end_all:
        window_end = min(cursor + timedelta(days=30 * window_months), end_all)
        windows.append((
            cursor.strftime('%Y-%m-%dT%H:%M:%SZ'),
            window_end.strftime('%Y-%m-%dT%H:%M:%SZ'),
        ))
        cursor = window_end

    return windows


def fetch_events(
    session: requests.Session,
    start_dt: str,
    end_dt: str,
    seen_ids: set[str],
) -> list[dict]:
    """
    Fetch all available GB events within a single date window, paginating
    until the API has no more pages or MAX_PAGES is reached.

    Already-seen event IDs are filtered out before returning so the caller
    always receives only new events. seen_ids is mutated in place so
    cross-window deduplication is automatic.

    Args:
        session:   Shared requests.Session from run_pipeline().
        start_dt:  Window start in ISO 8601 format, e.g. "2026-07-08T00:00:00Z"
        end_dt:    Window end in ISO 8601 format.
        seen_ids:  Set of event IDs already collected — mutated in place.

    Returns:
        List of raw event dicts (full Ticketmaster event objects).
    """
    new_events: list[dict] = []

    for page in range(MAX_PAGES):
        params = {
            'apikey':        API_KEY,
            'countryCode':   'GB',
            'startDateTime': start_dt,
            'endDateTime':   end_dt,
            'size':          PAGE_SIZE,
            'page':          page,
            'sort':          'date,asc',
        }

        try:
            response = session.get(BASE_URL, params=params, timeout=15)

            # Ticketmaster returns 429 when rate-limited — back off and retry once
            if response.status_code == 429:
                print(f'  Rate limited on page {page} — waiting 30s')
                time.sleep(30)
                response = session.get(BASE_URL, params=params, timeout=15)

            response.raise_for_status()
            data = response.json()

        except requests.exceptions.HTTPError as err:
            # 400 on a page > 0 typically means we've gone past available results
            if response.status_code == 400 and page > 0:
                print(f'  No more pages available (stopped at page {page})')
            else:
                print(f'  HTTP error on page {page}: {err}')
            break
        except requests.exceptions.RequestException as err:
            print(f'  Request error on page {page}: {err}')
            break

        page_info   = data.get('page', {})
        total_pages = page_info.get('totalPages', 0)
        events      = data.get('_embedded', {}).get('events', [])

        if not events:
            break

        # Filter to events we haven't seen yet, then register them
        for event in events:
            event_id = event.get('id')
            if event_id and event_id not in seen_ids:
                seen_ids.add(event_id)
                new_events.append(event)

        print(
            f'  [{start_dt[:10]} to {end_dt[:10]}] '
            f'page {page + 1}/{total_pages} — '
            f'+{len(events)} fetched, {len(new_events)} new so far'
        )

        # Stop if we've exhausted all pages for this window
        if page + 1 >= total_pages:
            break

        time.sleep(REQUEST_DELAY)

    return new_events

# ---------------------------------------------------------------------------
# flatten_event
# ---------------------------------------------------------------------------

def flatten_event(raw: dict) -> dict:
    """
    Extract the fields we care about from a raw Ticketmaster event dict
    and return them as a flat dictionary ready for validation.

    All values are kept as their native types (strings, bools) — type
    coercion is handled downstream by the Pydantic model.

    Args:
        raw: A single event object from the Ticketmaster API response,
             i.e. one item from data['_embedded']['events'].

    Returns:
        Flat dict with the fields defined in the output schema.
    """
    classifications = raw.get('classifications', [{}])[0]
    venues          = raw.get('_embedded', {}).get('venues', [{}])
    venue           = venues[0] if venues else {}
    location        = venue.get('location', {})
    start           = raw.get('dates', {}).get('start', {})

    return {
        'event_id':        raw.get('id'),
        'name':            raw.get('name'),
        'date':            start.get('localDate'),
        'time':            start.get('localTime') if not start.get('timeTBA') else None,
        'multi_day_event': raw.get('dates', {}).get('spanMultipleDays'),
        'city':            venue.get('city', {}).get('name'),
        'longitude':       location.get('longitude'),
        'latitude':        location.get('latitude'),
        'venue':           venue.get('name'),
        'capacity':        None,  # filled in by get_venue_capacity()
        'segment':         classifications.get('segment', {}).get('name'),
        'genre':           classifications.get('genre', {}).get('name'),
        'sub_genre':       classifications.get('subGenre', {}).get('name'),
    }

# ---------------------------------------------------------------------------
# get_venue_capacity
# ---------------------------------------------------------------------------

def get_venue_capacity(venue_name: str) -> int | None:
    """
    Look up venue capacity from the static VENUE_CAPACITY_TABLE.

    Results are cached in memory so repeated calls for the same venue name
    return immediately. Venues not in the table return None.

    Args:
        venue_name: Venue name string from the Ticketmaster response,
                    e.g. "AO Arena".

    Returns:
        Integer capacity if found in the table, None otherwise.
    """
    if venue_name in _capacity_cache:
        return _capacity_cache[venue_name]

    capacity = VENUE_CAPACITY_TABLE.get(venue_name)
    _capacity_cache[venue_name] = capacity
    return capacity

# ---------------------------------------------------------------------------
# validate_event
# ---------------------------------------------------------------------------

def validate_event(flat: dict) -> EventRecord | None:
    """
    Validate a flattened event dict against the EventRecord Pydantic model.

    Type coercion (string → date, string → float, etc.) is handled by the
    model itself. This function just attempts construction and returns None
    if validation fails, so the caller can skip bad records without crashing.

    Args:
        flat: A flat event dict as returned by flatten_event().

    Returns:
        A validated EventRecord instance, or None if validation fails.
    """
    try:
        return EventRecord(**flat)
    except ValidationError as e:
        print(f'  Validation failed for event "{flat.get("event_id")}": {e.error_count()} error(s)')
        return None

# ---------------------------------------------------------------------------
# run_pipeline
# ---------------------------------------------------------------------------

def write_csv(records: list[dict]) -> None:
    """Write all collected records to the output CSV."""
    DATA_DIR.mkdir(exist_ok=True)
    with OUTPUT_FILE.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(records)
    print(f'Wrote {len(records)} records to {OUTPUT_FILE}')


# ---------------------------------------------------------------------------
# clean_events_data
# ---------------------------------------------------------------------------

# Ticketed attractions / museums / theme parks — not live performance events.
# These inflate event counts due to time-slotted ticketing and are not relevant
# for brand campaign sponsorship around live events.
EXCLUDED_VENUES: set[str] = {
    "Twist Museum",
    "Marble Arch Place",
    "Neon at Battersea Power Station",
    "County Hall",
    "The London Eye",
    "The London Dungeon",
    "Chessington World of Adventures",
    "Thorpe Park",
    "Alton Towers",
    "Legoland Windsor",
    "Warwick Castle",
    "Sandcastle Waterpark",
    "Madame Tussauds London",
    "Madame Tussauds Blackpool",
    "SEA LIFE Brighton",
    "SEA LIFE Blackpool",
    "SEA LIFE Manchester",
    "National SEA LIFE Centre Birmingham",
    "Empress Museum",
    "The Arts at Marble Arch",
}


def normalise_city(city: str) -> str:
    """
    Standardise a city name returned by the Ticketmaster API.

    Handles:
      - Leading/trailing whitespace
      - Postcodes appended after a comma (e.g. "Newcastle upon Tyne, NE1 2PQ")
      - Inconsistent title-casing (e.g. "Upon" vs "upon")

    Args:
        city: Raw city name string.

    Returns:
        Cleaned, title-cased city name.
    """
    if not isinstance(city, str):
        return city
    # Strip whitespace and remove anything after a comma (postcodes)
    city = city.strip()
    if ',' in city:
        city = city.split(',')[0].strip()
    # Apply consistent title case
    return city.title()


def clean_events_data(data: pd.DataFrame) -> pd.DataFrame:
    """
    Apply row-level cleaning to the raw events DataFrame:
      - Normalise city names (strip whitespace, remove postcodes, title-case)
      - Remove ticketed attractions/museums/theme parks (not live events)
      - Drop events with longitude > 2 or latitude < 50 (non-UK coordinates)
      - Replace 'Undefined' segment values with NaN, then drop those rows
      - Drop rows with a null time
      - Fill null capacity with -1 (sentinel for "unknown")

    Args:
        data: Raw events DataFrame as read from the CSV.

    Returns:
        Cleaned DataFrame with invalid rows removed.
    """
    clean = data.copy()

    # Normalise city names (whitespace, postcodes, casing)
    clean['city'] = clean['city'].apply(normalise_city)

    # Remove ticketed attractions
    clean = clean[~clean['venue'].isin(EXCLUDED_VENUES)]

    # Identify rows with coordinates outside the UK bounding box
    bad_coords = clean[clean['longitude'] > 2].index
    bad_coords = bad_coords.union(clean[clean['latitude'] < 50].index)

    clean['segment'] = clean['segment'].replace('Undefined', np.nan)
    clean = clean.drop(index=bad_coords)
    clean = clean.dropna(subset=['segment'])
    clean = clean.dropna(subset=['time'])
    clean['capacity'] = clean['capacity'].fillna(-1)

    return clean


# ---------------------------------------------------------------------------
# correct_types
# ---------------------------------------------------------------------------

def correct_types(data: pd.DataFrame) -> pd.DataFrame:
    """
    Cast DataFrame columns to their appropriate types:
      - date    → datetime64
      - time    → datetime.time
      - capacity → int
      - segment, genre, sub_genre → category

    Args:
        data: Cleaned events DataFrame.

    Returns:
        DataFrame with corrected column types.
    """
    out = data.copy()
    out['date']      = pd.to_datetime(out['date'])
    out['time']      = pd.to_datetime(out['time'], format='%H:%M:%S').dt.time
    out['capacity']  = out['capacity'].astype(int)
    out['segment']   = out['segment'].astype('category')
    out['genre']     = out['genre'].astype('category')
    out['sub_genre'] = out['sub_genre'].astype('category')
    return out


# ---------------------------------------------------------------------------
# add_london_borough
# ---------------------------------------------------------------------------

BOROUGH_GEOJSON_URL = (
    "https://raw.githubusercontent.com/radoi90/housequest-data/master/london_boroughs.geojson"
)


def add_london_borough(data: pd.DataFrame) -> pd.DataFrame:
    """
    Adds a 'london_borough' column to the events DataFrame.

    For events whose city is 'London', a spatial join against the GLA borough
    boundaries is used to identify the specific borough based on the event's
    longitude/latitude. Events that fall outside all borough polygons (e.g. on
    the GLA boundary) are dropped and a count is printed.

    For all non-London events the column value is 'N/A'.

    Args:
        data: Cleaned, type-corrected events DataFrame containing 'city',
              'longitude', and 'latitude' columns.

    Returns:
        DataFrame with a new 'london_borough' column.
    """
    out = data.copy()
    out['london_borough'] = 'N/A'

    is_london = out['city'].str.strip().str.lower() == 'london'

    if not is_london.any():
        return out

    # Load borough boundaries (WGS84)
    boroughs = gpd.read_file(BOROUGH_GEOJSON_URL)[['name', 'geometry']].rename(
        columns={'name': 'borough'}
    )

    # Build a GeoDataFrame from the London subset only
    london = out[is_london].copy()
    london_gdf = gpd.GeoDataFrame(
        london,
        geometry=[Point(xy) for xy in zip(london['longitude'], london['latitude'])],
        crs='EPSG:4326',
    )

    # Spatial join: attach borough to each London event
    joined = gpd.sjoin(london_gdf, boroughs, how='left', predicate='within')
    joined = joined.drop(columns='index_right')

    # Report and drop London events that didn't fall within any borough polygon
    unmatched = joined[joined['borough'].isna()]
    if not unmatched.empty:
        print(
            f'{len(unmatched)} London event(s) did not match a borough '
            f'and were dropped'
        )
        joined = joined.drop(index=unmatched.index)

    # Write borough names back into the main DataFrame
    out = out.drop(index=unmatched.index)
    out.loc[joined.index, 'london_borough'] = joined['borough']

    return out


def run_pipeline(fetch_capacity: bool = True) -> None:
    """
    Orchestrate the full ingestion pipeline:
      1. Build date windows across the next 12 months
      2. For each window, fetch events and filter out already-seen IDs
      3. Flatten, enrich with venue capacity, and validate each event
      4. Write the final CSV once all windows are processed

    Args:
        fetch_capacity: Set to False to skip capacity lookups.
    """
    DATA_DIR.mkdir(exist_ok=True)

    session           = requests.Session()
    seen_ids:  set[str]   = set()
    collected: list[dict] = []
    validation_errors = 0

    windows = build_date_windows(months=12, window_months=2)

    for idx, (start_dt, end_dt) in enumerate(windows, 1):
        print(f'\nWindow {idx}/{len(windows)}: {start_dt[:10]} to {end_dt[:10]} '
              f'(collected so far: {len(collected)})')

        raw_events = fetch_events(session, start_dt, end_dt, seen_ids)

        for raw in raw_events:
            flat = flatten_event(raw)

            if fetch_capacity and flat.get('venue'):
                flat['capacity'] = get_venue_capacity(flat['venue'])

            record = validate_event(flat)

            if record is None:
                validation_errors += 1
                continue

            collected.append(record.model_dump())

        print(f'Window {idx} done | total collected: {len(collected)}')

    print(f'\nPipeline complete | valid: {len(collected)} | '
          f'validation errors: {validation_errors}')

    write_csv(collected)

    # Load the raw CSV, clean it, correct types, and overwrite
    events = pd.read_csv(OUTPUT_FILE)
    events = clean_events_data(events)
    events = correct_types(events)
    events = add_london_borough(events)
    events.to_csv(OUTPUT_FILE, index=False)
    print(f'Cleaned dataset: {len(events)} records written to {OUTPUT_FILE}')


# -----------------------------------------------------------------------------------
# CLI Entry point
#
#   python ingest.py                  full run with capacity lookups
#   python ingest.py --no-capacity    full run, skip capacity lookups
# -----------------------------------------------------------------------------------

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='UK Events Ingestion Pipeline')
    parser.add_argument(
        '--no-capacity',
        action='store_true',
        help='Skip Wikidata capacity lookups (faster test run)',
    )
    args = parser.parse_args()

    run_pipeline(fetch_capacity=not args.no_capacity)
