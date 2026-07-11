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
# SECTION 2: Top 20 Cities + Monthly Volume (side by side)
# ===========================================================================

sec2_col1, sec2_col2 = st.columns(2)

with sec2_col1:
    st.subheader('Top 20 Cities by Event Frequency')
    st.caption('London excluded — it accounts for the majority of activity and is analysed separately below.')
    _, _, top_20_df = create_top_20_cities(event_data)

    fig_bar = px.bar(
        top_20_df,
        x='nb_events',
        y='city',
        orientation='h',
        color_discrete_sequence=[PRIMARY],
        labels={'nb_events': 'Number of Events', 'city': ''},
    )
    fig_bar.update_layout(
        plot_bgcolor=NEUTRAL,
        paper_bgcolor=NEUTRAL,
        yaxis=dict(categoryorder='total ascending'),
        margin=dict(l=10, r=10, t=10, b=10),
        height=500,
    )
    st.plotly_chart(fig_bar, use_container_width=True)

with sec2_col2:
    st.subheader('When Does Event Activity Peak?')
    st.caption('Monthly event volume by segment')
    monthly = event_data.copy()
    monthly['month'] = monthly['date'].dt.to_period('M').astype(str)
    monthly_counts = (
        monthly.groupby(['month', 'segment'])
        .size()
        .reset_index(name='events')
    )
    fig_monthly = px.bar(
        monthly_counts,
        x='month',
        y='events',
        color='segment',
        color_discrete_sequence=PALETTE,
        labels={'month': '', 'events': 'Events', 'segment': 'Segment'},
    )
    fig_monthly.update_layout(
        plot_bgcolor=NEUTRAL,
        paper_bgcolor=NEUTRAL,
        margin=dict(l=10, r=10, t=10, b=10),
        height=500,
        xaxis_tickangle=-45,
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
    )
    st.plotly_chart(fig_monthly, use_container_width=True)

st.divider()

# ===========================================================================
# SECTION 3: Filtered Map + City Drill-Down
# ===========================================================================

st.subheader('Event Venue Map')
st.caption('Filter by segment, genre, time period, and/or city to explore event distribution.')

# --- Sidebar-style filters in columns ---
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
    date_range = st.date_input(
        'Date range',
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )

with filter_col4:
    cities = sorted(event_data['city'].dropna().unique())
    selected_city = st.selectbox('City', ['All'] + cities)

# --- Borough filter (London only) ---
selected_borough = 'All'
if selected_city and selected_city.strip().lower() == 'london':
    london_boroughs = sorted(
        event_data[event_data['city'].str.strip().str.lower() == 'london']['london_borough']
        .dropna().unique()
    )
    selected_borough = st.selectbox('Borough', ['All'] + london_boroughs)

# --- Apply filters ---
filtered = event_data.copy()

if selected_segment != 'All':
    filtered = filtered[filtered['segment'] == selected_segment]
if selected_genre != 'All':
    filtered = filtered[filtered['genre'] == selected_genre]
if isinstance(date_range, tuple) and len(date_range) == 2:
    start_d, end_d = date_range
    filtered = filtered[
        (filtered['date'] >= pd.Timestamp(start_d)) &
        (filtered['date'] <= pd.Timestamp(end_d))
    ]
if selected_city != 'All':
    filtered = filtered[filtered['city'] == selected_city]
if selected_borough != 'All':
    filtered = filtered[filtered['london_borough'] == selected_borough]

# --- Map + optional city drill-down side-by-side ---
map_data = filtered.dropna(subset=['latitude', 'longitude'])

if map_data.empty:
    st.warning('No events match the current filters.')
elif selected_city != 'All':
    # Side-by-side layout: map on left, sunburst + metrics on right
    map_col, sunburst_col = st.columns([3, 2])

    with map_col:
        fig_map = px.scatter_map(
            map_data,
            lat='latitude',
            lon='longitude',
            hover_name='venue',
            hover_data={'date': True, 'segment': True, 'genre': True, 'name': True},
            color='segment',
            color_discrete_sequence=PALETTE,
            zoom=11,
            height=600,
        )
        fig_map.update_layout(
            map_style='carto-positron',
            margin=dict(l=0, r=0, t=0, b=0),
        )
        st.plotly_chart(fig_map, use_container_width=True)

    with sunburst_col:
        # Metrics — reflects the segment/genre/date filters applied
        num_events = len(filtered)
        num_major  = int(filtered['major_venue'].sum())

        met_col1, met_col2 = st.columns(2)
        with met_col1:
            st.metric('Upcoming Events', f'{num_events:,}')
        with met_col2:
            st.metric('Events in Large Venues', f'{num_major:,}')

        # Sunburst — uses the filtered data so segment/genre filters apply
        st.caption('Segment / Genre / Sub-genre breakdown for applied filters.')

        if selected_city.strip().lower() == 'london':
            area_values = filtered['area'].dropna().unique().tolist()
        else:
            area_values = selected_city

        start_str = str(start_d) if isinstance(date_range, tuple) and len(date_range) == 2 else None
        end_str   = str(end_d)   if isinstance(date_range, tuple) and len(date_range) == 2 else None

        try:
            fig_sun, _, total = plot_sunburst(
                filtered,
                area=area_values,
                start_date=start_str,
                end_date=end_str,
            )
            fig_sun.update_layout(
                margin=dict(l=10, r=10, t=60, b=10),
                height=450,
            )
            st.plotly_chart(fig_sun, use_container_width=True)
        except ValueError as e:
            st.info(str(e))
else:
    # No city filter — full-width map only
    fig_map = px.scatter_map(
        map_data,
        lat='latitude',
        lon='longitude',
        hover_name='venue',
        hover_data={'date': True, 'segment': True, 'genre': True, 'name': True},
        color='segment',
        color_discrete_sequence=PALETTE,
        zoom=5,
        height=600,
    )
    fig_map.update_layout(
        map_style='carto-positron',
        margin=dict(l=0, r=0, t=0, b=0),
    )
    st.plotly_chart(fig_map, use_container_width=True)

st.divider()


