import streamlit as st
import pandas as pd

from app.utils.data import load_reservoir_data

st.title("Reservoir Data")
st.write("This is the data page for visualizing reservoir information.")

reservoir_data = load_reservoir_data()
if reservoir_data.empty:
    st.warning("Reservoir data is not available. Please check the data source.")
    st.stop()

# Creates a dataframe to display the overview of the reservoir data
overview_data = {
    "Column": reservoir_data.columns,
    "Data": []
}
for column in reservoir_data.columns:
    overview_data["Data"].append(
        reservoir_data[column].to_list()
        )

# Display the overview data in a table format
st.dataframe(
    overview_data,
    use_container_width=True,
    column_config={
        "Column": st.column_config.LineChartColumn(
            "Column",
            help="The name of the column in the reservoir data.", #hovering gives a description of the column
        ),
        "Data": st.column_config.LineChartColumn(
            "Data",
            help="The data contained in the column.",
        ),
    }
)