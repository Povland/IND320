import streamlit as st

from utils.data import run_connection_test
from utils.about import APP_VERSION

# Tests the database connection once each time the page is loaded.
# st.session_state lasts as long as the browser tab: it is kept when moving between pages,
# and empty again after a reload. So the test runs only when there is no result yet
if "mongo_status" not in st.session_state:
    with st.spinner("Testing the database connection..."):
        run_connection_test()

# The app's pages, with the names shown in the sidebar.
# st.navigation replaces Streamlit's automatic page list (which used the file names),
# so the names and the order are decided here
pages = [
    st.Page("pages/page_home.py", title="Home", default=True),
    st.Page("pages/page_data.py", title="Reservoir Data", url_path="reservoir-data"),
    st.Page("pages/page_plot.py", title="Reservoir Plot", url_path="reservoir-plot"),
    st.Page("pages/page_cross_border.py", title="Cross-border flow", url_path="cross-border-flow"),
    st.Page("pages/page_about.py", title="About", url_path="about"),
]

navigation = st.navigation(pages)

# Pinned to the bottom of the sidebar. The number is set in pyproject.toml (see utils/about.py)
st.sidebar.markdown(
    f"<div style='position: fixed; bottom: 1rem; font-size: 0.8rem; opacity: 0.6;'>App version: {APP_VERSION}</div>",
    unsafe_allow_html=True,
)
navigation.run()