import streamlit as st

from utils.controls import global_selection
from utils.data import run_connection_test
from utils.about import APP_VERSION

# Uses the full width of the window instead of Streamlit's narrow default. Applies to every page
st.set_page_config(layout="wide")
# Keeps the content from getting too wide on very large screens
st.markdown("<style>.block-container { max-width: 1800px; }</style>", unsafe_allow_html=True)

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
    st.Page("pages/page_reservoirs.py", title="Reservoirs", url_path="reservoirs"),
    st.Page("pages/page_seasonal.py", title="Seasonality & Spectrum", url_path="seasonality-spectrum"),
    st.Page("pages/page_weather.py", title="Weather Outliers", url_path="weather-outliers"),
    st.Page("pages/page_cross_border.py", title="Cross-border flow", url_path="cross-border-flow"),
    st.Page("pages/page_about.py", title="About", url_path="about"),
]

navigation = st.navigation(pages)

# Pages that use (or are influenced by) the global data selection. It is drawn here, in the entry file,
# so it is the same widget on every page
GLOBAL_SELECTION_PAGES = {"reservoirs", "seasonality-spectrum", "weather-outliers"}
if navigation.url_path in GLOBAL_SELECTION_PAGES:
    global_selection()

# Pinned to the bottom of the sidebar. The number is set in pyproject.toml (see utils/about.py)
st.sidebar.markdown(
    f"<div style='position: fixed; bottom: 1rem; font-size: 0.8rem; opacity: 0.6;'>App version: {APP_VERSION}</div>",
    unsafe_allow_html=True,
)

navigation.run()