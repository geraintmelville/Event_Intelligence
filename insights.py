import pandas as pd

def create_top_20_cities(data):
    total_events = data.groupby('city')['event_id'].count().sort_values(ascending=False).sum()
    top_20_cities = data.groupby('city')['event_id'].count().sort_values(ascending=False).head(21)
    london = top_20_cities['London']
    non_london_events = total_events - london
    top_20_cities = top_20_cities.drop(index='London') # drop London from data as it is an outlier
    top_20_cities = pd.DataFrame(top_20_cities).reset_index().rename(columns={'event_id': 'nb_events'})
    return london, non_london_events, top_20_cities

def create_top_20_areas(data):
    top_20_areas = data.groupby('area')['event_id'].count().sort_values(ascending=False).head(21)
    westminster = top_20_areas['Westminster']
    top_20_areas = top_20_areas.drop(index='Westminster') # drop London from data as it is an outlier
    top_20_areas = pd.DataFrame(top_20_areas).reset_index().rename(columns={'event_id': 'nb_events'})
    return westminster, top_20_areas
