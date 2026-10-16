import sys
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

# ind320 is installed as a package via uv sync. 
try:
    from ind320 import nve
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
    from ind320 import nve


# Caches the result for one hour, since the data only changes weekly.
# Errors are raised from here instead of returned, so a failed download is NOT cached
@st.cache_data(ttl=3600, show_spinner="Downloading reservoir data from NVE...")
def _fetch_reservoir_data():
    return nve.fetch_reservoir_data()


# All reservoir statistics from NVE's API (all areas, all weeks).
# Shows an error in the app and returns an empty table if the download fails
def load_reservoir_data():
    try:
        return _fetch_reservoir_data()
    except requests.RequestException as error:
        st.error(f"Could not fetch data from NVE: {error}")
        return pd.DataFrame()


# All weeks that exist in the data, as dates. Used as options in the period slider
def available_dates():
    data = load_reservoir_data()
    return sorted(set(data.index.date))


# The area numbers that exist in the data for one type of area, e.g. [1, 2, 3, 4, 5] for EL
def available_area_numbers(area_type):
    data = load_reservoir_data()
    return sorted(data.loc[data["area_type"] == area_type, "area_nr"].unique().tolist())


# Reservoir statistics for the chosen areas of one type (EL, NO or VASS) within the chosen period.
# NVE's API has no date parameters, so everything is downloaded once (cached above) and the period is cut out here. The slider therefore decides which data the app uses.
def load_reservoir_period(area_type, area_numbers, start, end):
    data = load_reservoir_data()
    if data.empty:
        return data
    data = data[(data["area_type"] == area_type) & (data["area_nr"].isin(area_numbers))]
    return data.loc[pd.Timestamp(start) : pd.Timestamp(end)]


# Names and descriptions of the areas in NVE's API, cached for one day.
# Errors are raised from here instead of returned, so a failed download is NOT cached
@st.cache_data(ttl=24 * 3600)
def _fetch_areas():
    return nve.fetch_areas()


def load_areas():
    try:
        return _fetch_areas()
    except requests.RequestException as error:
        st.error(f"Could not fetch areas from NVE: {error}")
        return pd.DataFrame()