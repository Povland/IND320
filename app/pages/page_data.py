import pandas as pd
import streamlit as st

from utils.controls import AREA_TYPES, get_global_selection
from utils.about import reservoir_data_info
from utils.data import load_reservoir_period
from utils.data import available_area_numbers, available_dates, load_reservoir_data, load_reservoir_period

st.title("Reservoir Data")
st.write(
    "Weekly reservoir statistics from NVE. Choose the type of area, the areas and the period in the sidebar. "
    "Each row is one area, and each chart shows how the value developed over the chosen period."
)

# The global selection from the sidebar (drawn by streamlit_app.py, shared with the other pages)
selection = get_global_selection()
area_type, area_numbers = selection["area_type"], selection["area_numbers"]
start, end = selection["start"], selection["end"]

if not area_numbers:
    st.info("No areas selected. Choose one or more areas in the sidebar.")
    st.stop()

data = load_reservoir_period(area_type, area_numbers, start, end)

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