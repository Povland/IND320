import calendar

import pandas as pd
import plotly.express as px
import streamlit as st

from utils.data import (
    DEFAULT_POINTS, FLOWS_COLLECTION, POINT_OPTIONS, check_crossborder, check_reservoirs, fresh_stored_weather,
    load_stored_weather, refresh_data, refresh_reservoirs, run_connection_test, weather, weather_years,
)
from utils.updates import weather_panel

st.title("Reservoirs, power flow and weather")
st.write("A dashboard for Norway's hydropower reservoirs, the power flow to and from the neighbouring countries, "
         "and the weather over the price and watercourse areas.")


st.subheader("Pages:")
st.markdown("""
- *Reservoirs*: The filling degree on a map (any week since 1995), the areas compared over time in a plot, and the data as a table.
- *Seasonality & Spectrum*: How the filling degree of one area is built up: STL decomposition and spectrogram.
- *Weather Outliers*: Hourly weather for one area and year: outliers in the precipitation (SPC) and anomalies in the temperature (LOF).
- *Cross-border flow*: Power flows between Norway and its neighbours (ENTSO-E, from MongoDB).
- *About*: Where the data come from, how they are processed, known limitations and the app version.

The type of area, the areas and the period are chosen in the sidebar on the pages that use them, and are shared between those pages.
""")


st.info("This dashboard is a work in progress. More features will be added in the future.")

# All areas that can have weather data: EL 1-5 and VASS 1-3 (no weather polygon for all of Norway).
# Taken from ind320.weather, not from the reservoir data, so the list is right even when NVE doesn't answer
expected_regions = [weather.parse_region_id(region) for region in weather.ALL_REGIONS]
area_labels = {f"{area_type} {nr}": (area_type, nr) for area_type, nr in expected_regions}


# ---------------------------------------------------------------------------------------------
# 1. The database connection: a button to test it, a line with the latest result, and the details.
#    The test runs automatically when the app is loaded (streamlit_app.py), and again with the button.
#    The details open by themselves after a manual test, or if the connection failed
# ---------------------------------------------------------------------------------------------
st.subheader("Database connection")

# The test runs as a callback (on_click), so it is done before the page is drawn,
# and the status read here is already the new one
status = st.session_state["mongo_status"]
tested_at = f"{status['tested_at']:%d.%m.%Y %H:%M:%S}"
tested_how = "manually" if status["manual"] else "automatically on load"

button_column, status_column = st.columns([1, 4], vertical_alignment="center")
with button_column:
    st.button("Test connection", on_click=run_connection_test, kwargs={"manual": True}, key="home_test_connection")
with status_column:
    if status["connected"]:
        st.success(f"Connected to MongoDB. Last tested {tested_how}: {tested_at}.")
    else:
        st.error(f"Not connected to MongoDB. Last tested {tested_how}: {tested_at}.")

details = status["details"]
with st.expander("Connection details" if status["connected"] else "Connection error",
                 expanded=status["manual"] or not status["connected"]):
    if not status["connected"]:
        st.error(f"Could not connect to MongoDB: {details}")
        st.caption("Check the secrets (.streamlit/secrets.toml, or Settings → Secrets on Streamlit Cloud), "
                   "and that this computer's IP address is allowed under Network Access in MongoDB Atlas.")
    else:
        st.write("The server answered and the login worked.")
        st.write("Collections:", details["collections"] if details["collections"] else "none yet")
        # Being connected doesn't mean the data is there, so the collection the Cross-border page reads is checked too
        if details["flow_documents"]:
            st.success(f"Cross-border data found: {details['flow_documents']:,} documents in `{FLOWS_COLLECTION}`.")
        else:
            st.warning(f"No documents in `{FLOWS_COLLECTION}`. Fetch them on the Cross-border flow page.")


# ---------------------------------------------------------------------------------------------
# 2. Check all data sources at once, or refresh every cache. Pressing either opens the download box below.
#    The check result is kept until the next check, so it stays when other buttons are clicked.
#    The weather is read fresh from MongoDB, not from the cache
# ---------------------------------------------------------------------------------------------
st.subheader("Data status")


# Opens the download box below. Called by both buttons
def open_download_box():
    st.session_state["home_open_download"] = True


# Refreshes every cache, and opens the download box
def refresh_everything():
    refresh_data()
    open_download_box()


# Fetches the newest reservoir week, and throws away the check, which is now out of date
def fetch_new_week():
    refresh_reservoirs()
    st.session_state.pop("home_check_all", None)


check_column, refresh_column = st.columns([1, 4], vertical_alignment="center")
with check_column:
    if st.button("Check all data sources", type="primary", key="home_check_all_button", on_click=open_download_box,
                 help="Checks the reservoir data (NVE), the cross-border flow (MongoDB) and the weather (MongoDB)"):
        st.session_state["home_check_all"] = {
            "reservoirs": check_reservoirs(),
            "crossborder": check_crossborder() if status["connected"] else None,
            "weather": fresh_stored_weather() if status["connected"] else None,
            "checked_at": pd.Timestamp.now(tz="Europe/Oslo"),
        }
with refresh_column:
    if st.button("Refresh all cached data", on_click=refresh_everything, key="home_refresh_all",
                 help="Fetches everything again from NVE and MongoDB, instead of waiting for the one-hour cache"):
        st.toast("Data refreshed.", icon="🔄")

checked = st.session_state.get("home_check_all")
if checked is None:
    st.caption("Press *Check all data sources* to see whether all the data has arrived and is up to date.")
else:
    st.caption(f"Checked {checked['checked_at']:%d.%m.%Y %H:%M:%S}.")
    reservoir_column, flow_column, weather_column = st.columns(3)

    # Reservoir levels: up to date, or a newer week to fetch
    with reservoir_column, st.container(border=True):
        st.markdown("**Reservoir levels (NVE)**")
        result = checked["reservoirs"]
        if not result["available"]:
            st.warning("NVE's API did not answer.")
        elif result["newer_expected"]:
            st.info(f"Up to the week ending {result['latest_week']:%d.%m.%Y}. A newer week is probably published.")
            st.button("Fetch the new week", on_click=fetch_new_week, key="home_fetch_new_week")
        else:
            st.success(f"Up to date: the week ending {result['latest_week']:%d.%m.%Y}. "
                       f"Next: {result['next_publication']:%d.%m.%Y %H:%M}.")

    # Cross-border flow: what is stored. Downloaded by the Oblig2 notebook
    with flow_column, st.container(border=True):
        st.markdown("**Cross-border flow (MongoDB)**")
        result = checked["crossborder"]
        if result is None:
            st.warning("Not connected to MongoDB.")
        elif not result["available"]:
            st.warning("No data stored yet.")
        else:
            (first_year, first_month), (last_year, last_month) = result["period"]
            st.success(f"{calendar.month_name[first_month]} {first_year} to {calendar.month_name[last_month]} {last_year}.")
            st.caption("Fetch new data on the Cross-border flow page.")

    # Weather: how many of the areas are stored and complete for the newest complete year, with the default
    # number of locations, and whether any stored document is incomplete
    with weather_column, st.container(border=True):
        st.markdown("**Weather (MongoDB)**")
        stored = checked["weather"]
        if stored is None:
            st.warning("Not connected to MongoDB.")
        else:
            newest_year = weather_years()[0]
            for_year = stored[(stored["year"] == newest_year) & (stored["points_per_area"] == DEFAULT_POINTS) & stored["complete"]]
            complete = len(set(zip(for_year["area_type"], for_year["area_nr"])) & set(expected_regions))
            message = f"{complete} of {len(expected_regions)} areas complete for {newest_year} ({DEFAULT_POINTS} locations)."
            if complete == len(expected_regions):
                st.success(message)
            else:
                st.info(message + " Download the rest below.")

            incomplete = stored[~stored["complete"]]
            if not incomplete.empty:
                st.warning(f"{len(incomplete)} stored area-years are incomplete (other variables or settings). "
                           "Choose them below and download them again.")


# ---------------------------------------------------------------------------------------------
# 3. Download weather data, in a box that opens when one of the two buttons above is pressed.
#    Choose the areas, the years and the number of locations. The bars show what is stored for that number,
#    and the panel below checks what is missing and downloads it
# ---------------------------------------------------------------------------------------------
with st.expander("Download weather data", expanded=st.session_state.get("home_open_download", False)):
    if not status["connected"]:
        st.warning("Not connected to MongoDB, so the weather data can't be read or stored. See *Database connection* above.")
    else:
        areas_column, years_column, points_column = st.columns(3)

        # One checkbox per area, in two groups, with All and None above them. Every area starts ticked
        with areas_column:
            st.markdown("**Areas**")
            area_keys = {label: f"home_weather_area_{label.replace(' ', '_')}" for label in area_labels}
            for key in area_keys.values():
                st.session_state.setdefault(key, True)

            # Ticks or unticks every box. Runs as a callback, i.e. before the checkboxes are drawn
            def set_all_areas(value):
                for key in area_keys.values():
                    st.session_state[key] = value

            all_button, none_button = st.columns(2)
            all_button.button("All", on_click=set_all_areas, args=(True,), key="home_weather_areas_all", width="stretch")
            none_button.button("None", on_click=set_all_areas, args=(False,), key="home_weather_areas_none", width="stretch")

            price_column, watercourse_column = st.columns(2)
            with price_column:
                st.caption("Price areas")
                for label in area_labels:
                    if label.startswith("EL"):
                        st.checkbox(label, key=area_keys[label])
            with watercourse_column:
                st.caption("Watercourse areas")
                for label in area_labels:
                    if label.startswith("VASS"):
                        st.checkbox(label, key=area_keys[label])

            chosen_labels = [label for label, key in area_keys.items() if st.session_state[key]]

        with years_column:
            st.markdown("**Years**")
            all_years = st.checkbox(f"All years ({weather_years()[-1]} to {weather_years()[0]})", key="home_weather_all_years")
            if all_years:
                chosen_years = weather_years()
            else:
                chosen_years = st.multiselect("Years", options=weather_years(), default=[weather_years()[0]],
                                              key="home_weather_years", label_visibility="collapsed")

        with points_column:
            st.markdown("**Locations**")
            chosen_points = st.select_slider("Random locations per area", options=POINT_OPTIONS, value=DEFAULT_POINTS,
                                             key="home_weather_points")

        # Coverage for the chosen number of locations: one row per area, one bar per stored year.
        # Complete and incomplete documents get different colours
        stored = load_stored_weather()
        stored = stored[stored["points_per_area"] == chosen_points]
        if stored.empty:
            st.caption(f"No weather data stored with {chosen_points:,} locations yet.")
        else:
            coverage = pd.DataFrame({
                "Area": stored["area_type"] + " " + stored["area_nr"].astype(str),
                "Start": pd.to_datetime(stored["year"].astype(str) + "-01-01"),
                "End": pd.to_datetime((stored["year"] + 1).astype(str) + "-01-01"),
                "Year": stored["year"].astype(str),
                "Status": stored["complete"].map({True: "Complete", False: "Incomplete"}),
            })
            fig = px.timeline(coverage, x_start="Start", x_end="End", y="Area", color="Status", hover_data={"Year": True},
                              color_discrete_map={"Complete": "#2a78d6", "Incomplete": "#eb6834"},
                              title=f"Stored weather data per area and year ({chosen_points:,} locations)")
            # All areas are shown, also those without data, in a fixed order from the top
            fig.update_yaxes(categoryorder="array", categoryarray=list(area_labels)[::-1], title=None)
            fig.update_xaxes(dtick="M12", tickformat="%Y", title=None)
            fig.update_layout(height=340, margin=dict(t=50, b=20))
            st.plotly_chart(fig, width="stretch")

        if not chosen_labels or not chosen_years:
            st.info("Choose at least one area and one year.")
        else:
            chosen_regions = [area_labels[label] for label in chosen_labels]
            weather_panel("home", chosen_regions, sorted(chosen_years), chosen_points)