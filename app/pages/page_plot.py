import plotly.express as px
import streamlit as st

from utils.controls import AREA_TYPES, get_global_selection
from utils.about import reservoir_data_info
from utils.data import load_reservoir_period
from utils.data import available_area_numbers, available_dates, load_reservoir_data, load_reservoir_period

st.title("Reservoir Plot")
st.write(
    "Compare the areas over time. Choose the type of area, the areas and the period in the sidebar, "
    "and which variable to plot below. Each line is one area."
)

# The global selection from the sidebar (drawn by streamlit_app.py, shared with the other pages)
selection = get_global_selection()
area_type, area_numbers = selection["area_type"], selection["area_numbers"]
start, end = selection["start"], selection["end"]

if not area_numbers:
    st.info("No areas selected. Choose one or more areas in the sidebar.")
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

reservoir_data_info()