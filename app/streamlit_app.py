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

# The app's pages, grouped by type of task. Each key is a heading in the sidebar ("" gives no heading, so Home
# is on top on its own). st.navigation replaces Streamlit's automatic page list (which used the file names),
# so the names, the groups and the order are decided here
SECTIONS = {
    "": [
        st.Page("pages/page_home.py", title="Home", default=True),
    ],
    "Explore": [
        st.Page("pages/page_reservoirs.py", title="Reservoirs", url_path="reservoirs"),
        st.Page("pages/page_seasonal.py", title="Seasonality & Spectrum", url_path="seasonality-spectrum"),
        st.Page("pages/page_cross_border.py", title="Cross-border flow", url_path="cross-border-flow"),
        st.Page("pages/page_currency.py", title="Currency", url_path="currency"),
    ],
    "Anomalies": [
        st.Page("pages/page_weather.py", title="Weather Outliers", url_path="weather-outliers"),
    ],
    "Predict": [
        st.Page("pages/page_correlation.py", title="Weather vs reservoirs", url_path="weather-vs-reservoirs"),
        st.Page("pages/page_forecast.py", title="Forecast", url_path="forecast"),
    ],
    "Data": [
        st.Page("pages/page_data_status.py", title="Data status", url_path="data-status"),
        st.Page("pages/page_about.py", title="About", url_path="about"),
    ],
}

# One accent colour per group, shown as a band with the group's name at the top of each page,
# so it is clear which group is active
GROUP_COLORS = {"Explore": "#2a78d6", "Anomalies": "#eb6834", "Predict": "#2e9e6a", "Data": "#8a8f98"}

navigation = st.navigation(SECTIONS)

# The group of the page that is shown
group = next((name for name, pages in SECTIONS.items()
              if any(page.url_path == navigation.url_path for page in pages)), "")
if group in GROUP_COLORS:
    st.markdown(
        f"<div style='border-left: 6px solid {GROUP_COLORS[group]}; padding: 0.15rem 0.7rem; "
        f"font-size: 0.8rem; letter-spacing: 0.08em; text-transform: uppercase; opacity: 0.85;'>{group}</div>",
        unsafe_allow_html=True,
    )

# Pages that use (or are influenced by) the global data selection. It is drawn here, in the entry file,
# so it is the same widget on every page. The Forecast page has its own selectors, so it isn't here
GLOBAL_SELECTION_PAGES = {"reservoirs", "seasonality-spectrum", "weather-outliers", "weather-vs-reservoirs"}
if navigation.url_path in GLOBAL_SELECTION_PAGES:
    global_selection()

# Pinned to the bottom of the sidebar. The number is set in pyproject.toml (see utils/about.py)
st.sidebar.markdown(
    f"<div style='position: fixed; bottom: 1rem; font-size: 0.8rem; opacity: 0.6;'>App version: {APP_VERSION}</div>",
    unsafe_allow_html=True,
)

navigation.run()