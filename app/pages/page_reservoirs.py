import pandas as pd
import plotly.express as px
import streamlit as st

from utils.about import reservoir_data_info
from utils.controls import AREA_TYPES, get_global_selection
from utils.data import (
    available_area_numbers, load_animation_shapes, load_reservoir_data, load_reservoir_period, maps, refresh_data,
)
from utils.updates import reservoir_panel

st.title("Reservoirs")
st.write(
    "Weekly reservoir statistics from NVE. Choose the type of area, the areas and the period in the sidebar. "
    "The map plays the filling degree week by week, the plot compares the areas over time, "
    "and the data tab shows the numbers."
)

# The reservoir data comes straight from NVE's API (every week since 1995, kept for an hour), so nothing has to be
# downloaded. It can only be missing if NVE doesn't answer, and then the answer is to try again
if load_reservoir_data().empty:
    st.warning("The reservoir data could not be fetched from NVE right now.")
    if st.button("Try again", on_click=refresh_data):
        st.rerun()
        st.page_link("pages/page_data_status.py", label="See Data status")
    st.stop()

# The global selection from the sidebar (drawn by streamlit_app.py, shared with the other pages)
selection = get_global_selection()
area_type, area_numbers = selection["area_type"], selection["area_numbers"]
start, end = selection["start"], selection["end"]

if not area_numbers:
    st.info("No areas selected. Choose one or more areas in the sidebar.")
    st.stop()

# Loaded once and used by both the plot and the data tab (Streamlit draws every tab on each run)
data = load_reservoir_period(area_type, area_numbers, start, end)

map_tab, plot_tab, data_tab = st.tabs(["Map", "Plot", "Data"])

# ---------------------------------------------------------------------------------------------
# Map: the filling degree of every area of the chosen type, week by week over the period from the sidebar.
# One map where dragging the slider and playing both happen in the browser, so the map changes without Streamlit
# redrawing the page. Coarse outlines and a choice of step keep it smooth. The chosen areas are outlined in orange
# ---------------------------------------------------------------------------------------------
with map_tab:
    with st.spinner("Preparing the map (the first time takes a few seconds)..."):
        shapes = load_animation_shapes(area_type)

    # One row per week, one column per area: the filling degree of every area of the type, not only the chosen ones
    all_areas = available_area_numbers(area_type)
    period = load_reservoir_period(area_type, all_areas, start, end)
    table = period.pivot_table(index=period.index, columns="area_nr", values="filling_degree")

    STEPS = {1: "Every week", 4: "Every 4 weeks", 13: "Every 13 weeks"}
    step = st.radio("Show", list(STEPS), index=1, format_func=STEPS.get, horizontal=True, key="reservoirs_map_step",
                    help="Fewer weeks make a long period play faster. The latest week is always included.")

    if table.empty:
        st.warning("No reservoir data in the chosen period.")
    else:
        # Every step-th week, counted back from the last one, so the latest week is always a frame
        frames = table.iloc[::-1].iloc[::step].iloc[::-1]

        map_column, info_column = st.columns([3, 1], gap="large")
        with map_column:
            dark = st.context.theme.type == "dark"
            fig = maps.overview_animation(
                shapes, frames, selected=area_numbers, label="Filling degree", dark=dark,
                title=f"{AREA_TYPES[area_type]}: filling degree, {start:%d.%m.%Y} to {end:%d.%m.%Y}",
            )
            st.plotly_chart(fig, width="stretch", key="reservoirs_map")

        # The period and how much the chosen areas changed over it. The week shown on the map is only known in the
        # browser, so the exact value for each week is in the hover
        with info_column:
            st.markdown(f"**Period**\n\n### {len(table):,} weeks")
            st.caption(f"{table.index[0]:%d.%m.%Y} to {table.index[-1]:%d.%m.%Y}, {len(frames):,} shown on the map")
            for area_nr in area_numbers:
                values = table[area_nr].dropna() if area_nr in table else pd.Series(dtype=float)
                if values.empty:
                    continue
                st.metric(
                    f"{area_type} {area_nr}, last week",
                    f"{values.iloc[-1]:.0%}",
                    delta=f"{(values.iloc[-1] - values.iloc[0]) * 100:+.1f} pp over the period",
                )

        st.caption(
            "Drag the slider under the map to move through the weeks, or press Slow, Normal or Fast to play from "
            "where the slider is. From start plays the whole period. It all happens in the browser, so the map "
            "doesn't reload. The counter shows the ISO year and week. The colour scale is fixed at 0 to 100 %, so "
            "the same colour means the same filling degree in every week. The chosen areas are outlined in orange."
        )

# ---------------------------------------------------------------------------------------------
# Plot: one line per area for the chosen variable (was the Reservoir Plot page)
# ---------------------------------------------------------------------------------------------
with plot_tab:
    # The variables that can be plotted, with readable names
    PLOT_COLUMNS = {
        "filling_degree": "Filling degree",
        "filling_TWh": "Filling (TWh)",
        "capacity_TWh": "Capacity (TWh)",
        "filling_degree_last_week": "Filling degree last week",
        "filling_degree_change": "Change from last week",
    }
    selected_column = st.selectbox("Variable:", options=list(PLOT_COLUMNS), format_func=PLOT_COLUMNS.get,
                                   key="reservoirs_plot_variable")

    # One line per area: the area label is used as colour in the plot
    plot_data = data.reset_index()
    plot_data["area"] = area_type + " " + plot_data["area_nr"].astype(str)

    fig = px.line(
        plot_data,
        x="date_id",
        y=selected_column,
        color="area",
        title=f"{PLOT_COLUMNS[selected_column]}, {AREA_TYPES[area_type]}",
        labels={"date_id": "Date", selected_column: PLOT_COLUMNS[selected_column], "area": "Area"},
    )
    st.plotly_chart(fig, width="stretch")

# ---------------------------------------------------------------------------------------------
# Data: one row per area with line charts, and the numbers as a table (was the Reservoir Data page)
# ---------------------------------------------------------------------------------------------
with data_tab:
    # The columns shown as line charts, with readable names
    CHART_COLUMNS = {
        "filling_degree": "Filling degree",
        "filling_TWh": "Filling (TWh)",
        "capacity_TWh": "Capacity (TWh)",
        "filling_degree_change": "Change from last week",
    }

    # One row per area number, where each cell holds the values over time for one variable
    rows = []
    for area_nr, area_data in data.groupby("area_nr"):
        row = {"Area": f"{area_type} {area_nr}"}
        for column in CHART_COLUMNS:
            row[column] = area_data[column].tolist()
        rows.append(row)

    st.subheader(f"{AREA_TYPES[area_type]}, {start:%Y-%m-%d} to {end:%Y-%m-%d}")
    st.dataframe(
        pd.DataFrame(rows),
        width="stretch",
        hide_index=True,
        column_config={
            "Area": st.column_config.TextColumn("Area"),
            **{
                column: st.column_config.LineChartColumn(label, help=f"{label} per week in the chosen period.")
                for column, label in CHART_COLUMNS.items()
            },
        },
    )

    # The underlying numbers, for those who want to look closer
    with st.expander("Show the data as a table"):
        st.dataframe(data, width="stretch")

# Checks whether NVE has published a newer week than the one in the app's cache, and fetches it
reservoir_panel("reservoirs")

reservoir_data_info()