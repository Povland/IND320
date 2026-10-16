import streamlit as st
import random
from utils.data import check_mongo_connection

st.title("Reservoir dashboard")
st.header("Home")
st.write("This is a dashboard for visualizing reservoir data." )


st.subheader("Pages:")
st.markdown("""
- *Data*: View imported data. One row per area, with line charts for each variable.
- *Plot*: Compare the areas over time in one plot.
- *Cross border*: Power flows between Norway and its neighbours (ENTSO-E, from MongoDB).
""")

st.info("This dashboard is a work in progress. More features will be added in the future.")

# Shows whether the app can reach MongoDB, where the curated data from the notebook is stored
with st.expander("Database connection"):
    connected, details = check_mongo_connection()
    if connected:
        st.success("Connected to MongoDB.")
        st.write("Collections:", details if details else "none yet")
    else:
        st.error(f"Could not connect to MongoDB: {details}")