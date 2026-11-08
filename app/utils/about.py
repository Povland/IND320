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
        table["has_data"] = [
            (area_type, area_nr) in with_data
            for area_type, area_nr in zip(table["area_type"], table["area_nr"])
        ]

    # How the description and has_data columns are shown
    column_config = {
        "description": st.column_config.TextColumn("description", width="large"),
        "has_data": st.column_config.CheckboxColumn(
            "Has data",
            help="Whether the area has any measurements in the reservoir data",
        ),
    }

    st.dataframe(table, hide_index=True, width="stretch", column_config=column_config)


def column_names():
    # Read from the same dictionary that renames the columns in ind320.nve, so it always matches the code
    st.write("The API returns Norwegian names. They are renamed on the way in:")
    st.markdown("\n".join(f"- `{norwegian}` → `{english}`" for norwegian, english in nve.COLUMN_NAMES.items()))


def reservoir_limitations():
    st.markdown("""
- VASS 4 (Nord-Norge) is in NVE's list of areas, but has no measurements. Only nine of the ten areas carry data.
- The data is weekly. Each date is the Sunday that ends the ISO week, not the day the values were measured.
- *Filling degree* is a fraction (0.72 = 72 %), not a percentage.
- The watercourse areas (VASS) are a hydrological division and don't match the price areas (EL).
- NVE's API has no date parameters, so the app downloads everything and keeps it for one hour.
  Use *Refresh data* on Home to get new numbers sooner.
""")


def crossborder_limitations():
    st.markdown("""
- The data is a snapshot from when the notebook was last run, two years back from then. The app doesn't fetch new data from ENTSO-E itself.
- The first and last year are therefore partial. *Data status* on Home shows the exact period.
- Borders that report every 15 minutes are averaged to hourly values, so short spikes are smoothed out.
- Hours without a reported value are left out, not set to zero.
- Times are stored in UTC and shown in Norwegian time.
""")


def links():
    st.markdown("""
- **Code:** [github.com/Povland/IND320](https://github.com/Povland/IND320)
- **NVE Magasinstatistikk:** [API](https://biapi.nve.no/magasinstatistikk/swagger/index.html) ·
  [description](https://www.nve.no/energi/analyser-og-statistikk/magasinstatistikk/)
- **ENTSO-E:** [Transparency Platform](https://transparency.entsoe.eu/) ·
  [API reference](https://documenter.getpostman.com/view/7009892/2s93JtP3F6) ·
  [entsoe-py](https://github.com/EnergieID/entsoe-py)
- **Tools:** [Streamlit docs](https://docs.streamlit.io/) · [MongoDB Atlas](https://cloud.mongodb.com/) · [uv](https://docs.astral.sh/uv/)
""")


# The packages the project uses, and what for. The versions are read from what is installed
PACKAGES = {
    "streamlit": "the app",
    "pandas": "tables and data handling",
    "plotly": "the plots",
    "pymongo": "reading from MongoDB",
    "requests": "NVE's API",
    "entsoe-py": "ENTSO-E's API (notebook)",
    "pyspark": "processing the data (notebook)",
    "cassandra-driver": "Cassandra (notebook)",
}


def tech_stack():
    rows = [{"Package": "Python", "Version": platform.python_version(), "Used for": "everything"}]
    for package, used_for in PACKAGES.items():
        try:
            installed = version(package)
        except PackageNotFoundError:
            installed = "not installed"
        rows.append({"Package": package, "Version": installed, "Used for": used_for})
    st.dataframe(pd.DataFrame(rows), hide_index=True)


# ---------------------------------------------------------------------------------------------
# The "About the data" boxes on the other pages: the parts that belong there, and a link to the About page
# ---------------------------------------------------------------------------------------------

def reservoir_data_info():
    with st.expander("About the data"):
        reservoir_source()
        st.markdown("**Known limitations**")
        reservoir_limitations()
        st.page_link(ABOUT_PAGE, label="More about the data and the project", icon="ℹ️")


def crossborder_data_info():
    with st.expander("About the data"):
        crossborder_source()
        pipeline()
        st.markdown("**Known limitations**")
        crossborder_limitations()
        st.page_link(ABOUT_PAGE, label="More about the data and the project", icon="ℹ️")