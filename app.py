"""
UK Event Intelligence Dashboard
================================
Streamlit dashboard for Cipher & Co — maps event density across the UK
by category, geography, and time window to inform brand campaign strategy.

Run with:  streamlit run app.py
"""

import streamlit as st
import plotly.express as px
import pandas as pd
import numpy as np

from insights import create_top_20_cities
from sunburst import plot_sunburst

# ---------------------------------------------------------------------------
# Palette (from brief)
# ---------------------------------------------------------------------------
# Primary   #1A3A8F  Deep navy blue — dominant structural colour
# Secondary #6B35C8  Mid purple — gradient midpoint
# Accent    #00B4C8  Teal/cyan — highlight
# Dark      #0D1F5C  Near-black navy — shadows/depth
# Light     #C8B8F0  Pale lavender — subtle fills
# Neutral   #F4F4F6  Off-white — background

PRIMARY   = '#1A3A8F'
SECONDARY = '#6B35C8'
ACCENT    = '#00B4C8'
DARK      = '#0D1F5C'
LIGHT     = '#C8B8F0'
NEUTRAL   = '#F4F4F6'

PALETTE = [PRIMARY, SECONDARY, ACCENT, DARK, LIGHT]

# Explicit segment → colour mapping (keeps map and sunburst in sync)
SEGMENT_COLOUR_MAP = {
    'Music':          PRIMARY,
    'Sports':         SECONDARY,
    'Arts & Theatre': ACCENT,
    'Film':           DARK,
    'Miscellaneous':  LIGHT,
}

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title='UK Event Intelligence',
    page_icon='📊',
    layout='wide',
)

# ---------------------------------------------------------------------------
# Custom theme (CSS) — apply palette colours to Streamlit UI
# ---------------------------------------------------------------------------
st.markdown(f"""
<style>
    /* --- Page background --- */
    .stApp {{
        background-color: {NEUTRAL};
    }}

    /* --- Sidebar --- */
    [data-testid="stSidebar"] {{
        background-color: {DARK};
    }}
    [data-testid="stSidebar"] * {{
        color: {NEUTRAL} !important;
    }}

    /* --- Headers --- */
    h1 {{
        color: {PRIMARY} !important;
    }}
    h2, h3, [data-testid="stSubheader"] {{
        color: {DARK} !important;
    }}

    /* --- Metric cards --- */
    [data-testid="stMetric"] {{
        background-color: white;
        border: 1px solid {LIGHT};
        border-radius: 8px;
        padding: 12px 16px;
        box-shadow: 0 1px 4px rgba(13, 31, 92, 0.08);
    }}
    [data-testid="stMetricLabel"] {{
        color: {SECONDARY} !important;
        font-weight: 600;
    }}
    [data-testid="stMetricValue"] {{
        color: {PRIMARY} !important;
        font-weight: 700;
    }}
    [data-testid="stMetricDelta"] {{
        color: {ACCENT} !important;
    }}

    /* --- Buttons --- */
    .stButton > button {{
        background-color: {PRIMARY};
        color: white;
        border: none;
        border-radius: 6px;
        font-weight: 600;
        transition: background-color 0.2s;
    }}
    .stButton > button:hover {{
        background-color: {SECONDARY};
        color: white;
    }}

    /* --- Selectboxes & inputs --- */
    [data-testid="stSelectbox"] label,
    [data-testid="stDateInput"] label {{
        color: {DARK} !important;
        font-weight: 600;
    }}
    .stSelectbox > div > div {{
        border-color: {LIGHT};
        border-radius: 6px;
    }}

    /* --- Dividers --- */
    hr {{
        border-color: {LIGHT} !important;
    }}

    /* --- Captions --- */
    .stCaption, [data-testid="stCaption"] {{
        color: {SECONDARY} !important;
    }}

    /* --- Tabs (if used) --- */
    .stTabs [data-baseweb="tab"] {{
        color: {DARK};
        font-weight: 600;
    }}
    .stTabs [aria-selected="true"] {{
        color: {PRIMARY} !important;
        border-bottom-color: {ACCENT} !important;
    }}

    /* --- Warning / info boxes --- */
    [data-testid="stAlert"] {{
        border-left-color: {ACCENT};
        background-color: white;
    }}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Load & prepare data
# ---------------------------------------------------------------------------

@st.cache_data
def load_data() -> pd.DataFrame:
    df = pd.read_csv('data/events.csv')
    df['date'] = pd.to_datetime(df['date'])
    # Normalise city names (strip whitespace, remove postcodes, title-case)
    df['city'] = df['city'].apply(
        lambda c: c.strip().split(',')[0].strip().title()
        if isinstance(c, str) else c
    )
    # Derive 'area' column expected by sunburst.py
    is_london = df['city'].str.strip().str.lower() == 'london'
    df['area'] = df['city']
    df.loc[is_london, 'area'] = df.loc[is_london, 'london_borough']
    # Derive major_venue flag (capacity > 0 means it was in our lookup table)
    df['major_venue'] = df['capacity'] > 0
    return df


event_data = load_data()

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
col1, col2 = st.columns([1, 8])
with col1:
    st.image('images/eventintelligence-logo.png', width=90)
with col2:
    st.title('UK Event Density — Yearly Forecast')
    st.caption('Data-backed view of live event activity across the UK calendar')

st.divider()

# ===========================================================================
# SECTION 1: Summary Metrics
# ===========================================================================

st.subheader('Dataset Overview')

london_events, non_london_events, _ = create_top_20_cities(event_data)
total_events  = len(event_data)
total_venues  = event_data['venue'].nunique()
total_cities  = event_data['city'].nunique()
london_pct    = round((london_events / total_events) * 100)

ov_col1, ov_col2, ov_col3, ov_col4 = st.columns(4)
with ov_col1:
    st.metric('Total Events', f'{total_events:,}')
with ov_col2:
    st.metric('London Events', f'{london_events:,}', f'{london_pct}% of total', delta_arrow='off')
with ov_col3:
    st.metric('Unique Venues', f'{total_venues:,}')
with ov_col4:
    st.metric('Cities Covered', f'{total_cities:,}')
    
st.write('---')

# ===========================================================================
# SECTION 2: Top 20 Areas + Monthly Volume (side by side)
# ===========================================================================

sec2_col1, sec2_col2 = st.columns(2)

with sec2_col1:
    st.subheader('Top 20 Areas by Event Frequency')
    st.caption('Treats London boroughs as individual areas. Click a bar to filter the map below.')

    # Build top 20 using the 'area' column (boroughs treated as separate areas)
    all_boroughs_set = set(
        event_data[event_data['city'].str.strip().str.lower() == 'london']['london_borough']
        .dropna().unique()
    )
    area_counts = (
        event_data.groupby('area')['event_id']
        .count()
        .sort_values(ascending=False)
        .head(20)
        .reset_index()
        .rename(columns={'event_id': 'nb_events'})
    )
    # Label boroughs as "London (borough_name)" for display
    area_counts['label'] = area_counts['area'].apply(
        lambda a: f'London ({a})' if a in all_boroughs_set else a
    )

    fig_bar = px.bar(
        area_counts,
        x='nb_events',
        y='label',
        orientation='h',
        color_discrete_sequence=[PRIMARY],
        labels={'nb_events': 'Number of Events', 'label': ''},
        custom_data=['area'],  # keep raw area name for click extraction
    )
    fig_bar.update_layout(
        plot_bgcolor=NEUTRAL,
        paper_bgcolor=NEUTRAL,
        yaxis=dict(categoryorder='total ascending'),
        margin=dict(l=10, r=10, t=10, b=10),
        height=500,
    )

    # Capture bar click events
    bar_selection = st.plotly_chart(
        fig_bar,
        use_container_width=True,
        on_select='rerun',
        key='top20_bar',
    )

    # Extract clicked area from selection (use customdata for raw area name)
    bar_clicked_area = None
    if bar_selection and bar_selection.selection and bar_selection.selection.points:
        point = bar_selection.selection.points[0]
        # customdata[0] holds the original area name
        bar_clicked_area = point.get('customdata', [None])[0] or point.get('y')

with sec2_col2:
    st.subheader('When Does Event Activity Peak?')
    st.caption('Total monthly event volume. Click a bar to filter the map below by month.')
    monthly = event_data.copy()
    monthly['month'] = monthly['date'].dt.to_period('M').astype(str)

    # Total events per month (single bar per month — entire bar is clickable)
    monthly_totals = (
        monthly.groupby('month')
        .size()
        .reset_index(name='events')
    )
    fig_monthly = px.bar(
        monthly_totals,
        x='month',
        y='events',
        color_discrete_sequence=[SECONDARY],
        labels={'month': '', 'events': 'Events'},
    )
    fig_monthly.update_layout(
        plot_bgcolor=NEUTRAL,
        paper_bgcolor=NEUTRAL,
        margin=dict(l=10, r=10, t=10, b=10),
        height=500,
        xaxis_tickangle=-45,
    )

    # Capture month bar click events
    month_selection = st.plotly_chart(
        fig_monthly,
        use_container_width=True,
        on_select='rerun',
        key='monthly_bar',
    )

    # Extract clicked month from selection
    month_clicked = None
    if month_selection and month_selection.selection and month_selection.selection.points:
        month_clicked = month_selection.selection.points[0].get('x')

st.divider()

# ===========================================================================
# SECTION 3: Filtered Map + City Drill-Down
# ===========================================================================

st.subheader('Event Venue Map')
st.caption('Filter by segment, genre, time period, and/or city to explore event distribution. '
           'You can also click a bar in the charts above.')

# --- Sync bar clicks into session state for filter defaults ---
if bar_clicked_area:
    all_boroughs = set(
        event_data[event_data['city'].str.strip().str.lower() == 'london']['london_borough']
        .dropna().unique()
    )
    if bar_clicked_area in all_boroughs:
        st.session_state['filter_city'] = 'London'
        st.session_state['filter_borough'] = bar_clicked_area
    else:
        st.session_state['filter_city'] = bar_clicked_area
        st.session_state['filter_borough'] = 'All'
    st.session_state['filter_month'] = None
else:
    # Bar deselected — revert city/borough to defaults
    st.session_state['filter_city'] = 'All'
    st.session_state['filter_borough'] = 'All'

if month_clicked:
    month_period = pd.Period(month_clicked, freq='M')
    st.session_state['filter_date_start'] = month_period.start_time.date()
    st.session_state['filter_date_end'] = month_period.end_time.date()
    st.session_state['filter_month'] = month_clicked
else:
    # Month bar deselected — revert date range to full extent
    st.session_state['filter_date_start'] = event_data['date'].min().date()
    st.session_state['filter_date_end'] = event_data['date'].max().date()
    st.session_state['filter_month'] = None

# --- Initialise session state defaults ---
if 'filter_city' not in st.session_state:
    st.session_state['filter_city'] = 'All'
if 'filter_borough' not in st.session_state:
    st.session_state['filter_borough'] = 'All'
if 'filter_month' not in st.session_state:
    st.session_state['filter_month'] = None

# --- Filter widgets (reflect session state) ---
filter_col1, filter_col2, filter_col3, filter_col4 = st.columns(4)

with filter_col1:
    segments = sorted(event_data['segment'].dropna().unique())
    selected_segment = st.selectbox('Segment', ['All'] + segments)

with filter_col2:
    if selected_segment != 'All':
        genres = sorted(
            event_data[event_data['segment'] == selected_segment]['genre']
            .dropna().unique()
        )
    else:
        genres = sorted(event_data['genre'].dropna().unique())
    selected_genre = st.selectbox('Genre', ['All'] + genres)

with filter_col3:
    min_date = event_data['date'].min().date()
    max_date = event_data['date'].max().date()
    # Use month-click dates if set, otherwise full range
    default_start = st.session_state.get('filter_date_start', min_date)
    default_end   = st.session_state.get('filter_date_end', max_date)
    date_range = st.date_input(
        'Date range',
        value=(default_start, default_end),
        min_value=min_date,
        max_value=max_date,
    )

with filter_col4:
    cities = sorted(event_data['city'].dropna().unique())
    city_options = ['All'] + cities
    # Set index to match session state city
    city_default = st.session_state['filter_city']
    city_index = city_options.index(city_default) if city_default in city_options else 0
    selected_city = st.selectbox('City', city_options, index=city_index)

# --- Borough filter (London only) ---
selected_borough = 'All'
if selected_city and selected_city.strip().lower() == 'london':
    london_boroughs = sorted(
        event_data[event_data['city'].str.strip().str.lower() == 'london']['london_borough']
        .dropna().unique()
    )
    borough_options = ['All'] + london_boroughs
    borough_default = st.session_state['filter_borough']
    borough_index = borough_options.index(borough_default) if borough_default in borough_options else 0
    selected_borough = st.selectbox('Borough', borough_options, index=borough_index)

# --- Apply filters ---
filtered = event_data.copy()

if selected_segment != 'All':
    filtered = filtered[filtered['segment'] == selected_segment]
if selected_genre != 'All':
    filtered = filtered[filtered['genre'] == selected_genre]

# Date range filter (already reflects month click via session state)
if isinstance(date_range, tuple) and len(date_range) == 2:
    start_d, end_d = date_range
    filtered = filtered[
        (filtered['date'] >= pd.Timestamp(start_d)) &
        (filtered['date'] <= pd.Timestamp(end_d))
    ]

# City/borough filter (already reflects area bar click via session state)
if selected_city != 'All':
    filtered = filtered[filtered['city'] == selected_city]
    if selected_borough != 'All':
        filtered = filtered[filtered['london_borough'] == selected_borough]

# --- Determine if we should show drill-down ---
show_drilldown = (
    selected_city != 'All'
    or month_clicked is not None
    or selected_segment != 'All'
)

# --- Map + optional drill-down side-by-side ---
map_data = filtered.dropna(subset=['latitude', 'longitude'])

if map_data.empty:
    st.warning('No events match the current filters.')
elif show_drilldown:
    # Side-by-side layout: map on left, sunburst + metrics on right
    map_col, sunburst_col = st.columns([3, 2])

    with map_col:
        # Zoom out for month-only or segment-only filter (UK-wide), zoom in for city
        if selected_city != 'All':
            zoom_level = 11
        else:
            zoom_level = 5

        fig_map = px.scatter_map(
            map_data,
            lat='latitude',
            lon='longitude',
            hover_name='venue',
            hover_data={'date': True, 'segment': True, 'genre': True, 'name': True},
            color='segment',
            color_discrete_map=SEGMENT_COLOUR_MAP,
            zoom=zoom_level,
            height=600,
        )
        fig_map.update_layout(
            map_style='carto-positron',
            margin=dict(l=0, r=0, t=0, b=0),
        )
        st.plotly_chart(fig_map, use_container_width=True)

    with sunburst_col:
        # Metrics
        num_events = len(filtered)
        num_major  = int(filtered['major_venue'].sum())

        met_col1, met_col2 = st.columns(2)
        with met_col1:
            st.metric('Upcoming Events', f'{num_events:,}')
        with met_col2:
            st.metric('Events in Large Venues', f'{num_major:,}')

        # Decide which sunburst to show:
        # - If city is selected: segment → genre → sub_genre breakdown (existing behaviour)
        # - If segment/genre filter but no city: area breakdown showing where events are
        if selected_city != 'All':
            # Category breakdown for the selected city
            st.caption('Segment / Genre / Sub-genre breakdown for applied filters.')

            if selected_city.strip().lower() == 'london':
                area_values = filtered['area'].dropna().unique().tolist()
                if selected_borough == 'All':
                    sunburst_title = 'All boroughs'
                else:
                    sunburst_title = selected_borough
            else:
                area_values = selected_city
                sunburst_title = selected_city

            if isinstance(date_range, tuple) and len(date_range) == 2:
                start_str = str(start_d)
                end_str   = str(end_d)
            else:
                start_str = None
                end_str   = None

            try:
                fig_sun, _, total = plot_sunburst(
                    filtered,
                    area=area_values,
                    start_date=start_str,
                    end_date=end_str,
                    title=sunburst_title,
                )
                fig_sun.update_layout(
                    margin=dict(l=10, r=10, t=60, b=10),
                    height=450,
                )
                st.plotly_chart(fig_sun, use_container_width=True)
            except ValueError as e:
                st.info(str(e))

        else:
            # Area breakdown: show where events are concentrated geographically
            filter_label = selected_segment
            if selected_genre != 'All':
                filter_label += f' / {selected_genre}'
            if month_clicked:
                filter_label += f' — {month_clicked}'
            st.caption(f'Geographic distribution of {filter_label} events by area.')

            # Build area counts for sunburst (city → area for London, just city otherwise)
            area_breakdown = (
                filtered.groupby(['city', 'area'])
                .size()
                .reset_index(name='event_count')
            )
            # Collapse small areas into "Other" for readability
            total_count = area_breakdown['event_count'].sum()
            threshold = total_count * 0.015  # group areas below 1.5%
            area_breakdown.loc[
                area_breakdown['event_count'] < threshold, 'area'
            ] = 'Other'
            area_breakdown = (
                area_breakdown.groupby(['city', 'area'])['event_count']
                .sum()
                .reset_index()
            )

            fig_area_sun = px.sunburst(
                area_breakdown,
                path=['city', 'area'],
                values='event_count',
                title=f'{filter_label}  ({total_count:,} events)',
                color_discrete_sequence=PALETTE,
            )
            fig_area_sun.update_traces(
                textinfo='label+value',
                hovertemplate='<b>%{label}</b><br>Events: %{value}<extra></extra>',
            )
            fig_area_sun.update_layout(
                margin=dict(l=10, r=10, t=60, b=10),
                height=450,
            )
            st.plotly_chart(fig_area_sun, use_container_width=True)
else:
    # No filter active — full-width map only
    fig_map = px.scatter_map(
        map_data,
        lat='latitude',
        lon='longitude',
        hover_name='venue',
        hover_data={'date': True, 'segment': True, 'genre': True, 'name': True},
        color='segment',
        color_discrete_map=SEGMENT_COLOUR_MAP,
        zoom=5,
        height=600,
    )
    fig_map.update_layout(
        map_style='carto-positron',
        margin=dict(l=0, r=0, t=0, b=0),
    )
    st.plotly_chart(fig_map, use_container_width=True)

st.divider()


