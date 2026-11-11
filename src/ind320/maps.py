# Maps with plotly, on an open map background (no token needed).
#   - area_map: one area with its ERA5 grid cells, sized by how many random locations fell in each (the weights)
#   - overview_map: all areas of one type, coloured by a value (e.g. the filling degree), with chosen areas outlined
# The areas come from ind320.areas (clipped to land, EPSG:25833). They are converted to latitude and longitude
# and simplified before drawing, since large GeoJSON makes the map slow in the browser.

import json
import math

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


# Latitude in degrees -> the y coordinate of the Mercator projection the map uses, also in degrees.
# Mercator stretches the map more and more towards the north, so the north of Norway takes up more height
def _mercator(lat):
    return math.degrees(math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)))


# The centre and zoom level that fit the areas in a map of the given height (in pixels).
# The width is assumed to be at least 1.25 times the height. The height is measured in Mercator,
# so all of Norway fits from Lindesnes to Finnmark. padding zooms out a little, so the coast doesn't touch the edge
def _view(areas, height, padding=0.3):
    width = height * 1.25
    min_lon, min_lat, max_lon, max_lat = areas.to_crs(4326).total_bounds
    lon_span = max(max_lon - min_lon, 0.01)
    y_min, y_max = _mercator(min_lat), _mercator(max_lat)
    y_span = max(y_max - y_min, 0.01)

    # A map tile is 512 pixels wide and covers 360 degrees at zoom 0, and twice as much detail per zoom level
    zoom = math.log2(min(width * 360 / (512 * lon_span), height * 360 / (512 * y_span))) - padding

    # The centre is the middle in Mercator, converted back to latitude
    centre_lat = math.degrees(2 * math.atan(math.exp(math.radians((y_min + y_max) / 2))) - math.pi / 2)
    return {"lat": centre_lat, "lon": (min_lon + max_lon) / 2}, float(np.clip(zoom, 2, 10))


# One area (a one-row table from ind320.areas) with its grid cells (latitude, longitude, n_points).
# The dot size grows with n_points, so the cells that count most in the average are the biggest
def area_map(area, cells, title=None, height=500):
    geojson, ids = to_geojson(area)
    center, zoom = _view(area, height)

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


# The layout of the overview maps: a plotly "geo" map without background tiles, zoomed to exactly the areas
# shown (fitbounds), in the Mercator projection like ordinary web maps. Plotly draws the areas itself as shapes,
# which is what makes the animation work: each frame only recolours the shapes already drawn
def _geo_layout(fig, title, height, bottom=0):
    fig.update_geos(fitbounds="locations", visible=False, projection_type="mercator", bgcolor="rgba(0,0,0,0)")
    fig.update_layout(
        title=title, height=height,
        margin=dict(l=0, r=0, t=40 if title else 0, b=bottom),
        paper_bgcolor="rgba(0,0,0,0)",
    )


# All areas of one type (a table from ind320.areas), coloured by values: a dict or Series from area_nr to a value.
# The areas in selected (area numbers) get an outline on top. value_format is a d3 format, e.g. ".0%".
# Drawn as a plotly geo map (no background tiles), zoomed to fit the areas
def overview_map(areas, values, selected=(), title=None, label="Value", value_format=".0%", zmin=None, zmax=None, height=600):
    shown = areas.copy()
    shown["value"] = shown["area_nr"].map(values)
    geojson, ids = to_geojson(shown)

    fig = go.Figure(go.Choropleth(
        geojson=geojson, locations=ids, featureidkey="properties.area_id",
        z=shown["value"], zmin=zmin, zmax=zmax, colorscale="Blues",
        marker_line_width=0.8, marker_line_color="white",
        colorbar=dict(title=label, tickformat=value_format),
        hovertemplate=f"%{{location}}: %{{z:{value_format}}}<extra></extra>",
        name=label,
    ))

    # The chosen areas: a transparent layer with an outline
    chosen = shown[shown["area_nr"].isin(list(selected))]
    if not chosen.empty:
        chosen_geojson, chosen_ids = to_geojson(chosen)
        fig.add_trace(go.Choropleth(
            geojson=chosen_geojson, locations=chosen_ids, featureidkey="properties.area_id",
            z=[0] * len(chosen_ids), colorscale=[[0, "rgba(0,0,0,0)"], [1, "rgba(0,0,0,0)"]], showscale=False,
            marker_line_width=1.5, marker_line_color=CELL_COLOR, hoverinfo="skip", name="Chosen",
        ))

    _geo_layout(fig, title, height)
    return fig


# The height (in pixels) of the play controls under the animated map. The page uses the same height for the week
# slider under the static map, so the map and the controls are in the same place in both modes
CONTROLS_HEIGHT = 100
PLAY_SPEEDS = {"Slow": 200, "Normal": 40, "Fast": 4}

# Colours for the play buttons, the slider and the week counter, matching Streamlit's light and dark themes.
# Plotly's own defaults (white buttons with dark text) don't follow the theme
CONTROL_COLORS = {
    False: dict(text="#31333f", background="#f0f2f6", active="#d5dae5", border="#c7ccd6"),   # light
    True: dict(text="#fafafa", background="#262730", active="#4a4f5c", border="#4a4f5c"),    # dark
}


# The overview map played over time: one frame per row of table (index: dates, columns: area numbers).
# The map is sent to the browser once, and each frame only holds the new colours, so plotly plays it in the browser.
# The speed buttons (Slow, Normal, Fast) are part of the map, not Streamlit widgets, and all continue from the
# current week, so changing speed doesn't start the animation over.
# The colour scale must be fixed (zmin, zmax), otherwise the same colour would mean different values in each frame
def overview_animation(areas, table, selected=(), title=None, label="Value", value_format=".0%",
                       zmin=0, zmax=1, speeds=PLAY_SPEEDS, height=600, dark=False):
    weeks = table.index
    fig = overview_map(areas, table.iloc[0], selected, title, label, value_format, zmin, zmax, height)

    # The order of the areas in the map, so each frame's values match the right area
    order = areas["area_nr"].tolist()
    names = [f"{week:%Y-%m-%d}" for week in weeks]

    # The week counter: ISO year and week (NVE's own numbering), with the date of the week's Sunday
    def counter(week):
        iso = week.isocalendar()
        return f"{iso.year} : {iso.week:02d}   (week ending {week:%d.%m.%Y})"

    # Each frame only changes the colours (z) of the first layer. The outline layer stays as it is
    fig.frames = [
        go.Frame(name=name, data=[go.Choropleth(z=[row.get(nr) for nr in order])], traces=[0])
        for name, (_, row) in zip(names, table.iterrows())
    ]

    # Every play button continues from the current frame (fromcurrent), so switching speed keeps the place
    def play(frame_ms):
        return dict(frame=dict(duration=frame_ms, redraw=True), fromcurrent=True, transition=dict(duration=0))

    pause = dict(frame=dict(duration=0, redraw=False), mode="immediate", transition=dict(duration=0))
    jump = dict(frame=dict(duration=0, redraw=True), mode="immediate", transition=dict(duration=0))

    # height is the map's own height, as in overview_map. The controls are added below it, so the map has exactly
    # the same size (and zoom) as the static map, and only the figure grows
    _geo_layout(fig, title, height + CONTROLS_HEIGHT, bottom=CONTROLS_HEIGHT)
    colors = CONTROL_COLORS[dark]
    fig.update_layout(
        updatemenus=[dict(
            type="buttons", direction="left", showactive=True, x=0, y=-0.02, xanchor="left", yanchor="top",
            bgcolor=colors["background"], bordercolor=colors["border"], borderwidth=1,
            font=dict(color=colors["text"]), active=-1,
            buttons=[dict(label="Pause", method="animate", args=[[None], pause])]
                    + [dict(label=name, method="animate", args=[None, play(ms)]) for name, ms in speeds.items()],
        )],
        sliders=[dict(
            active=0, x=0.32, len=0.68, y=-0.02, yanchor="top",
            bgcolor=colors["background"], bordercolor=colors["border"], activebgcolor=colors["active"],
            # The week counter above the slider has its own text colour. The slider's tick labels are hidden
            # (one step per week is too many to label), and without its own colour the counter would be hidden too
            currentvalue=dict(prefix="", visible=True, xanchor="left", font=dict(size=15, color=colors["text"])),
            font=dict(color="rgba(0,0,0,0)"), ticklen=0, tickcolor="rgba(0,0,0,0)",
            steps=[dict(label=counter(week), method="animate", args=[[name], jump])
                   for week, name in zip(weeks, names)],
        )],
    )
    return fig