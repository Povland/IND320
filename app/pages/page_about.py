import streamlit as st

from utils import about

st.title("About the data and the project")
about.author()

st.header("Three data sources")
about.reservoir_source()
about.crossborder_source()
about.weather_source()

st.header("How they fit together")
about.how_they_fit()

st.header("The pipeline")
about.pipeline()

st.header("Methods")
about.seasonal_methods()
about.anomaly_methods()

st.header("Areas in the data")
about.areas_table()

st.header("Column names")
about.column_names()

st.header("Known limitations")
st.subheader("Reservoir data")
about.reservoir_limitations()
st.subheader("Cross-border flow")
about.crossborder_limitations()
st.subheader("Weather")
about.weather_limitations()

st.header("Links")
about.links()

st.header("Tech stack")
about.tech_stack()