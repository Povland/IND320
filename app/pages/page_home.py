import pandas as pd
import streamlit as st

from utils.controls import area_type_selector, select_area
from utils.data import available_dates, load_area_shapes, load_filling_at, load_weekly_weather, maps, weather

st.title("Reservoirs, power flow and weather")
st.write("A dashboard for Norway's hydropower reservoirs, the power flow to and from the neighbouring countries, "
         "and the weather over the price and watercourse areas.")

# If the database didn't answer when the app was loaded, say so on the front page, with a link to the details
if not st.session_state["mongo_status"]["connected"]:
    st.warning("Not connected to MongoDB, so the weather and cross-border data can't be read.")
    st.page_link("pages/page_data_status.py", label="See Data status")


# ---------------------------------------------------------------------------------------------
# The main map: the areas of one type, coloured by the filling degree or a weather property in the chosen week,
# and a click on an area selects it for the other pages
# ---------------------------------------------------------------------------------------------
st.subheader("Map")

# The weather variables, how they are shown, and the colours. Temperature is a mean over the period, the rest sums
WEATHER_VARIABLES = {
    "temperature_2m": ("Temperature", "°C", ".1f", "RdBu_r"),
    "precipitation": ("Precipitation", "mm", ".0f", "Blues"),
    "rain": ("Rain", "mm", ".0f", "Blues"),
    "snowfall": ("Snowfall", "cm", ".0f", "Purples"),
    "et0_fao_evapotranspiration": ("Evaporation", "mm", ".0f", "Oranges"),
}
PERIODS = {1: "1 week", 4: "4 weeks", 13: "13 weeks (a quarter)", 26: "26 weeks", 52: "52 weeks (a year)"}

left, middle, right = st.columns(3)
with left:
    # The same type of area as the sidebar on the other pages (the global choice)
    area_type = area_type_selector("home", horizontal=False)
with middle:
    # No weather for all of Norway, so NO can only be coloured by the filling degree
    colour_options = ["Filling degree"] if area_type == "NO" else ["Filling degree", "Weather"]
    colour_by = st.radio("Colour by", colour_options, key="home_colour_by")
with right:
    if colour_by == "Weather":
        variable = st.selectbox("Weather property", list(WEATHER_VARIABLES),
                                format_func=lambda v: WEATHER_VARIABLES[v][0], key="home_weather_variable")
        n_weeks = st.selectbox("Over the last", list(PERIODS), index=1, format_func=PERIODS.get,
                               key="home_weather_weeks", help="The weather is aggregated over this many weeks, "
                               "ending in the chosen week: temperature as a mean, the rest as a sum.")

# The week: shared with the Forecast page (its last week of training) through st.session_state["selected_week"].
# Starts on the latest published week
weeks = available_dates()
if st.session_state.get("home_week") not in weeks:
    shared_week = st.session_state.get("selected_week")
    st.session_state["home_week"] = shared_week if shared_week in weeks else weeks[-1]


def share_week():
    st.session_state["selected_week"] = st.session_state["home_week"]


week = st.select_slider("Week", options=weeks, key="home_week", on_change=share_week,
                        format_func=lambda date: f"{date:%d.%m.%Y}",
                        help="Any week since 1995. Shared with the Forecast page.")

# The values to colour by: one per area of the type
shapes = load_area_shapes(area_type)
area_numbers = shapes["area_nr"].tolist()

if colour_by == "Filling degree":
    values, shown_week = load_filling_at(area_type, week)
    label, value_format, colorscale, zmin, zmax = "Filling degree", ".0%", "Blues", 0, 1
    caption = f"Filling degree in the week ending {shown_week:%d.%m.%Y}." if shown_week is not None else ""
else:
    name, unit, value_format, colorscale = WEATHER_VARIABLES[variable]
    how = weather.WEEKLY_AGGREGATION[variable]
    period_end = pd.Timestamp(week)
    period_start = period_end - pd.Timedelta(weeks=n_weeks - 1)

    # Only areas with every week of the period stored get a value. The others are drawn as outlines only
    values = {}
    for area_nr in area_numbers:
        weekly = load_weekly_weather(area_type, area_nr)
        if weekly.empty or variable not in weekly:
            continue
        period = weekly.loc[period_start:period_end, variable]
        if len(period) == n_weeks and period.notna().all():
            values[area_nr] = period.mean() if how == "mean" else period.sum()

    label = f"{name} ({unit})"
    zmin = zmax = None
    caption = (f"{name}, {'mean' if how == 'mean' else 'sum'} over the {PERIODS[n_weeks]} ending "
               f"{period_end:%d.%m.%Y}.")
    if len(values) < len(area_numbers):
        caption += (" Areas without colour have no weather stored for the whole period "
                    "(see Data status for what is stored).")

# The selected area, if it is of the type shown
selected = st.session_state.get("selected_area")
selected_nr = selected[1] if selected and selected[0] == area_type else None

map_column, info_column = st.columns([3, 1], gap="large")

with map_column:
    dark = st.context.theme.type == "dark"
    fig = maps.selection_map(shapes, values, selected=selected_nr, label=label, value_format=value_format,
                             colorscale=colorscale, zmin=zmin, zmax=zmax, dark=dark)
    event = st.plotly_chart(fig, width="stretch", on_select="rerun", selection_mode="points",
                            key=f"home_map_{area_type}")
    st.caption(caption + " Click an area to select it for the other pages.")

# A click: the clicked area's id (e.g. "EL 3") is in "location". Streamlit keeps the selection between reruns,
# so a click is only used once (compared with the last one used). An empty selection resets it,
# so the same area can be clicked again after choosing another one in the dropdown
points = event.selection.points if event and event.selection else []
clicked = points[0].get("location") if points else None
if clicked is None:
    st.session_state["home_map_last_click"] = None
elif clicked != st.session_state.get("home_map_last_click"):
    st.session_state["home_map_last_click"] = clicked
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


# ---------------------------------------------------------------------------------------------
# The pages, grouped as in the sidebar. st.page_link gives clickable links to the pages
# ---------------------------------------------------------------------------------------------
st.subheader("Pages")
explore, anomalies, predict = st.columns(3)

with explore:
    st.markdown("**Explore**")
    st.page_link("pages/page_reservoirs.py", label="Reservoirs")
    st.page_link("pages/page_seasonal.py", label="Seasonality & Spectrum")
    st.page_link("pages/page_cross_border.py", label="Cross-border flow")
    st.page_link("pages/page_currency.py", label="Currency")

with anomalies:
    st.markdown("**Anomalies**")
    st.page_link("pages/page_weather.py", label="Weather Outliers")

with predict:
    st.markdown("**Predict**")
    st.page_link("pages/page_correlation.py", label="Weather vs reservoirs")
    st.page_link("pages/page_forecast.py", label="Forecast")

st.caption("The type of area, the areas and the period are chosen in the sidebar on the pages that use them, "
           "and are shared between those pages. Data status and About are at the bottom of the menu.")