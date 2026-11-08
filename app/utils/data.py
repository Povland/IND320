import sys
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

from pymongo import MongoClient

from datetime import datetime
from zoneinfo import ZoneInfo

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


# One shared MongoDB connection for the whole app, using the details in st.secrets["mongo"].
# cache_resource (not cache_data) is used because a connection should be reused, not copied
@st.cache_resource
def get_mongo_db():
    client = MongoClient(st.secrets["mongo"]["uri"], serverSelectionTimeoutMS=10000)
    return client[st.secrets["mongo"].get("database", "ind320")]


# Checks the connection to MongoDB in three steps, all of which need a live connection:
# 1. ping: the server answers, and the login in the URI is accepted
# 2. list the collections: the user is allowed to read the database
# 3. count the cross-border documents: the data the app needs is actually there
# Returns (True, {"collections": [...], "flow_documents": n}) or (False, error message)
def check_mongo_connection():
    try:
        if "mongo" not in st.secrets:   # raises an error itself if there is no secrets file at all
            return False, "No [mongo] section in the secrets (.streamlit/secrets.toml, or Settings → Secrets on Streamlit Cloud)."
        db = get_mongo_db()
        db.client.admin.command("ping")
        return True, {
            "collections": db.list_collection_names(),
            "flow_documents": db[FLOWS_COLLECTION].count_documents({}),
        }
    except Exception as error:   # missing secrets, wrong password, network, IP not allowed in Atlas...
        return False, str(error)


# Runs the check above and stores the result in the session, so every page can read it without asking MongoDB again.
# Called once when the page is loaded (streamlit_app.py, manual=False) and when the "Test connection" button on Home is clicked (manual=True)
def run_connection_test(manual=False):
    connected, details = check_mongo_connection()
    st.session_state["mongo_status"] = {
        "connected": connected,
        "details": details,
        "tested_at": datetime.now(ZoneInfo("Europe/Oslo")),   # Norwegian time, also on Streamlit Cloud (which runs in UTC)
        "manual": manual,   # whether the last test was started with the button
    }

# Clears everything cached with st.cache_data (NVE data, areas, cross-border data, version), so it is fetched again.
# The MongoDB connection itself (cache_resource) is kept
def refresh_data():
    st.cache_data.clear()


# ---------------------------------------------------------------------------------------------
# Cross-border flows (ENTSO-E), prepared in the notebook with Spark and stored in MongoDB.
# One document per connection, year, month and direction, with the hours as lists (time, mwh)
# and the month's total (total_mwh). See notebooks/Oblig2.ipynb.
# ---------------------------------------------------------------------------------------------

FLOWS_COLLECTION = "crossborder_flows"


# All connections in MongoDB, e.g. ["NO_1-SE_3", "NO_2-DE_LU", ...]
@st.cache_data(ttl=3600)
def load_connections():
    return sorted(get_mongo_db()[FLOWS_COLLECTION].distinct("connection"))


# The years with data for one connection
@st.cache_data(ttl=3600)
def load_years(connection):
    return sorted(get_mongo_db()[FLOWS_COLLECTION].distinct("year", {"connection": connection}))


# The months with data for one connection in one year (2024 and 2026 are partial years)
@st.cache_data(ttl=3600)
def load_months(connection, year):
    return sorted(get_mongo_db()[FLOWS_COLLECTION].distinct("month", {"connection": connection, "year": year}))

# The first and last month with cross-border data, as ((year, month), (year, month)). None if the collection is empty
@st.cache_data(ttl=3600)
def load_flow_period():
    collection = get_mongo_db()[FLOWS_COLLECTION]
    projection = {"_id": 0, "year": 1, "month": 1}
    first = collection.find_one({}, projection, sort=[("year", 1), ("month", 1)])
    last = collection.find_one({}, projection, sort=[("year", -1), ("month", -1)])
    if first is None:
        return None
    return (first["year"], first["month"]), (last["year"], last["month"])


# Total flow in each direction for one connection in one year, in GWh.
# MongoDB sums the monthly totals, so only the totals (not the hours) are sent to the app
@st.cache_data(ttl=3600)
def load_yearly_totals(connection, year):
    result = get_mongo_db()[FLOWS_COLLECTION].aggregate([
        {"$match": {"connection": connection, "year": year}},
        {"$group": {"_id": "$direction", "total_mwh": {"$sum": "$total_mwh"}}},
    ])
    return pd.DataFrame(
        [{"direction": doc["_id"], "gwh": doc["total_mwh"] / 1000} for doc in result]
    )


# Hourly flow for one connection in the chosen months of one year, one row per hour and direction.
# The lists in each document are unpacked into rows, and the time is converted to Norwegian time
@st.cache_data(ttl=3600)
def load_hourly_flows(connection, year, months):
    documents = get_mongo_db()[FLOWS_COLLECTION].find(
        {"connection": connection, "year": year, "month": {"$in": list(months)}},
        {"_id": 0, "direction": 1, "time": 1, "mwh": 1},
    )
    frames = [
        pd.DataFrame({"time": doc["time"], "mwh": doc["mwh"], "direction": doc["direction"]})
        for doc in documents
    ]
    if not frames:
        return pd.DataFrame(columns=["time", "mwh", "direction"])

    hourly = pd.concat(frames, ignore_index=True)
    # MongoDB returns UTC times without time zone info, so they are marked as UTC first
    hourly["time"] = pd.to_datetime(hourly["time"], utc=True).dt.tz_convert("Europe/Oslo")
    return hourly.sort_values(["direction", "time"])