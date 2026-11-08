import streamlit as st
from utils.data import FLOWS_COLLECTION, run_connection_test

st.title("Reservoir dashboard")
st.header("Home")
st.write("This is a dashboard for visualizing reservoir data." )


st.subheader("Pages:")
st.markdown("""
- *Reservoir Data*: View imported data. One row per area, with line charts for each variable.
- *Reservoir Plot*: Compare the areas over time in one plot.
- *Cross-border flow*: Power flows between Norway and its neighbours (ENTSO-E, from MongoDB).
""")


st.info("This dashboard is a work in progress. More features will be added in the future.")

# Shows the result of the last connection test to MongoDB, where the curated data from the notebook is stored.
# The test runs when the page is loaded (streamlit_app.py), and again when the button is clicked.
# The button uses on_click, so the new test runs before the page is drawn and the new result is shown right away
status = st.session_state["mongo_status"]

with st.expander("Database connection", expanded=not status["connected"]):   # opens by itself if the test failed
    button_column, box_column = st.columns([1, 3], vertical_alignment="center")

    with button_column:
        # kwargs passes manual=True to run_connection_test, so the result remembers that it was a manual test.
        # st.button returns True in the run right after it was clicked, so the toast only shows after a manual test
        if st.button("Test connection", on_click=run_connection_test, kwargs={"manual": True}):
            if status["connected"]:
                st.toast(f"Connection tested: {tested_at}. Connected.", icon="✅")
            else:
                st.toast(f"Connection tested: {tested_at}. Not connected.", icon="❌")

    # Box to the right of the button, shown as long as the last test was a manual one (gone after a reload)
    with box_column:
        if status["manual"]:
            if status["connected"]:
                st.success(f"Manually tested: {tested_at}. Connected.")
            else:
                st.error(f"Manually tested: {tested_at}. Not connected.")