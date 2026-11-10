import pandas as pd
import plotly.express as px
import streamlit as st

from utils.about import reservoir_data_info
from utils.controls import AREA_TYPES, get_global_selection
from utils.data import (
    available_area_numbers, available_dates, load_area_shapes, load_filling_at, load_reservoir_data,
    load_reservoir_period, maps, refresh_data,
)

st.title("Reservoirs")
st.write(
    "Weekly reservoir statistics from NVE. Choose the type of area, the areas and the period in the sidebar. "
    "The map shows the filling degree in one week, the plot compares the areas over time, "
    "and the data tab shows the numbers."
)

# The reservoir data comes straight from NVE's API (every week since 1995, kept for an hour), so nothing has to be
# downloaded. It can only be missing if NVE doesn't answer, and then the answer is to try again
if load_reservoir_data().empty:
    st.warning("The reservoir data could not be fetched from NVE right now.")
    if st.button("Try again", on_click=refresh_data):
        st.rerun()
    st.page_link("pages/page_home.py", label="See the data status on Home")
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
# Map: the filling degree of every area of the chosen type.
# Off: one week, chosen with its own slider (default: the latest, i.e. the current filling degree).
# On ("Play the period"): the period from the sidebar played week by week in the browser.
# The type and the outlined areas come from the sidebar
# ---------------------------------------------------------------------------------------------
with map_tab:
    with st.spinner("Preparing the map (the first time takes a few seconds)..."):
        shapes = load_area_shapes(area_type)

    animate = st.toggle(
        "Play the period", key="reservoirs_map_animate",
        help="Plays the period chosen in the sidebar week by week, with Play and Pause under the map.",
    )

    if animate:
        # One row per week, one column per area: the filling degree of every area of the type, not only the chosen ones
        all_areas = available_area_numbers(area_type)
        period = load_reservoir_period(area_type, all_areas, start, end)
        table = period.pivot_table(index=period.index, columns="area_nr", values="filling_degree")

        if table.empty:
            st.warning("No reservoir data in the chosen period.")
        else:
            fig = maps.overview_animation(
                shapes, table, selected=area_numbers, label="Filling degree",
                title=f"{AREA_TYPES[area_type]}: filling degree, {start:%d.%m.%Y} to {end:%d.%m.%Y}",
            )
            st.plotly_chart(fig, width="stretch")
            st.caption(
                f"{len(table):,} weeks, the period chosen in the sidebar. Press Slow, Normal or Fast under the map "
                "to play, and switch speed while it plays without losing the place. The counter shows the year and "
                "ISO week. The colour scale is fixed at 0 to 100 %, so the same colour means the same filling degree "
                "in every week."
            )

    else:
        weeks = available_dates()

        # Starts on the latest week. If a new week has been published since, it starts there again.
        # Set through session_state before the slider is drawn (not with value=), to avoid Streamlit's
        # warning about a widget getting its value twice
        if st.session_state.get("reservoirs_map_week") not in weeks:
            st.session_state["reservoirs_map_week"] = weeks[-1]
        chosen_week = st.select_slider(
            "Week", options=weeks, key="reservoirs_map_week",
            format_func=lambda date: f"{date:%d.%m.%Y}",
            help="Drag to see the filling degree in any week since 1995. The period in the sidebar doesn't affect this.",
        )

        filling, week = load_filling_at(area_type, chosen_week)
        if filling.empty:
            st.warning(f"No reservoir data for {AREA_TYPES[area_type]} in that week.")
        else:
            map_column, info_column = st.columns([3, 1], gap="large")

            with map_column:
                fig = maps.overview_map(
                    shapes, filling, selected=area_numbers, label="Filling degree", zmin=0, zmax=1,
                    title=f"{AREA_TYPES[area_type]}: filling degree",
                )
                st.plotly_chart(fig, width="stretch")

            # The week and the chosen areas' numbers, to the right of the map
            with info_column:
                iso = week.isocalendar()
                st.markdown(f"**Week ending**\n\n### {week:%d.%m.%Y}")
                st.caption(f"ISO week {iso.week}, {iso.year}")
                if week == pd.Timestamp(weeks[-1]):
                    st.caption("This is the latest published week.")

                that_week = load_reservoir_period(area_type, area_numbers, week, week).set_index("area_nr")
                for area_nr, row in that_week.iterrows():
                    change = row["filling_degree_change"]
                    st.metric(
                        f"{area_type} {area_nr}",
                        f"{row['filling_degree']:.0%}",
                        delta=f"{change * 100:+.1f} pp from last week" if pd.notna(change) else None,
                    )

            st.caption("The areas chosen in the sidebar are outlined in orange, and their numbers are shown to the right.")


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

reservoir_data_info()