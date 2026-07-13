"""
territory_breakdown.py
======================
Given a clicked Voronoi polygon (its centre event_id), resolve the events that
polygon covers (centre + nearby_event_ids from proximity_df), join them to
events.csv for dates/segments, and build a segment-coloured histogram of
events over time.

The histogram:
  - x axis = date (zoomable/pannable via Plotly)
  - bars stacked & coloured by segment
  - hover shows event name(s) + segment + date
"""

import ast

import pandas as pd
import plotly.express as px

SEGMENT_COLOUR_MAP = {
    'Music':          '#1A3A8F',
    'Sports':         '#6B35C8',
    'Arts & Theatre': '#00B4C8',
    'Film':           '#0D1F5C',
    'Miscellaneous':  '#C8B8F0',
    'Undefined':      '#9CA3AF',
    'Unknown':        '#9CA3AF',
}


def _parse_list(val):
    if isinstance(val, list):
        return val
    if pd.isna(val) or val == '':
        return []
    try:
        return ast.literal_eval(val)
    except (ValueError, SyntaxError):
        return []


def covered_events_for(centre_event_id: str,
                       proximity_df: pd.DataFrame,
                       events_df: pd.DataFrame) -> pd.DataFrame:
    """
    Return a dataframe of events covered by the polygon whose centre is
    `centre_event_id`: the centre event itself plus its nearby_event_ids,
    enriched with date + segment from events_df.
    """
    prox_row = proximity_df[proximity_df['event_id'] == centre_event_id]
    if prox_row.empty:
        return pd.DataFrame(columns=['event_id', 'name', 'date', 'segment'])

    nearby_ids = _parse_list(prox_row.iloc[0].get('nearby_event_ids'))
    all_ids = [centre_event_id] + list(nearby_ids)

    ev = events_df.set_index('event_id')
    sub = ev.reindex(all_ids).reset_index()
    sub = sub.dropna(subset=['date'])
    sub['date'] = pd.to_datetime(sub['date'], errors='coerce')
    sub = sub.dropna(subset=['date'])
    sub['segment'] = sub['segment'].fillna('Unknown')
    return sub[['event_id', 'name', 'date', 'segment']]


def build_breakdown_histogram(covered_df: pd.DataFrame, centre_name: str):
    """
    Build a segment-coloured, time-binned histogram from covered events.
    Returns a plotly Figure (or None if there's nothing to plot).
    """
    if covered_df.empty:
        return None

    # One row per event; group into per-day, per-segment counts so hover can
    # list the actual event names on each bar.
    covered_df = covered_df.copy()
    covered_df['day'] = covered_df['date'].dt.date

    grouped = (
        covered_df
        .groupby(['day', 'segment'])
        .agg(count=('event_id', 'size'),
             events=('name', lambda s: '<br>'.join(sorted(set(s))[:12]) +
                     ('<br>…' if s.nunique() > 12 else '')))
        .reset_index()
    )
    grouped['day'] = pd.to_datetime(grouped['day'])

    fig = px.bar(
        grouped,
        x='day',
        y='count',
        color='segment',
        color_discrete_map=SEGMENT_COLOUR_MAP,
        custom_data=['segment', 'events'],
        title=f'Events covered by “{centre_name}” — by day & segment',
    )
    fig.update_traces(
        hovertemplate=(
            '<b>%{x|%d %b %Y}</b><br>'
            'Segment: %{customdata[0]}<br>'
            'Count: %{y}<br>'
            '%{customdata[1]}<extra></extra>'
        )
    )
    fig.update_layout(
        barmode='stack',
        xaxis_title='Date',
        yaxis_title='Number of events',
        legend_title='Segment',
        margin=dict(t=50, l=10, r=10, b=10),
        height=380,
        bargap=0.15,
    )
    # Enable range slider so the user can zoom into specific days
    fig.update_xaxes(rangeslider_visible=True, type='date')
    return fig
