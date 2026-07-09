import pandas as pd

def create_top_20_cities(data):
  top_20_cities = data.groupby('city')['event_id'].count().sort_values(ascending=False).head(21)
  london = top_20_cities['London']
  top_20_cities = top_20_cities.drop(index='London') # drop London from data as it is an outlier
  top_20_cities = pd.DataFrame(top_20_cities).reset_index().rename(columns={'event_id': 'nb_events'})
  
  return london, top_20_cities