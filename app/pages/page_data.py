import pandas as pd
import streamlit as st

from utils.data import load_reservoir_data

st.title("Reservoir Data")
st.write("Weekly reservoir statistics from NVE's API. One row per variable, showing the first month of data.")

reservoir_data = load_reservoir_data()
if reservoir_data.empty:
    st.warning("Reservoir data is not available. Please check the data source.")
    st.stop()

# Choose area, since each date has one row per area
areas = (
    reservoir_data[["area_type", "area_nr"]]
    .drop_duplicates()
    .sort_values(["area_type", "area_nr"])
)
area_labels = [f"{t} {n}" for t, n in areas.itertuples(index=False)]
selected_area = st.selectbox("Area:", area_labels)
area_type, area_nr = selected_area.split()

area_data = reservoir_data[
    (reservoir_data["area_type"] == area_type)
    & (reservoir_data["area_nr"] == int(area_nr))
]

# First month of data for the selected area
first_date = area_data.index.min()
first_month = area_data.loc[first_date : first_date + pd.DateOffset(months=1)]

# Only numeric columns can be drawn as line charts
numeric_columns = first_month.select_dtypes("number").columns.drop(["area_nr", "iso_aar", "iso_week"])

overview = pd.DataFrame({
    "Column": numeric_columns,
    "Data": [first_month[column].tolist() for column in numeric_columns],
})

st.dataframe(
    overview,
    width="stretch",
    hide_index=True,
    column_config={
        "Column": st.column_config.TextColumn(
            "Column",
            help="The name of the column in the reservoir data.",
        ),
        "Data": st.column_config.LineChartColumn(
            "Data",
            help=f"Values from {first_date:%Y-%m-%d} and one month ahead.",
        ),
    },
)