import pandas as pd
import streamlit as st

from utils.controls import AREA_TYPES, area_number_selector, area_type_selector, period_selector
from utils.data import available_area_numbers, available_dates, load_reservoir_data, load_reservoir_period

st.title("Reservoir Data")
st.write(
    "Weekly reservoir statistics from NVE. Choose the type of area and the period. "
    "Each row is one area, and each chart shows how the value developed over the chosen period."
)

if load_reservoir_data().empty:
    st.warning("Reservoir data is not available. Please check the data source.")
    st.stop()

# Controls at the top of the page (shared with the Plot page). Area type and areas on the left, period on the right
left, right = st.columns([1, 2])
with left:
    area_type = area_type_selector("data")
    area_numbers = area_number_selector("data", area_type, available_area_numbers(area_type))
with right:
    start, end = period_selector("data", available_dates())

if not area_numbers:
    st.info("No areas selected. Choose one or more areas above.")
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