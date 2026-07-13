"""
voronoi_dashboard.py
====================
Streamlit tab: interactive UK map of sponsorship Voronoi territories.

- Voronoi is built over EVERY event that month (from proximity_df), so every
  event — chosen sponsorship or not — gets its own territory polygon.
- Polygons are coloured by segment (SEGMENT_COLOUR_MAP).
- Chosen sponsorships (from choices_df) get a bolder navy border; every
  other event gets a thin grey border.
- The best sponsorship IN EACH CITY (highest nearby_count) gets a gold
  glowing pulsing marker — one glow per city, not just one nationally.
- Click a polygon -> see its details and nearby events.

Integrate into app.py with:
    from voronoi_dashboard import render_voronoi_tab
    render_voronoi_tab(choices_df, proximity_df)
"""

import folium
import pandas as pd
import streamlit as st
from folium import DivIcon
from streamlit_folium import st_folium

from voronoi_utils import build_voronoi_geojson
from territory_breakdown import covered_events_for, build_breakdown_histogram

UK_CENTER = [54.5, -3.5]

PRIMARY   = '#1A3A8F'   # Music
SECONDARY = '#6B35C8'   # Sports
ACCENT    = '#00B4C8'   # Arts & Theatre
DARK      = '#0D1F5C'   # Film
LIGHT     = '#C8B8F0'   # Miscellaneous
GREY      = '#9CA3AF'   # Undefined / unknown segment

SEGMENT_COLOUR_MAP = {
    'Music':          PRIMARY,
    'Sports':         SECONDARY,
    'Arts & Theatre': ACCENT,
    'Film':           DARK,
    'Miscellaneous':  LIGHT,
}

GOLD = '#FFD700'
CHOSEN_BORDER = '#1A1A2E'

_PULSE_CSS = """
<style>
@keyframes pulse-glow {
    0%   { box-shadow: 0 0 4px 2px rgba(255, 215, 0, 0.9); }
    50%  { box-shadow: 0 0 16px 8px rgba(255, 215, 0, 0.9); }
    100% { box-shadow: 0 0 4px 2px rgba(255, 215, 0, 0.9); }
}
.best-marker {
    width: 14px; height: 14px; border-radius: 50%;
    background: #FFD700; border: 2px solid #7a5c00;
    animation: pulse-glow 1.4s ease-in-out infinite;
}
</style>
"""

def _segment_colour(segment):
    return SEGMENT_COLOUR_MAP.get(segment, GREY)


def render_voronoi_tab(choices_df: pd.DataFrame, proximity_df: pd.DataFrame,
                       events_df: pd.DataFrame):
    st.subheader('Sponsorship Territory Map')
    st.caption(
        'Every event that month has its own territory, coloured by segment. '
        'Chosen sponsorships have a bold border. The gold glowing marker is '
        'the best pick in each city. Click a polygon for details.'
    )

    months = sorted(choices_df['month'].dropna().unique())
    selected_month = st.selectbox('Month', months, index=0)

    choices_sub = choices_df[choices_df['month'] == selected_month]
    month_events = proximity_df[proximity_df['month'] == selected_month].dropna(
        subset=['latitude', 'longitude']
    )

    if len(month_events) < 4:
        st.warning('Need at least 4 events to draw a Voronoi diagram for this month.')
        return

    # Voronoi over EVERY event that month — not just the chosen sponsorships —
    # so every event gets its own territory.
    geojson = build_voronoi_geojson(month_events, proximity_df)

    chosen_ids = set(choices_sub['event_id'])
    # Best pick PER CITY (not just one nationally) -> one glow marker per city.
    best_per_city = choices_sub.loc[choices_sub.groupby('city')['nearby_count'].idxmax()]
    glow_ids = set(best_per_city['event_id'])

    fmap = folium.Map(location=UK_CENTER, zoom_start=6, tiles='cartodbpositron')
    fmap.get_root().html.add_child(folium.Element(_PULSE_CSS))

    # --- Enrich each feature with is_chosen / is_glow / display fields, then
    #     render as ONE GeoJson layer (not one folium object per polygon) so
    #     ~1,000+ territories don't bloat the page and stall the browser. ---
    for feature in geojson['features']:
        props = feature['properties']
        props['is_chosen'] = props['event_id'] in chosen_ids
        props['is_glow'] = props['event_id'] in glow_ids
        props['segment_display'] = props.get('segment') or 'Unknown'
        names = props.get('nearby_names') or []
        props['nearby_display'] = ', '.join(names[:8]) + (f' (+{len(names)-8} more)' if len(names) > 8 else '')
        props['badge'] = '🏆 Best pick in ' + props['city'] if props['is_glow'] else ''

    def style_fn(feature):
        props = feature['properties']
        colour = _segment_colour(props.get('segment'))
        if props['is_glow']:
            return {'fillColor': colour, 'color': GOLD, 'weight': 4, 'fillOpacity': 0.7, 'dashArray': '6,3'}
        elif props['is_chosen']:
            return {'fillColor': colour, 'color': CHOSEN_BORDER, 'weight': 2, 'fillOpacity': 0.55}
        else:
            return {'fillColor': colour, 'color': '#999999', 'weight': 0.5, 'fillOpacity': 0.25}

    def highlight_fn(feature):
        return {'weight': 4, 'fillOpacity': 0.8}

    folium.GeoJson(
        geojson,
        name='Event territories',
        style_function=style_fn,
        highlight_function=highlight_fn,
        tooltip=folium.GeoJsonTooltip(
            fields=['badge', 'name', 'segment_display', 'city', 'nearby_count'],
            aliases=['', 'Event', 'Segment', 'City', 'Nearby events'],
            sticky=True,
        ),
        popup=folium.GeoJsonPopup(
            fields=['badge', 'name', 'segment_display', 'city', 'nearby_count', 'nearby_display'],
            aliases=['', 'Event', 'Segment', 'City', 'Nearby count', 'Nearby events'],
            max_width=320,
        ),
    ).add_to(fmap)

    # --- One glowing pulsing marker per city's best pick ---
    for _, row in best_per_city.iterrows():
        folium.Marker(
            location=[row['latitude'], row['longitude']],
            icon=DivIcon(html='<div class="best-marker"></div>'),
            tooltip=f"🏆 Best pick — {row['city']}: {row['name']}",
        ).add_to(fmap)

    folium.LayerControl(collapsed=False).add_to(fmap)

    # --- Legend ---
    legend_items = ''.join(
        f'<div><span style="display:inline-block;width:12px;height:12px;'
        f'background:{colour};margin-right:6px;border-radius:2px;"></span>{seg}</div>'
        for seg, colour in SEGMENT_COLOUR_MAP.items()
    )
    legend_html = f"""
    <div style="position: fixed; bottom: 30px; left: 30px; z-index: 9999;
                background: white; padding: 10px 14px; border-radius: 6px;
                border: 1px solid #ccc; font-family: sans-serif; font-size: 13px;
                box-shadow: 0 1px 4px rgba(0,0,0,0.2);">
        <b>Segment</b><br>{legend_items}
        <div style="margin-top:6px;">
            <span style="display:inline-block;width:12px;height:12px;
                  border:2px solid {CHOSEN_BORDER};margin-right:6px;"></span>Chosen sponsorship
        </div>
        <div style="margin-top:4px;">
            <span style="display:inline-block;width:12px;height:12px;
                  border:2px dashed {GOLD};margin-right:6px;"></span>Best pick per city
        </div>
    </div>
    """
    fmap.get_root().html.add_child(folium.Element(legend_html))

    map_state = st_folium(
        fmap, width=None, height=650,
        returned_objects=['last_object_clicked', 'last_active_drawing'],
    )

    st.caption(
        f'{len(geojson["features"]):,} event territories · '
        f'{len(chosen_ids)} chosen sponsorships · '
        f'{len(glow_ids)} city best-picks — {selected_month}'
    )

    # --- Click -> territory breakdown histogram ---
    # st_folium gives us the clicked geometry (last_active_drawing) whose
    # properties carry the centre event_id; fall back to matching the clicked
    # lat/lng to the nearest polygon centre if properties aren't present.
    clicked_event_id = None
    clicked_name = None

    drawing = map_state.get('last_active_drawing')
    if drawing and isinstance(drawing, dict):
        props = drawing.get('properties') or {}
        clicked_event_id = props.get('event_id')
        clicked_name = props.get('name')

    if clicked_event_id is None:
        click = map_state.get('last_object_clicked')
        if click and 'lat' in click and 'lng' in click:
            # Nearest polygon centre to the click point
            feats = geojson['features']
            best = min(
                feats,
                key=lambda f: (f['properties']['latitude'] - click['lat']) ** 2
                + (f['properties']['longitude'] - click['lng']) ** 2,
            )
            clicked_event_id = best['properties']['event_id']
            clicked_name = best['properties']['name']

    st.markdown('---')
    if clicked_event_id is None:
        st.info('Click a territory on the map to see its event breakdown over time.')
    else:
        covered = covered_events_for(clicked_event_id, proximity_df, events_df)
        st.markdown(f'#### Breakdown for “{clicked_name}” — {len(covered)} events covered')
        fig = build_breakdown_histogram(covered, clicked_name)
        if fig is None:
            st.warning('No dated events found for this territory.')
        else:
            st.plotly_chart(fig, use_container_width=True)


if __name__ == '__main__':
    st.set_page_config(page_title='Voronoi Test', layout='wide')
    choices = pd.read_csv('data/choices_df.csv')
    proximity = pd.read_csv('data/proximity_df.csv')
    events = pd.read_csv('data/events.csv')
    render_voronoi_tab(choices, proximity, events)
