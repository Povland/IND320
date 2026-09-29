import streamlit as st
import random

st.title("Reservoir dashboard")
st.header("Home")
st.write("This is a dashboard for visualizing reservoir data." )


st.subheader("Pages:")
st.markdown("""
- *Data*: View imported data.
- *Plot*: Explore the reservoir data.
- *Test*: Placeholder.
""")

st.info("This dashboard is a work in progress. More features will be added in the future.")