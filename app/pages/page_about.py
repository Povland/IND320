import streamlit as st

from utils import about
from utils.version import show_version

st.title("About the data and the project")
about.author()
show_version()

st.header("Two data sources")
about.reservoir_source()
about.crossborder_source()

st.header("How the two fit together")
about.how_they_fit()

st.header("The pipeline")
about.pipeline()

st.header("Areas in the data")
about.areas_table()

st.header("Column names")
about.column_names()

st.header("Known limitations")
st.subheader("Reservoir data")
about.reservoir_limitations()
st.subheader("Cross-border flow")
about.crossborder_limitations()

st.header("Links")
about.links()

st.header("Tech stack")
about.tech_stack()