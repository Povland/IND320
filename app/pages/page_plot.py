import streamlit as st
import plotly.express as px

from utils.data import load_reservoir_data

st.title("Reservoir Data Plot")
st.write("This page allows you to visualize reservoir data through interactive plots.")

# Load the reservoir data
reservoir_data = load_reservoir_data()

if reservoir_data.empty:
    st.warning("Reservoir data is not available. Please check the data source.")
    st.stop()

# Select column to plot
columns = reservoir_data.columns.tolist()
selected_column = st.selectbox(
    "Select a column to plot:",
    ["All columns"] + columns
    )

# Select end date for the plot
dates = reservoir_data.index.tolist()
selected_date = st.select_slider(
    "Select a date range for the plot:",
    options = dates,
    value = dates[0],
    format_func = lambda date: date.strftime("%Y-%m-%d")
)

plot_data = reservoir_data.loc[
    reservoir_data.index <= selected_date
]

# Create the plot
if selected_column == "All columns":
    fig = px.line(
        plot_data,
        x=plot_data.index,
        y=plot_data.columns,
        title="Reservoir Data Over Time",
        labels={"x": "Date", "y": "Value"},
    )

else:
    fig = px.line(
        plot_data,
        x=plot_data.index,
        y=selected_column,
        title=f"{selected_column} Over Time",
        labels={"x": "Date", "y": selected_column},
    )

# Display the plot
st.plotly_chart(fig, use_container_width=True)