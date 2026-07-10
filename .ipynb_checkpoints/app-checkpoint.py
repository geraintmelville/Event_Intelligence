import streamlit as st 
import plotly.express as px
import pandas as pd
from insights import create_top_20_cities

event_data = pd.read_csv('data/events.csv')

col1, col2 = st.columns([1, 5])

with col1:
    st.image("images/eventintelligence-logo.png", width=100)

with col2:
    st.title("UK Event Density Yearly Forecast")

st.write('---')

st.subheader('Top 20 Cities by Event Frequency (excluding London)')
fig = px.bar(
  create_top_20_cities(event_data)[1],
  x='nb_events',
  y='city',
  orientation='h'
)

st.plotly_chart(fig)

st.write('---')

st.subheader('Distribution of UK Events Over the Coming Year')

fig = px.scatter_map(
    event_data,
    lat="latitude",
    lon="longitude",
    hover_name="venue",
    hover_data="date",
    color="segment",
    zoom=12,
    height=600
)

fig.update_layout(map_style="carto-darkmatter")

st.plotly_chart(fig)

st.write('---')

col1, col2, col3 = st.columns(3) 
with col1:
  st.metric('London Events', create_top_20_cities(event_data)[0])

