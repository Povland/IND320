import sys
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st
from pymongo import MongoClient

# The app always uses the ind320 code in this repository (src/ind320), not an installed copy of it.
# Locally, uv sync installs the package as editable, so the two are the same. On Streamlit Cloud the package
# is installed as a fixed copy, and only reinstalled when the dependencies change, so after a code-only push
# the installed copy would be out of date. Putting src first on the import path avoids that
SRC_PATH = Path(__file__).resolve().parents[2] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from ind320 import correlation, norgesbank, anomalies, forecast, areas, entsoe, maps, nve, openmeteo, seasonal, weather

# The MongoDB collection with the cross-border flows: written by notebooks/Oblig2.ipynb, and kept up to date by the
# app (ind320.entsoe). The name comes from the package, so it is only written in one place
FLOWS_COLLECTION = entsoe.FLOWS_COLLECTION

# When the app last actually downloaded from NVE and Norges Bank (not read from its cache), for Data status.
# Kept in the server's memory: shared by all visitors, and empty again after the app restarts
LAST_DOWNLOAD = {}


# Caches the result for one hour, since the data only changes weekly.
# Errors are raised from here instead of returned, so a failed download is NOT cached
@st.cache_data(ttl=3600, show_spinner="Downloading reservoir data from NVE...")
def _fetch_reservoir_data():
    data = nve.fetch_reservoir_data()
    LAST_DOWNLOAD["nve"] = pd.Timestamp.now(tz="Europe/Oslo")
    return data


# All reservoir statistics from NVE's API (all areas, all weeks).
# Shows an error in the app and returns an empty table if the download fails: the network, NVE being down,
# or an answer that can't be read
def load_reservoir_data():
    try:
        return _fetch_reservoir_data()
    except Exception as error:
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
# NVE's API has no date parameters, so everything is downloaded once (cached above) and the period is cut out here. 
# The slider therefore decides which data the app uses.
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
# Called once when the page is loaded (streamlit_app.py, manual=False) and when the "Test connection" button on Data status is clicked (manual=True)
def run_connection_test(manual=False):
    connected, details = check_mongo_connection()
    st.session_state["mongo_status"] = {
        "connected": connected,
        "details": details,
        "tested_at": datetime.now(ZoneInfo("Europe/Oslo")),   # Norwegian time, also on Streamlit Cloud (which runs in UTC)
        "manual": manual,   # whether the last test was started with the button
    }


# Clears everything cached with st.cache_data (NVE data, areas, cross-border data), so it is fetched again.
# The MongoDB connection itself (cache_resource) is kept
def refresh_data():
    st.cache_data.clear()


# ---------------------------------------------------------------------------------------------
# Cross-border flows (ENTSO-E) in MongoDB: first stored by the Oblig2 notebook (through Cassandra and Spark),
# then kept up to date by the app (straight from ENTSO-E, see ind320.entsoe).
# ---------------------------------------------------------------------------------------------


# All connections in MongoDB, e.g. ["NO_1-SE_3", "NO_2-DE_LU", ...]
@st.cache_data(ttl=3600)
def load_connections():
    return sorted(get_mongo_db()[FLOWS_COLLECTION].distinct("connection"))


# The years with data for the chosen connections (a tuple, so it can be cached)
@st.cache_data(ttl=3600)
def load_years(connections):
    return sorted(get_mongo_db()[FLOWS_COLLECTION].distinct("year", {"connection": {"$in": list(connections)}}))


# The months with data for the chosen connections in the chosen years (2024 and 2026 are partial years)
@st.cache_data(ttl=3600)
def load_months(connections, years):
    return sorted(get_mongo_db()[FLOWS_COLLECTION].distinct(
        "month", {"connection": {"$in": list(connections)}, "year": {"$in": list(years)}}
    ))


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


# Total flow for each chosen connection and direction in the chosen years, in GWh.
# MongoDB sums the monthly totals, so only the totals (not the hours) are sent to the app
@st.cache_data(ttl=3600)
def load_yearly_totals(connections, years):
    result = get_mongo_db()[FLOWS_COLLECTION].aggregate([
        {"$match": {"connection": {"$in": list(connections)}, "year": {"$in": list(years)}}},
        {"$group": {
            "_id": {"connection": "$connection", "direction": "$direction"},
            "total_mwh": {"$sum": "$total_mwh"},
        }},
    ])
    rows = [
        {"connection": doc["_id"]["connection"], "direction": doc["_id"]["direction"], "gwh": doc["total_mwh"] / 1000}
        for doc in result
    ]
    return pd.DataFrame(rows, columns=["connection", "direction", "gwh"])


# Hourly flow for the chosen connections in the chosen months of the chosen years, one row per hour, connection and direction.
# The lists in each document are unpacked into rows, and the time is converted to Norwegian time
@st.cache_data(ttl=3600)
def load_hourly_flows(connections, years, months):
    documents = get_mongo_db()[FLOWS_COLLECTION].find(
        {"connection": {"$in": list(connections)}, "year": {"$in": list(years)}, "month": {"$in": list(months)}},
        {"_id": 0, "connection": 1, "direction": 1, "time": 1, "mwh": 1},
    )
    frames = [
        pd.DataFrame({"time": doc["time"], "mwh": doc["mwh"], "connection": doc["connection"], "direction": doc["direction"]})
        for doc in documents
    ]
    if not frames:
        return pd.DataFrame(columns=["time", "mwh", "connection", "direction"])

    hourly = pd.concat(frames, ignore_index=True)
    # MongoDB returns UTC times without time zone info, so they are marked as UTC first
    hourly["time"] = pd.to_datetime(hourly["time"], utc=True).dt.tz_convert("Europe/Oslo")
    return hourly.sort_values(["connection", "direction", "time"])

# The cross-border flow in one week, per connection: out of Norway, into Norway and net (out minus in), in GWh,
# and how many hours were found. The week is Monday 00:00 to Sunday 23:59 Norwegian time, ending on week_end
# (a Sunday, like NVE's date_id). Only the one or two months the week touches are read from MongoDB.
# Empty table if nothing is stored for the week
@st.cache_data(ttl=3600, show_spinner=False)
def load_weekly_flows(week_end):
    columns = ["connection", "out_gwh", "in_gwh", "net_gwh", "hours"]
    end = pd.Timestamp(week_end).tz_localize("Europe/Oslo") + pd.Timedelta(days=1)
    start = end - pd.Timedelta(days=7)
    last_hour = end - pd.Timedelta(hours=1)

    connections = tuple(load_connections())
    years = tuple(sorted({start.year, last_hour.year}))
    months = tuple(sorted({start.month, last_hour.month}))
    hourly = load_hourly_flows(connections, years, months)
    if hourly.empty:
        return pd.DataFrame(columns=columns)

    week = hourly[(hourly["time"] >= start) & (hourly["time"] < end)]
    if week.empty:
        return pd.DataFrame(columns=columns)

    totals = week.pivot_table(index="connection", columns="direction", values="mwh", aggfunc="sum", fill_value=0)
    totals = totals.reindex(columns=["out", "in"], fill_value=0) / 1000
    result = pd.DataFrame({"out_gwh": totals["out"], "in_gwh": totals["in"]})
    result["net_gwh"] = result["out_gwh"] - result["in_gwh"]
    result["hours"] = week.groupby("connection")["time"].nunique()
    return result.reset_index()[columns]

# Filling degree as a regular weekly series, for STL and the spectrogram (ind320.seasonal).
# Built from the reservoir data above, so it follows the same period slider.

# One area's filling degree within the chosen period, one value per week (Sundays).
# Returns an empty series if there is no data for the area or period
def load_filling_series(area_type, area_nr, start, end):
    data = load_reservoir_period(area_type, [area_nr], start, end)
    if data.empty:
        return pd.Series(dtype=float)
    return seasonal.filling_series(data, area_type, area_nr)


# Weather (ERA5 via Open-Meteo), averaged per area and stored in MongoDB (see ind320.weather).
# One document per area, year and number of random locations. Downloaded on Weather Outliers
# (one area) or Data status (all missing areas), or from notebooks/Oblig3.ipynb.

# The numbers of random locations per area that can be chosen, and the default
POINT_OPTIONS = areas.POINT_OPTIONS
DEFAULT_POINTS = areas.POINTS_PER_AREA

# The first year offered on the weather pages. ERA5 goes back to 1940, but older years are rarely needed here
WEATHER_FIRST_YEAR = 2015


# Which areas, years and numbers of locations are stored. Errors are raised from here, so a failed load is NOT cached
@st.cache_data(ttl=3600)
def _fetch_stored_weather():
    return weather.stored_weather(get_mongo_db())


# Which areas, years and numbers of locations are stored, one row each. Empty table (and a message) if MongoDB can't be reached
def load_stored_weather():
    try:
        return _fetch_stored_weather()
    except Exception as error:   # missing secrets, network, IP not allowed in Atlas...
        st.error(f"Could not read the stored weather data from MongoDB: {error}")
        return pd.DataFrame(columns=["region", "area_type", "area_nr", "year", "points_per_area", "variables", 
                                     "settings", "first_hour", "last_hour", "stored_at", "reason", "complete"])


# The stored weather straight from MongoDB, not from the cache, for the checks on Data status.
# The cache is cleared first, so the rest of the app sees the same fresh table afterwards
def fresh_stored_weather():
    _fetch_stored_weather.clear()
    return load_stored_weather()


# The years that can be chosen on the weather pages, newest first: every year from WEATHER_FIRST_YEAR, including the
# current one, which runs up to the newest ERA5 data (about 6 days ago, see weather.year_end). In the first days of
# January there is no data for the new year yet, so it starts with the year before
def weather_years():
    newest = (datetime.now(timezone.utc) - timedelta(days=weather.ERA5_DELAY_DAYS)).year
    return list(range(newest, WEATHER_FIRST_YEAR - 1, -1))


# One area's hourly weather for one year and number of locations. None if it isn't stored.
# Cached per area, year and number, so switching back and forth doesn't ask MongoDB again
@st.cache_data(ttl=3600, show_spinner="Loading weather data from MongoDB...")
def _fetch_region_weather(area_type, area_nr, year, points_per_area):
    return weather.load_region_weather(get_mongo_db(), weather.region_id(area_type, area_nr), year, points_per_area)


def load_region_weather(area_type, area_nr, year, points_per_area=DEFAULT_POINTS):
    try:
        return _fetch_region_weather(area_type, area_nr, year, points_per_area)
    except Exception as error:
        st.error(f"Could not read weather data for {weather.region_id(area_type, area_nr)} {year}: {error}")
        return None


# One area's weekly weather (weeks ending on Sunday, like NVE's), from all the complete years stored for the area
# and number of locations. Used by the map, the forecast and the correlation. The hourly years are joined before they
# are made weekly, so the week across New Year is complete. Cached, so it is made once per area and number of
# locations, not on every move of a slider. Errors are raised from here, so a failed load is NOT cached
@st.cache_data(ttl=3600, show_spinner="Loading weekly weather from MongoDB...")
def _fetch_weekly_weather(area_type, area_nr, points_per_area):
    stored = _fetch_stored_weather()
    match = ((stored["area_type"] == area_type) & (stored["area_nr"] == area_nr)
             & (stored["points_per_area"] == points_per_area) & (stored["complete"] == True))
    years = sorted(stored.loc[match, "year"].astype(int).tolist())
    frames = [_fetch_region_weather(area_type, area_nr, year, points_per_area) for year in years]
    frames = [frame for frame in frames if frame is not None and not frame.empty]
    if not frames:
        return pd.DataFrame()
    return weather.weekly_weather(pd.concat(frames).sort_index())


# The same, with a readable message instead of a crash if MongoDB can't be read. Empty table then.
# show_error=False leaves the message to the page, e.g. the map, which loads every area and shows one message for all
def load_weekly_weather(area_type, area_nr, points_per_area=DEFAULT_POINTS, show_error=True):
    try:
        return _fetch_weekly_weather(area_type, area_nr, points_per_area)
    except Exception as error:
        if show_error:
            st.error(f"Could not read the weather for {weather.region_id(area_type, area_nr)} from MongoDB: {error}")
        return pd.DataFrame()
    

# How long a download of this many API calls takes, in minutes. Follows the pacing in openmeteo.fetch_cells:
# by the minute limit if the job fits within one hour's limit, otherwise by the hour limit
def _download_minutes(calls):
    if calls <= 0.9 * openmeteo.CALLS_PER_HOUR:
        return calls / openmeteo.CALLS_PER_MINUTE
    return calls / openmeteo.CALLS_PER_HOUR * 60


def _clear_weather_caches():
    _fetch_stored_weather.clear()
    _fetch_region_weather.clear()
    _fetch_weekly_weather.clear()


# ---------------------------------------------------------------------------------------------
# Shapes and grid cells for the maps (ind320.areas and ind320.maps).
# The shapefiles are read and clipped once per server (cached inside ind320.areas), which takes a few seconds
# the first time. These functions only pick out what each map needs
# ---------------------------------------------------------------------------------------------


# The shapes of all areas of one type, ready to draw (latitude and longitude, simplified), read from the GeoJSON
# files in data/ (made by areas.export_geojson). Falls back to the shapefiles if a file is missing.
# Cached, so the file is read once per type of area. cache_data hands out a copy each time,
# so a page can't change the cached table
@st.cache_data(show_spinner=False)
def load_area_shapes(area_type):
    return areas.load_geojson(area_type)


# The shape of one area, as a one-row table (the map on Weather Outliers)
def load_area_shape(area_type, area_nr):
    shapes = load_area_shapes(area_type)
    return shapes[shapes["area_nr"] == area_nr]


# Coarser outlines for the animated map on Reservoirs. In an animation every frame
# redraws every outline, so far fewer points make it play and drag much more smoothly. On a map of all of Norway
# the difference can't be seen. Cached per type of area
@st.cache_data(show_spinner=False)
def load_animation_shapes(area_type):
    return areas.map_shapes(area_type, tolerance=0.05)


# One area's grid cells (latitude, longitude, n_points) for a given number of random locations
def load_region_cells(area_type, area_nr, points_per_area=DEFAULT_POINTS):
    return weather.region_cells(weather.region_id(area_type, area_nr), points_per_area)


# The filling degree of each area of one type at the last week on or before the given date.
# Returns (Series from area_nr to filling degree, the date of that week). Empty if there is no data
def load_filling_at(area_type, date):
    data = load_reservoir_data()
    if data.empty:
        return pd.Series(dtype=float), None
    of_type = data[data["area_type"] == area_type]
    of_type = of_type.loc[: pd.Timestamp(date)]
    if of_type.empty:
        return pd.Series(dtype=float), None
    week = of_type.index.max()
    return of_type.loc[[week]].set_index("area_nr")["filling_degree"], week


# ---------------------------------------------------------------------------------------------
# Checking for updates and downloading what is missing. Used by the "Fetch latest data" panels
# (utils/updates.py) and by Home. A check is free, and only a download uses the API
# ---------------------------------------------------------------------------------------------


# Reservoir data: the latest week in the app's cache, NVE's next publication, and whether that time has passed,
# so a newer week has probably been published. NVE publishes every Wednesday at 13:00
def check_reservoirs():
    data = load_reservoir_data()
    if data.empty:
        return {"available": False}

    next_publication = pd.Timestamp(data.iloc[-1]["next_publishing_date"])
    if next_publication.tzinfo is not None:
        next_publication = next_publication.tz_convert("Europe/Oslo").tz_localize(None)
    now = pd.Timestamp.now(tz="Europe/Oslo").tz_localize(None)

    return {
        "available": True,
        "latest_week": data.index[-1],
        "next_publication": next_publication,
        "newer_expected": now >= next_publication,
    }


# Clears only the reservoir cache, so the next load fetches from NVE again (the rest of the cache is kept)
def refresh_reservoirs():
    _fetch_reservoir_data.clear()

# Clears only the currency cache, so the Currency page fetches from Norges Bank again
def refresh_rates():
    _fetch_rates.clear()


# Currency: asks Norges Bank directly (not the cache) for the last two weeks, and gives the latest business day
# with a rate. This is the ping: it shows whether the API answers and how new its data is.
# Errors are raised, so the page can show them
def check_currency():
    today = pd.Timestamp.now(tz="Europe/Oslo").tz_localize(None).normalize()
    rates = norgesbank.fetch_rates(today - pd.Timedelta(days=14), today)
    LAST_DOWNLOAD["norgesbank"] = pd.Timestamp.now(tz="Europe/Oslo")
    rates = rates.dropna(how="all")
    return {"available": not rates.empty, "latest_day": rates.index.max() if not rates.empty else None}


# Cross-border flow: the period stored in MongoDB, the last hour stored, and whether that is more than a couple of
# hours behind (ENTSO-E publishes with about an hour's delay). Also whether the app has an ENTSO-E token to update with
def check_crossborder():
    period = load_flow_period()
    collection = get_mongo_db()[FLOWS_COLLECTION]
    last_hour = entsoe.last_stored_hour(collection)
    now = pd.Timestamp.now(tz="UTC")
    return {
        "available": period is not None,
        "period": period,
        "last_hour": last_hour,
        "behind": (now - last_hour) if last_hour is not None else None,
        "newer_expected": last_hour is None or now - last_hour > pd.Timedelta(hours=3),
        "has_token": "entsoe" in st.secrets and "token" in st.secrets["entsoe"],
        "stored_at": entsoe.last_download(collection),
    }


# Clears the caches of the cross-border data, so the page sees new months right away
def _clear_flow_caches():
    for cached in [load_connections, load_years, load_months, load_flow_period, load_yearly_totals, load_hourly_flows,
                   load_weekly_flows]:
        cached.clear()


# Fetches new cross-border flows from ENTSO-E (from the start of the newest stored month up to now) and stores them
# in MongoDB. progress(done, total) is called after each of the 18 series. Errors are raised, so the page can show them
def download_crossborder(progress=None):
    client = entsoe.get_client(st.secrets["entsoe"]["token"])
    try:
        return entsoe.update_crossborder(get_mongo_db()[FLOWS_COLLECTION], client, progress=progress)
    finally:
        _clear_flow_caches()


# What is missing of the weather data for the given areas ((area_type, area_nr) pairs), years and number of
# locations, and what downloading it would cost. Returns (missing, cost), where missing has one row per area and
# year with the reason, and cost has the grid cells, API calls, minutes and days (at 10,000 calls per day).
# Cells shared by several areas in the same year are counted once, since they are downloaded once
def check_weather(regions, years, points_per_area=DEFAULT_POINTS):
    region_ids = [weather.region_id(area_type, nr) for area_type, nr in regions]
    missing = weather.missing_weather(get_mongo_db(), region_ids, years, points_per_area)

    cells, calls = 0, 0.0
    for year, group in missing.groupby("year"):
        unique = weather.unique_cells(group["region"].tolist(), points_per_area)
        cells += len(unique)
        calls += openmeteo.call_weight(len(unique), f"{year}-01-01", f"{weather.year_end(year):%Y-%m-%d}")

    cost = {
        "cells": cells,
        "calls": calls,
        "minutes": _download_minutes(calls),
        "days": math.ceil(calls / openmeteo.CALLS_PER_DAY) if calls else 0,
    }
    return missing, cost


# Downloads what check_weather found missing, one year at a time: all the year's cells first (each shared cell
# once), then each of the year's areas is stored in MongoDB before the next year starts. So if a limit stops it,
# every year finished so far is stored, and the next check only finds what is left.
# progress(fraction, text) is called as it goes, with fraction from 0 to 1 over all the years.
# Errors (the API limit, the network) are raised, so the page can show them
def download_missing_weather(missing, points_per_area=DEFAULT_POINTS, progress=None):
    db = get_mongo_db()
    years = sorted(int(year) for year in missing["year"].unique())

    try:
        for number, year in enumerate(years, start=1):
            regions = missing.loc[missing["year"] == year, "region"].tolist()

            def year_progress(done, total, year=year, number=number):
                if progress:
                    fraction = (number - 1 + done / total) / len(years)
                    progress(fraction, f"{year}: {done} of {total} grid cells ({number} of {len(years)} years)")

            if progress:
                progress((number - 1) / len(years), f"{year}: checking which cells are already downloaded...")

            averages = weather.download_regions_weather(
                                regions, f"{year}-01-01", f"{weather.year_end(year):%Y-%m-%d}", points_per_area=points_per_area,
                progress=year_progress,
            )
            for region, average in averages.items():
                weather.save_region_weather(db, region, average, points_per_area)

        if progress:
            progress(1.0, "Done")
    finally:
        # Also after an error, so the years that were stored show up right away
        _clear_weather_caches()


# ---------------------------------------------------------------------------------------------
# Exchange rates from Norges Bank (ind320.norgesbank). Fetched straight from the API, no token needed
# ---------------------------------------------------------------------------------------------

# EUR and USD in NOK, daily (business days) or weekly (weeks ending Sunday, like NVE's). Cached for an hour.
# Errors are raised from here, so a failed fetch is NOT cached
@st.cache_data(ttl=3600, show_spinner="Fetching exchange rates from Norges Bank...")
def _fetch_rates(start, end, weekly):
    rates = norgesbank.weekly_rates(start, end) if weekly else norgesbank.fetch_rates(start, end)
    LAST_DOWNLOAD["norgesbank"] = pd.Timestamp.now(tz="Europe/Oslo")
    return rates


# The same, with a readable message instead of a crash if Norges Bank doesn't answer. Empty table then
def load_rates(start, end, weekly=False):
    try:
        return _fetch_rates(start, end, weekly)
    except Exception as error:
        st.error(f"Could not fetch exchange rates from Norges Bank: {error}")
        return pd.DataFrame()


# ---------------------------------------------------------------------------------------------
# Cached results of the analyses (Oblig4). Each is computed once per set of inputs, so going back to a setting
# that was already shown is instant. The inputs (series, tables, numbers) are what decides the cache.
# Errors (e.g. too little data for the settings) are raised and NOT cached, so the page can show them
# ---------------------------------------------------------------------------------------------

# The forecast (ind320.forecast.forecast_filling) with the same arguments. info["seconds"] is the time of the
# first run, also when the result comes from the cache
@st.cache_data(ttl=3600, show_spinner="Training the model and forecasting...", max_entries=100)
def run_forecast(filling, exog=None, **settings):
    return forecast.forecast_filling(filling, exog=exog, **settings)


# The sliding window correlation and the lag scan (ind320.correlation)
@st.cache_data(ttl=3600, show_spinner=False, max_entries=100)
def run_sliding_correlation(weather_series, reservoir_series, window, lag):
    return correlation.sliding_correlation(weather_series, reservoir_series, window=window, lag=lag)


@st.cache_data(ttl=3600, show_spinner=False, max_entries=100)
def run_lag_correlations(weather_series, reservoir_series, max_lag=52):
    return correlation.lag_correlations(weather_series, reservoir_series, max_lag=max_lag)


# The animated map on Reservoirs, with its table (one row per week, one column per area). Building the figure
# (the shapes and hundreds of frames) is the slow part, so it is made once per type of area, period, step,
# outlined areas and light/dark theme, not on every rerun. Returns (None, empty table) if there is no data
@st.cache_data(ttl=3600, show_spinner="Preparing the map...", max_entries=20)
def load_animation_figure(area_type, start, end, step, selected, dark, title):
    shapes = load_animation_shapes(area_type)
    period = load_reservoir_period(area_type, available_area_numbers(area_type), start, end)
    table = period.pivot_table(index=period.index, columns="area_nr", values="filling_degree")
    if table.empty:
        return None, table

    # Every step-th week, counted back from the last one, so the latest week is always a frame
    frames = table.iloc[::-1].iloc[::step].iloc[::-1]
    fig = maps.overview_animation(shapes, frames, selected=list(selected), label="Filling degree", dark=dark,
                                  title=title)
    return fig, table