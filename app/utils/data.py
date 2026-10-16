import sys
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

# ind320 is installed as a package via uv sync. The fallback covers environments


try:
    from ind320 import nve
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
    from ind320 import nve


@st.cache_data(ttl=3600)
# Caches the result for one hour, since the data only changes weekly
def load_reservoir_data():
    try:
        return nve.fetch_reservoir_data()
    except requests.RequestException as error:
        st.error(f"Could not fetch data from NVE: {error}")
        return pd.DataFrame()


@st.cache_data(ttl=24 * 3600)
def load_areas():
    try:
        return nve.fetch_areas()
    except requests.RequestException as error:
        st.error(f"Could not fetch areas from NVE: {error}")
        return pd.DataFrame()