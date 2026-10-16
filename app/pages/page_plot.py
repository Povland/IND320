import plotly.express as px
import streamlit as st

from utils.controls import AREA_TYPES, area_number_selector, area_type_selector, period_selector
from utils.data import available_area_numbers, available_dates, load_reservoir_data, load_reservoir_period

st.title("Reservoir Data Plot")
st.write(
    "Compare the areas over time. Choose the type of area and the period, and which variable to plot below. Each line is one area."
)

if load_reservoir_data().empty:
    st.warning("Reservoir data is not available. Please check the data source.")
    st.stop()

# Controls at the top of the page (shared with the Data page) Area type and areas on the left, period on the right
left, right = st.columns([1, 2])
with left:
    area_type = area_type_selector("plot")
    area_numbers = area_number_selector("plot", area_type, available_area_numbers(area_type))
with right:
    start, end = period_selector("plot", available_dates())

if not area_numbers:
    st.info("No areas selected. Choose one or more areas above.")
    st.stop()

# The variables that can be plotted, with readable names
PLOT_COLUMNS = {
    "filling_degree": "Filling degree",
    "filling_TWh": "Filling (TWh)",
    "capacity_TWh": "Capacity (TWh)",
    "filling_degree_last_week": "Filling degree last week",
    "filling_degree_change": "Change from last week",
}
selected_column = st.selectbox("Variable:", options=list(PLOT_COLUMNS), format_func=PLOT_COLUMNS.get)

data = load_reservoir_period(area_type, area_numbers, start, end)

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