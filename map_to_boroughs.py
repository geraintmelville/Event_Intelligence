import pandas as pd
import geopandas as gpd
from shapely.geometry import Point

# 0. Load your events data
events_df = pd.read_csv("data/events.csv")

# 1. Load London borough boundaries (33 boroughs, WGS84 lat/long)
boroughs = gpd.read_file(
    "https://raw.githubusercontent.com/radoi90/housequest-data/master/london_boroughs.geojson"
)[["name", "geometry"]].rename(columns={"name": "borough"})

# 2. Convert your events df into a GeoDataFrame
#    (swap 'latitude'/'longitude' for your actual column names)
events_gdf = gpd.GeoDataFrame(
    events_df,
    geometry=[Point(xy) for xy in zip(events_df["longitude"], events_df["latitude"])],
    crs="EPSG:4326"
)

# 3. Spatial join: attach borough name to each event (NaN if not within a borough)
events_gdf = gpd.sjoin(events_gdf, boroughs, how="left", predicate="within")
events_gdf = events_gdf.drop(columns="index_right")

# 4. New 'area' column: borough if it's a London event, otherwise the original city
#    Adjust the city string(s) below to match however "London" appears in your data
is_london = events_gdf["city"].str.strip().str.lower() == "london"

events_gdf["area"] = events_gdf["city"]
events_gdf.loc[is_london, "area"] = events_gdf.loc[is_london, "borough"]

# 5. Sanity checks
# London events that didn't match a borough (e.g. right on/outside the GLA boundary)
unmatched_london = events_gdf.loc[is_london & events_gdf["borough"].isna()]
events_gdf = events_gdf.drop(unmatched_london.index)
print(f"{len(unmatched_london)} London events did not match a borough and were dropped")

print(events_gdf["area"].value_counts().head(10))

# 6. Export to CSV (drop geometry + borough helper column; area has everything you need)
events_gdf.drop(columns=["geometry", "borough"]).to_csv(
    "data/events.csv", index=False
)