import streamlit as st
import random

st.title("Reservoir dashboard")
st.header("Home")
st.write("This is a dashboard for visualizing reservoir data." )


st.subheader("Pages:")
st.markdown("""
- *Data*: View imported data. One row per area, with line charts for each variable.
- *Plot*: Compare the areas over time in one plot.
- *Test*: Placeholder.
""")

st.info("This dashboard is a work in progress. More features will be added in the future.")