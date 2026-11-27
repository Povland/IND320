import pandas as pd
import streamlit as st

from utils.controls import area_type_selector, select_area
from utils.data import (
    available_dates, load_area_shapes, load_filling_at, load_flow_period, load_weekly_flows, load_weekly_weather,
    maps, weather,
)

st.title("Map of Norway")
st.write(
    "The areas of one type, coloured by the filling degree or a weather property in the chosen week. "
    "Click an area to select it: the other pages start from the selected area."
)

# The weather variables, how they are shown, and the colours. Temperature is a mean over the period, the rest sums
WEATHER_VARIABLES = {
    "temperature_2m": ("Temperature", "°C", ".1f", "RdBu_r"),
    "precipitation": ("Precipitation", "mm", ".0f", "Blues"),
    "rain": ("Rain", "mm", ".0f", "Blues"),
    "snowfall": ("Snowfall", "cm", ".0f", "Purples"),
    "et0_fao_evapotranspiration": ("Evaporation", "mm", ".0f", "Oranges"),
}
PERIODS = {1: "1 week", 4: "4 weeks", 13: "13 weeks (a quarter)", 26: "26 weeks", 52: "52 weeks (a year)"}

# ---------------------------------------------------------------------------------------------
# Controls: the type of area (the global choice), what to colour by, and for the weather: the property and period
# ---------------------------------------------------------------------------------------------
# What the cross-border flow covers, for the help icon next to the toggle. Only read when the database is connected
connected = st.session_state["mongo_status"]["connected"]
flow_period = None
if connected:
    try:
        flow_period = load_flow_period()
    except Exception:
        flow_period = None

if flow_period:
    (first_year, first_month), (last_year, last_month) = flow_period
    flow_help = (f"The net power flow to and from the neighbouring countries in the chosen week (ENTSO-E, hourly, "
                 f"stored in MongoDB). Stored from {first_month:02d}.{first_year} to {last_month:02d}.{last_year}. "
                 "Newer data can be fetched on the Cross-border flow page. The positions of the arrows are approximate.")
elif connected:
    flow_help = "No cross-border flow is stored yet. It can be fetched on the Cross-border flow page."
else:
    flow_help = "Not connected to MongoDB, so the cross-border flow can't be read."

type_column, colour_column, flow_column, weather_column = st.columns(4)
with type_column:
    area_type = area_type_selector("map", horizontal=False)
with colour_column:
    # No weather for all of Norway, so NO can only be coloured by the filling degree
    colour_options = ["Filling degree"] if area_type == "NO" else ["Filling degree", "Weather"]
    colour_by = st.radio("Colour by", colour_options, key="map_colour_by")
with flow_column:
    show_flow = st.toggle("Show cross-border flow", key="map_show_flow", help=flow_help, disabled=not connected)
    # Filled in further down, once the week is known: a note if the week has no flow
    flow_note = st.empty()
with weather_column:
    if colour_by == "Weather":
        variable = st.selectbox("Weather property", list(WEATHER_VARIABLES),
                                format_func=lambda v: WEATHER_VARIABLES[v][0], key="map_weather_variable")
        n_weeks = st.selectbox("Over the last", list(PERIODS), index=1, format_func=PERIODS.get,
                               key="map_weather_weeks", help="The weather is aggregated over this many weeks, "
                               "ending in the chosen week: temperature as a mean, the rest as a sum.")

shapes = load_area_shapes(area_type)
area_numbers = shapes["area_nr"].tolist()


# The week slider. The chosen week is shared with the Forecast page (its last week of training) through
# st.session_state["selected_week"], but only when the user moves the slider, so switching between filling degree
# and weather (which offer different weeks) doesn't change the Forecast page by itself
def share_week(widget_key):
    st.session_state["selected_week"] = st.session_state[widget_key]


def week_slider(widget_key, options, help_text):
    if st.session_state.get(widget_key) not in options:
        shared_week = st.session_state.get("selected_week")
        st.session_state[widget_key] = shared_week if shared_week in options else options[-1]
    return st.select_slider("Week", options=options, key=widget_key, on_change=share_week, args=(widget_key,),
                            format_func=lambda date: f"{date:%d.%m.%Y}", help=help_text)


# ---------------------------------------------------------------------------------------------
# The values to colour by, one per area, and a fixed colour scale
# ---------------------------------------------------------------------------------------------
if colour_by == "Filling degree":
    week = week_slider("map_week", available_dates(), "Any week since 1995. Shared with the Forecast page.")
    values, shown_week = load_filling_at(area_type, week)
    label, value_format, colorscale, zmin, zmax, unit = "Filling degree", ".0%", "Blues", 0, 1, ""
    caption = f"Filling degree in the week ending {shown_week:%d.%m.%Y}." if shown_week is not None else ""

else:
    name, unit, value_format, colorscale = WEATHER_VARIABLES[variable]
    how = weather.WEEKLY_AGGREGATION[variable]

    # Each area's weekly weather aggregated over the last n_weeks (a rolling mean or sum), so every stored week has
    # a value. One column per area, one row per week
    aggregated = {}
    for area_nr in area_numbers:
        weekly = load_weekly_weather(area_type, area_nr)
        if weekly.empty or variable not in weekly:
            continue
        rolling = weekly[variable].asfreq("W-SUN").rolling(n_weeks, min_periods=n_weeks)
        aggregated[area_nr] = rolling.mean() if how == "mean" else rolling.sum()
    table = pd.DataFrame(aggregated).dropna(how="all")

    if table.empty:
        st.warning("No weather is stored for these areas yet.")
        st.page_link("pages/page_data_status.py", label="Download weather on Data status")
        st.stop()

    # Only the weeks with weather stored can be chosen
    weather_weeks = [timestamp.date() for timestamp in table.index]
    week = week_slider("map_weather_week", weather_weeks,
                       f"Only the weeks with weather stored ({weather_weeks[0]:%d.%m.%Y} to "
                       f"{weather_weeks[-1]:%d.%m.%Y}). Shared with the Forecast page.")
    values = table.loc[pd.Timestamp(week)].dropna().to_dict()

    # A colour scale fixed over every stored week and area, so the same colour means the same value in every week.
    # Temperature is centred on 0 °C (blue below freezing, red above), the amounts start at 0
    low, high = table.min().min(), table.max().max()
    if variable == "temperature_2m":
        limit = max(abs(low), abs(high))
        zmin, zmax = -limit, limit
    else:
        zmin, zmax = 0, high

    label = f"{name} ({unit})"
    caption = (f"{name}, {'mean' if how == 'mean' else 'sum'} over the {PERIODS[n_weeks]} ending {week:%d.%m.%Y}. "
               f"Weather is stored from {weather_weeks[0]:%d.%m.%Y} to {weather_weeks[-1]:%d.%m.%Y}, and the "
               "colour scale is the same for all those weeks.")
    if len(values) < len(area_numbers):
        caption += " Areas without colour have no weather stored for this week."


# ---------------------------------------------------------------------------------------------
# Cross-border flow in the chosen week, for the arrows on the map. A small note under the toggle if the week has none
# ---------------------------------------------------------------------------------------------
flows = pd.DataFrame()
if show_flow and connected:
    try:
        flows = load_weekly_flows(week)
    except Exception as error:
        flow_note.error(f"Could not read the cross-border flow: {error}")
    else:
        if flows.empty:
            flow_note.info(f"No cross-border flow for the week ending {week:%d.%m.%Y}.")

# ---------------------------------------------------------------------------------------------
# The map, and the selected area next to it
# ---------------------------------------------------------------------------------------------
selected = st.session_state.get("selected_area")
selected_nr = selected[1] if selected and selected[0] == area_type else None

map_column, info_column = st.columns([3, 1], gap="large")

with map_column:
    dark = st.context.theme.type == "dark"
    fig = maps.selection_map(shapes, values, selected=selected_nr, label=label, value_format=value_format,
                             colorscale=colorscale, zmin=zmin, zmax=zmax, dark=dark)
    fig = maps.add_flow_arrows(fig, flows, dark=dark)
    event = st.plotly_chart(fig, width="stretch", on_select="rerun", selection_mode="points",
                            key=f"map_chart_{area_type}")
    st.caption(caption + " Click an area to select it for the other pages.")
    if not flows.empty:
        st.caption("Arrows: the net cross-border flow in the week. Orange is net export (out of Norway), purple net "
                   "import, and the thicker the line, the more power. The positions are approximate.")
        with st.expander("The flow per connection this week"):
            table = flows.set_index("connection")[["out_gwh", "in_gwh", "net_gwh"]]
            table.columns = ["Out of Norway (GWh)", "Into Norway (GWh)", "Net (GWh)"]
            st.dataframe(table.style.format("{:,.0f}"), width="stretch")

# A click: the clicked area's id (e.g. "EL 3") is in "location". Streamlit keeps the selection between reruns,
# so a click is only used once (compared with the last one used). An empty selection resets it,
# so the same area can be clicked again after choosing another one in the dropdown
points = event.selection.points if event and event.selection else []
clicked = points[0].get("location") if points else None
if clicked is None:
    st.session_state["map_last_click"] = None
elif clicked != st.session_state.get("map_last_click"):
    st.session_state["map_last_click"] = clicked
    clicked_type, clicked_nr = clicked.split()
    select_area(clicked_type, int(clicked_nr))
    st.rerun()

with info_column:
    # The same choice as a click, for those who prefer a list (or if a click doesn't register)
    choice = st.selectbox(
        "Selected area", options=area_numbers, format_func=lambda nr: f"{area_type} {nr}",
        index=area_numbers.index(selected_nr) if selected_nr in area_numbers else None,
        placeholder="Click the map or choose here",
    )
    if choice is not None and choice != selected_nr:
        select_area(area_type, choice)
        st.rerun()

    if selected_nr is not None:
        # .get works the same for the filling degree (a Series) and the weather (a dict)
        value = values.get(selected_nr)
        if value is not None and pd.notna(value):
            shown = f"{value:.0%}" if colour_by == "Filling degree" else f"{value:{value_format}} {unit}"
            st.metric(f"{area_type} {selected_nr}: {label.split(' (')[0].lower()}", shown)
        st.caption("Used as the starting area on the other pages.")
        st.page_link("pages/page_forecast.py", label="Forecast this area")
        st.page_link("pages/page_reservoirs.py", label="Reservoirs over time")
        st.page_link("pages/page_correlation.py", label="Weather vs reservoirs")