import platform
from importlib.metadata import PackageNotFoundError, version

import pandas as pd
import streamlit as st

from utils.data import available_dates, load_areas, load_reservoir_data, nve

# Everything about the data and the project is written once, in the functions below.
# The About page shows all of them, and the "About the data" boxes on the other pages show the parts that belong there.
# So there is only one place to change the text.

ABOUT_PAGE = "pages/page_about.py"

# The app version. Set by hand: one number per assignment
APP_VERSION = "3"


def author():
    st.markdown(f"**Philip A. K. Øvland** · IND320 Data til beslutning · NMBU · autumn 2026 · version {APP_VERSION}")


def reservoir_source():
    # The first year is read from the data, so the text is never wrong. Left out if NVE can't be reached
    data = load_reservoir_data()
    since = f", going back to {available_dates()[0].year}" if not data.empty else ""
    st.markdown(f"""
**Reservoir levels** come from NVE's
[Magasinstatistikk API](https://biapi.nve.no/magasinstatistikk/swagger/index.html), fetched with the module `ind320.nve`.
It publishes how full the Norwegian hydropower reservoirs are, one measurement per area per week{since}.
New figures arrive every Wednesday at 13:00.

Part 1 of this project read a CSV copy of that data. Part 2 calls the API directly instead,
so the app is never out of date. The CSV is only kept so that the Part 1 notebook still runs.
""")


def crossborder_source():
    st.markdown("""
**Cross-border power flow** comes from the [ENTSO-E Transparency Platform](https://transparency.entsoe.eu/),
fetched with the Python library `entsoe-py`. It reports the physical flow on the interconnectors in Europe,
every 15 minutes or every hour depending on the border. The app covers all of Norway's 9 connections to other countries,
in both directions:

- **NO 1:** Sweden (SE 3)
- **NO 2:** Denmark (Skagerrak), Germany (NordLink), the Netherlands (NorNed) and Great Britain (North Sea Link)
- **NO 3:** Sweden (SE 2)
- **NO 4:** Sweden (SE 1 and SE 2) and Finland

"Out of Norway" is flow from the Norwegian price area to the foreign area, "Into Norway" the opposite.
""")


def how_they_fit():
    st.markdown("""
Reservoirs fill up with rain and snowmelt, and empty when the power is used or sold.
The flow data show how much is actually being sold abroad, and how much is bought back.
""")


def pipeline():
    st.markdown("""
The cross-border data go through several steps before the app reads them (see `notebooks/Oblig2.ipynb`):

| Step | Where it runs | What it does or holds |
|---|---|---|
| ENTSO-E API | notebook | hourly flows for the last two years. Borders that report every 15 minutes are averaged to one value per hour |
| Cassandra | local Docker container | the hourly values, one row per hour, connection and direction, written with Spark |
| Spark | locally | picks the columns and groups them into one document per connection, year, month and direction |
| MongoDB Atlas | cloud | the documents this app reads |
| Streamlit | this app | reads from MongoDB and draws the plots |

The detour through Cassandra and Spark is there because a deployed app can't reach a database running on my laptop.
Whatever the app needs has to end up somewhere online, and in a shape the app can read quickly.

The reservoir data take a shorter route: the app calls NVE's API itself and keeps the result for one hour.
""")


def areas_table():
    areas = load_areas()
    if areas.empty:
        st.warning("Could not fetch the list of areas from NVE.")
        return

    # NVE's names -> the names used in the rest of the project
    table = areas.rename(columns={
        "omrType": "area_type",
        "omrnr": "area_nr",
        "navn": "name",
        "navn_langt": "long_name",
        "beskrivelse": "description",
    })[["area_type", "area_nr", "name", "long_name", "description"]]

    # Marks which areas actually have measurements in the reservoir data (VASS 4 has none)
    data = load_reservoir_data()
    if not data.empty:
        with_data = set(zip(data["area_type"], data["area_nr"]))
        table["has_data"] = [(t, n) in with_data for t, n in zip(table["area_type"], table["area_nr"])]

    st.dataframe(
        table,
        hide_index=True,