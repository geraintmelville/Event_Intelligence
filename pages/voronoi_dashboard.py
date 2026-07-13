"""
Sponsorship Territory Map (Voronoi)
====================================
Second page of the UK Event Intelligence dashboard.

Displays an interactive Voronoi diagram over UK events where each territory
polygon represents the "catchment area" of a sponsorship choice. Territories
are coloured by segment, with chosen sponsorships highlighted and the best
pick per city given a pulsing gold marker.

Click a territory to see its event breakdown over time.
"""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# Ensure the project root is on the path so local imports resolve
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from voronoi_dashboard import render_voronoi_tab  # noqa: E402

# ---------------------------------------------------------------------------
# Palette (consistent with main app.py)
# ---------------------------------------------------------------------------
PRIMARY   = '#1A3A8F'
SECONDARY = '#6B35C8'
ACCENT    = '#00B4C8'
DARK      = '#0D1F5C'
LIGHT     = '#C8B8F0'
NEUTRAL   = '#F4F4F6'

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title='Sponsorship Territories',
    page_icon='🗺️',
    layout='wide',
)

# ---------------------------------------------------------------------------
# Custom theme (CSS) — same as main dashboard
# ---------------------------------------------------------------------------
st.markdown(f"""
<style>
    .stApp {{
        background-color: {NEUTRAL};
    }}
    [data-testid="stSidebar"] {{
        background-color: {DARK};
    }}
    [data-testid="stSidebar"] * {{
        color: {NEUTRAL} !important;
    }}
    h1 {{
        color: {PRIMARY} !important;
    }}
    h2, h3, [data-testid="stSubheader"] {{
        color: {DARK} !important;
    }}
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
    [data-testid="stSelectbox"] label,
    [data-testid="stDateInput"] label {{
        color: {DARK} !important;
        font-weight: 600;
    }}
    .stSelectbox > div > div {{
        border-color: {LIGHT};
        border-radius: 6px;
    }}
    hr {{
        border-color: {LIGHT} !important;
    }}
    .stCaption, [data-testid="stCaption"] {{
        color: {SECONDARY} !important;
    }}
    [data-testid="stAlert"] {{
        border-left-color: {ACCENT};
        background-color: white;
    }}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

@st.cache_data
def load_voronoi_data():
    choices_df   = pd.read_csv('data/choices_df.csv')
    proximity_df = pd.read_csv('data/proximity_df.csv')
    events_df    = pd.read_csv('data/events.csv')
    return choices_df, proximity_df, events_df


choices_df, proximity_df, events_df = load_voronoi_data()

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
col1, col2 = st.columns([1, 8])
with col1:
    st.image('images/eventintelligence-logo.png', width=90)
with col2:
    st.title('Sponsorship Territory Map')
    st.caption('Voronoi territories showing event coverage per sponsorship choice')

st.divider()

# ---------------------------------------------------------------------------
# Render the voronoi tab
# ---------------------------------------------------------------------------
render_voronoi_tab(choices_df, proximity_df, events_df)
