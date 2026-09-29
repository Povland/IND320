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

# Get numeric columns
plot_columns = [
    "filling_degree",
    "capacity_TWh",
    "filling_TWh",
    "filling_degree_last_week",
    "filling_degree_change"
]

# Select column to plot
selected_column = st.selectbox(
    "Select a column to plot:",
    ["All columns"] + plot_columns
    )

# Select period for the plot
dates = reservoir_data.index.tolist()
selected_period = st.select_slider(
    "Select a date range for the plot:",
    options = dates,
    value = (dates[0], dates[-1]),
    format_func = lambda date: date.strftime("%Y-%m-%d")
)
start_date, end_date = selected_period

# Filter the data based on the selected period
plot_data = reservoir_data.loc[
    start_date:end_date,
    plot_columns
]

# Create the plot
if selected_column == "All columns":
    fig = px.line(
        plot_data,
        x=plot_data.index,
        y=plot_columns,
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
st.plotly_chart(
    fig, 
    use_container_width=True
    )