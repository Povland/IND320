# Maps with plotly, on an open map background (no token needed).
#   - area_map: one area with its ERA5 grid cells, sized by how many random locations fell in each (the weights)
#   - overview_map: all areas of one type, coloured by a value (e.g. the filling degree), with chosen areas outlined
# The areas come from ind320.areas (clipped to land, EPSG:25833). They are converted to latitude and longitude
# and simplified before drawing, since large GeoJSON makes the map slow in the browser.

import json

import numpy as np
import plotly.graph_objects as go

# Map background without a token
MAP_STYLE = "carto-positron"

AREA_COLOR = "#2a78d6"      # blue, as in the other plots
CELL_COLOR = "#eb6834"      # orange, for what stands out


# The areas as GeoJSON for plotly, in latitude and longitude, simplified by tolerance degrees (0.01° is about 1 km).
# Each area gets an id like "EL 3", which the maps use to match values to areas
def to_geojson(areas, tolerance=0.01):
    simple = areas.to_crs(4326)[["area_type", "area_nr", "geometry"]].copy()
    simple["geometry"] = simple.geometry.simplify(tolerance, preserve_topology=True)
    simple["area_id"] = simple["area_type"] + " " + simple["area_nr"].astype(str)
    return json.loads(simple.to_json()), simple["area_id"].tolist()


# The centre and zoom level that fit the areas on the map
def _view(areas):
    min_lon, min_lat, max_lon, max_lat = areas.to_crs(4326).total_bounds
    span = max(max_lon - min_lon, (max_lat - min_lat) * 2)     # a degree of latitude is about twice as wide here
    zoom = float(np.clip(8.5 - np.log2(span + 1e-6), 2, 9))
    return {"lat": (min_lat + max_lat) / 2, "lon": (min_lon + max_lon) / 2}, zoom


# One area (a one-row table from ind320.areas) with its grid cells (latitude, longitude, n_points).
# The dot size grows with n_points, so the cells that count most in the average are the biggest
def area_map(area, cells, title=None, height=500):
    geojson, ids = to_geojson(area)
    center, zoom = _view(area)

    fig = go.Figure()
    fig.add_trace(go.Choroplethmap(
        geojson=geojson, locations=ids, featureidkey="properties.area_id",
        z=[1] * len(ids), colorscale=[[0, AREA_COLOR], [1, AREA_COLOR]], showscale=False,
        marker_opacity=0.25, marker_line_width=1.5, marker_line_color=AREA_COLOR,
        hoverinfo="skip", name="Area",
    ))
    fig.add_trace(go.Scattermap(
        lat=cells["latitude"], lon=cells["longitude"], mode="markers",
        marker=dict(size=4 + 4 * np.sqrt(cells["n_points"]), color=CELL_COLOR, opacity=0.8),
        customdata=cells["n_points"],
        hovertemplate="%{lat:.2f}° N, %{lon:.2f}° E<br>%{customdata} locations<extra></extra>",
        name="Grid cells",
    ))
    fig.update_layout(
        title=title, height=height, showlegend=False,
        map=dict(style=MAP_STYLE, center=center, zoom=zoom),
        margin=dict(l=0, r=0, t=40 if title else 0, b=0),
    )
    return fig


# All areas of one type (a table from ind320.areas), coloured by values: a dict or Series from area_nr to a value.
# The areas in selected (area numbers) get a thick outline on top. value_format is a d3 format, e.g. ".0%"
def overview_map(areas, values, selected=(), title=None, label="Value", value_format=".0%", zmin=None, zmax=None, height=550):
    shown = areas.copy()
    shown["value"] = shown["area_nr"].map(values)
    geojson, ids = to_geojson(shown)
    center, zoom = _view(shown)

    fig = go.Figure(go.Choroplethmap(
        geojson=geojson, locations=ids, featureidkey="properties.area_id",
        z=shown["value"], zmin=zmin, zmax=zmax, colorscale="Blues",
        marker_opacity=0.8, marker_line_width=0.8, marker_line_color="white",
        colorbar=dict(title=label, tickformat=value_format),
        hovertemplate=f"%{{location}}: %{{z:{value_format}}}<extra></extra>",
        name=label,
    ))

    # The chosen areas: a transparent layer with a thick outline
    chosen = shown[shown["area_nr"].isin(list(selected))]
    if not chosen.empty:
        chosen_geojson, chosen_ids = to_geojson(chosen)
        fig.add_trace(go.Choroplethmap(
            geojson=chosen_geojson, locations=chosen_ids, featureidkey="properties.area_id",
            z=[0] * len(chosen_ids), colorscale=[[0, "rgba(0,0,0,0)"], [1, "rgba(0,0,0,0)"]], showscale=False,
            marker_line_width=3, marker_line_color=CELL_COLOR, hoverinfo="skip", name="Chosen",
        ))

    fig.update_layout(
        title=title, height=height,
        map=dict(style=MAP_STYLE, center=center, zoom=zoom),
        margin=dict(l=0, r=0, t=40 if title else 0, b=0),
    )
    return fig