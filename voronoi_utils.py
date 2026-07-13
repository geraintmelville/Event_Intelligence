"""
voronoi_utils.py
================
Builds a clipped Voronoi diagram from sponsorship 'choice' points and
packages each cell as a GeoJSON feature carrying the centre event's
details plus the list of nearby events that fall under that centre
(pulled from proximity_df's nearby_event_ids / nearby_names).

Usage:
    geojson, points_df = build_voronoi_geojson(choices_df, proximity_df)
"""

import ast
import json
import os

import numpy as np
import pandas as pd
from scipy.spatial import Voronoi
from shapely.geometry import Polygon, Point, box, shape, mapping
from shapely.ops import unary_union

_UK_BOUNDARY_PATH = os.path.join(os.path.dirname(__file__), 'uk_boundary.geojson')
_uk_boundary_cache = None


def _load_uk_boundary():
    """Load the real UK coastline polygon (cached) for clipping Voronoi cells."""
    global _uk_boundary_cache
    if _uk_boundary_cache is None:
        with open(_UK_BOUNDARY_PATH) as f:
            gj = json.load(f)
        _uk_boundary_cache = unary_union([shape(feat['geometry']) for feat in gj['features']])
    return _uk_boundary_cache


def _parse_list_col(val):
    """proximity_df stores nearby_event_ids / nearby_names as stringified lists."""
    if isinstance(val, list):
        return val
    if pd.isna(val) or val == '':
        return []
    try:
        return ast.literal_eval(val)
    except (ValueError, SyntaxError):
        return []


def _voronoi_finite_polygons(vor, bound_box, clip_shape=None):
    """
    Convert scipy Voronoi's (possibly infinite) regions into finite,
    clipped shapely Polygons — one per input point, same order as vor.points.

    bound_box:  shapely box() used only to size how far infinite ridges get
                extended (must fully contain clip_shape).
    clip_shape: the shapely geometry each polygon is actually clipped to
                (e.g. the real UK coastline). Falls back to bound_box if None.
    """
    if clip_shape is None:
        clip_shape = bound_box
    center = vor.points.mean(axis=0)
    bx0, by0, bx1, by1 = bound_box.bounds
    radius = max(bx1 - bx0, by1 - by0) * 4 + 1  # far enough to exceed bound_box/clip_shape

    # Map each ridge to the two regions it separates
    ridge_by_point = {}
    for (p1, p2), (v1, v2) in zip(vor.ridge_points, vor.ridge_vertices):
        ridge_by_point.setdefault(p1, []).append((p2, v1, v2))
        ridge_by_point.setdefault(p2, []).append((p1, v1, v2))

    polygons = []
    for point_idx, region_idx in enumerate(vor.point_region):
        region = vor.regions[region_idx]

        if region and -1 not in region:
            # Already finite
            poly_pts = [vor.vertices[i] for i in region]
        else:
            # Reconstruct infinite region by extending open ridges outward
            poly_pts = [vor.vertices[i] for i in region if i != -1]

            for other_idx, v1, v2 in ridge_by_point.get(point_idx, []):
                if v1 == -1 or v2 == -1:
                    finite_v = v2 if v1 == -1 else v1
                    t = vor.points[other_idx] - vor.points[point_idx]
                    t = t / np.linalg.norm(t)
                    normal = np.array([-t[1], t[0]])
                    midpoint = (vor.points[point_idx] + vor.points[other_idx]) / 2
                    direction = np.sign(np.dot(midpoint - center, normal)) * normal
                    far_point = vor.vertices[finite_v] + direction * radius
                    poly_pts.append(far_point)

            if len(poly_pts) < 3:
                polygons.append(None)
                continue

            # Order points angularly around their centroid so Polygon() is valid
            pts_arr = np.array(poly_pts)
            centroid = pts_arr.mean(axis=0)
            angles = np.arctan2(pts_arr[:, 1] - centroid[1], pts_arr[:, 0] - centroid[0])
            poly_pts = pts_arr[np.argsort(angles)].tolist()

        try:
            poly = Polygon(poly_pts).intersection(clip_shape)
        except Exception:
            poly = None
        polygons.append(poly)

    return polygons


def build_voronoi_geojson(choices_df: pd.DataFrame,
                           proximity_df: pd.DataFrame,
                           buffer_deg: float = 0.15) -> dict:
    """
    Parameters
    ----------
    choices_df : the post-set-covering centres (one row per sponsorship).
                 Must have: event_id, name, city, month, latitude, longitude, nearby_count
    proximity_df : pre-set-covering table with nearby_event_ids / nearby_names
                   per event_id (used to enrich each centre's popup).
    buffer_deg : padding (in degrees) added around the points' bounding box
                 before clipping — keeps outer cells from running to infinity
                 while still looking reasonable on a UK-scale map.

    Returns
    -------
    dict : a GeoJSON FeatureCollection. Each feature.properties has:
           event_id, name, city, month, nearby_count, nearby_names (list)
    """
    df = choices_df.dropna(subset=['latitude', 'longitude']).reset_index(drop=True)

    # Drop obviously bad / out-of-UK coordinates (e.g. (0,0), or outside GB bounding box)
    # so they don't blow up the bounding box used for clipping.
    uk_mask = (
        df['latitude'].between(49.5, 61) &
        df['longitude'].between(-8.5, 2)
    )
    dropped = df.loc[~uk_mask]
    if not dropped.empty:
        print(f"Dropping {len(dropped)} out-of-UK / bad coordinate rows: "
              f"{dropped[['event_id', 'city', 'latitude', 'longitude']].to_dict('records')}")
    df = df.loc[uk_mask].reset_index(drop=True)

    if len(df) < 4:
        raise ValueError('Need at least 4 points to build a Voronoi diagram.')

    # Lookup nearby names/ids per centre from proximity_df
    prox_lookup = proximity_df.set_index('event_id')

    points = df[['longitude', 'latitude']].to_numpy().astype(float)

    # Qhull (scipy's Voronoi backend) can crash the whole process — not just
    # raise a catchable Python exception — on exactly duplicate input points,
    # on some platforms/scipy builds. Nudge duplicates apart by a negligible
    # amount (~0.1m) so every point is numerically distinct.
    seen = {}
    rng = np.random.default_rng(42)  # deterministic jitter
    for i, pt in enumerate(points):
        key = (round(pt[0], 9), round(pt[1], 9))
        if key in seen:
            points[i] += rng.uniform(-1e-6, 1e-6, size=2)
        else:
            seen[key] = i

    vor = Voronoi(points)

    # Real UK coastline — this is what cells actually get clipped to.
    uk_shape = _load_uk_boundary()

    # Rectangular box: only used to give infinite ridges somewhere far enough
    # to extend to before we clip to the real coastline below. Must cover the
    # full UK extent (not just the current point subset), otherwise filtering
    # to a single month/city can produce a box too small to reach the coastline.
    uk_minx, uk_miny, uk_maxx, uk_maxy = uk_shape.bounds
    minx, miny = points.min(axis=0) - buffer_deg
    maxx, maxy = points.max(axis=0) + buffer_deg
    bound_box = box(
        min(minx, uk_minx), min(miny, uk_miny),
        max(maxx, uk_maxx), max(maxy, uk_maxy),
    )

    polygons = _voronoi_finite_polygons(vor, bound_box, clip_shape=uk_shape)

    features = []
    for i, poly in enumerate(polygons):
        if poly is None or poly.is_empty:
            continue

        row = df.iloc[i]
        nearby_ids = []
        nearby_names = []
        segment = None
        if row['event_id'] in prox_lookup.index:
            prox_row = prox_lookup.loc[row['event_id']]
            nearby_ids = _parse_list_col(prox_row.get('nearby_event_ids'))
            nearby_names = _parse_list_col(prox_row.get('nearby_names'))
            segment = prox_row.get('segment')

        geom = mapping(poly)
        features.append({
            "type": "Feature",
            "geometry": geom,
            "properties": {
                "event_id": row['event_id'],
                "name": row['name'],
                "city": row['city'],
                "month": str(row['month']),
                "latitude": row['latitude'],
                "longitude": row['longitude'],
                "nearby_count": int(row['nearby_count']),
                "nearby_event_ids": nearby_ids,
                "nearby_names": nearby_names,
                "segment": segment,
            }
        })

    return {"type": "FeatureCollection", "features": features}


if __name__ == '__main__':
    choices = pd.read_csv('data/choices_df.csv')
    proximity = pd.read_csv('data/proximity_df.csv')

    gj = build_voronoi_geojson(choices, proximity)
    print(f"Built {len(gj['features'])} Voronoi cells (of {len(choices)} centres)")

    with open('voronoi_test.geojson', 'w') as f:
        json.dump(gj, f)
    print("Saved voronoi_test.geojson")
