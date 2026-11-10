import calendar
import math

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

from utils.data import (
    FLOWS_COLLECTION, available_area_numbers, download_and_store_all_weather, load_flow_period, load_reservoir_data,
    load_stored_weather, openmeteo, refresh_data, run_connection_test, weather_bulk_cost, weather_years,
)

st.title("Reservoir dashboard")
st.header("Home")
st.write("This is a dashboard for visualizing reservoir data." )


st.subheader("Pages:")
st.markdown("""
- *Reservoir Data*: View imported data. One row per area, with line charts for each variable.
- *Reservoir Plot*: Compare the areas over time in one plot.
- *Seasonality & Spectrum*: How the filling degree of one area is built up: STL decomposition and spectrogram.
- *Weather Outliers*: Hourly weather for one area and year: outliers in the precipitation (SPC) and anomalies in the temperature (LOF).
- *Cross-border flow*: Power flows between Norway and its neighbours (ENTSO-E, from MongoDB).
- *About*: Where the data come from, how they are processed, known limitations and the app version.

The type of area, the areas and the period are chosen in the sidebar on the pages that use them, and are shared between those pages.
""")


st.info("This dashboard is a work in progress. More features will be added in the future.")

# The result of the last connection test to MongoDB. The test runs when the page is loaded (streamlit_app.py),
# and again when the button below is clicked. Used by both boxes below
status = st.session_state["mongo_status"]
tested_at = f"{status['tested_at']:%d.%m.%Y %H:%M:%S}"

# ---------------------------------------------------------------------------------------------
# Data status: one line per source, and a summary of whether all the data has arrived.
# The summary is worked out first, so it can be shown in the heading of the box
# ---------------------------------------------------------------------------------------------

reservoir = load_reservoir_data()   # shows an error itself if NVE can't be reached
flow_period = load_flow_period() if status["connected"] else None
stored_weather = load_stored_weather() if status["connected"] else pd.DataFrame()

# All areas that should have weather data: EL 1-5 and VASS 1-3 (no weather polygon for all of Norway)
expected_regions = [("EL", nr) for nr in available_area_numbers("EL")] + [("VASS", nr) for nr in available_area_numbers("VASS")]

# Weather counts as arrived when every area is stored for the newest year, through 31 December
weather_complete = False
if not stored_weather.empty:
    newest_year = int(stored_weather["year"].max())
    newest = stored_weather[stored_weather["year"] == newest_year]
    stored_regions = set(zip(newest["area_type"], newest["area_nr"]))
    last_hour = pd.Timestamp(newest["last_hour"].min())
    year_complete = last_hour >= pd.Timestamp(f"{newest_year}-12-31 23:00")
    weather_complete = stored_regions >= set(expected_regions) and year_complete

missing = []
if reservoir.empty:
    missing.append("reservoir levels")
if flow_period is None:
    missing.append("cross-border flow")
if not weather_complete:
    missing.append("weather")

with st.expander(f"Data status {'✅' if not missing else '⚠️'}"):
    if missing:
        st.warning(f"Some data has not arrived yet: {', '.join(missing)}. See below.")
    else:
        st.success("All data sources have data.")

    # on_click clears the cache before the page is drawn, so the data below is fetched again in the same run
    if st.button("Refresh data", on_click=refresh_data, help="Fetches the data again from NVE and MongoDB, instead of waiting for the one-hour cache"):
        st.toast("Data refreshed.", icon="🔄")

    # Reservoir levels (NVE's API, fetched live)
    if not reservoir.empty:
        latest = reservoir.iloc[-1]
        st.markdown(
            f"**Reservoir levels (NVE):** the latest data is week {latest['iso_week']} of {latest['iso_aar']} "
            f"(ending {reservoir.index[-1]:%d.%m.%Y}). Next publication: {latest['next_publishing_date']:%d.%m.%Y}."
        )

    # Cross-border flow (MongoDB, stored by the Oblig2 notebook)
    if not status["connected"]:
        st.markdown("**Cross-border flow (MongoDB):** not available. See *Database connection* below.")
    elif flow_period is None:
        st.markdown("**Cross-border flow (MongoDB):** no data yet.")
    else:
        (first_year, first_month), (last_year, last_month) = flow_period
        st.markdown(
            f"**Cross-border flow (MongoDB):** {calendar.month_name[first_month]} {first_year} "
            f"to {calendar.month_name[last_month]} {last_year}."
        )

        # Weather (MongoDB, downloaded on the Weather Outliers page or from the Oblig3 notebook)
    if not status["connected"]:
        st.markdown("**Weather (MongoDB):** not available. See *Database connection* below.")
    elif stored_weather.empty:
        st.markdown("**Weather (MongoDB):** no data yet.")
    else:
        stored_labels = ", ".join(f"{area_type} {nr}" for area_type, nr in sorted(stored_regions))
        st.markdown(
            f"**Weather (MongoDB):** {len(stored_regions & set(expected_regions))} of {len(expected_regions)} areas "
            f"stored for {newest_year} ({stored_labels}), through {last_hour:%d.%m.%Y %H:%M} UTC."
        )

    # Weather is downloaded on the Weather Outliers page, one area and year at a time, when it is chosen there.
    st.page_link("pages/page_weather.py", label="Download weather data for an area and year on Weather Outliers", icon="🌦️")

# ---------------------------------------------------------------------------------------------
# Weather data: what is stored (one bar per area and year), and a download of all missing areas for a chosen year
# ---------------------------------------------------------------------------------------------
with st.expander("Weather data"):
    if not status["connected"]:
        st.warning("Not connected to MongoDB, so the weather data can't be read or stored. See *Database connection* below.")
    else:
        area_labels = [f"{area_type} {nr}" for area_type, nr in expected_regions]

        # Coverage: one row per area, one bar per stored year
        if stored_weather.empty:
            st.caption("No weather data stored yet.")
        else:
            coverage = pd.DataFrame({
                "Area": stored_weather["area_type"] + " " + stored_weather["area_nr"].astype(str),
                "Start": pd.to_datetime(stored_weather["year"].astype(str) + "-01-01"),
                "End": pd.to_datetime((stored_weather["year"] + 1).astype(str) + "-01-01"),
                "Year": stored_weather["year"].astype(str),
            })
            fig = px.timeline(coverage, x_start="Start", x_end="End", y="Area", hover_data={"Year": True},
                              title="Stored weather data per area and year")
            fig.update_traces(marker_color="#2a78d6")
            # All areas are shown, also those without data, in a fixed order from the top
            fig.update_yaxes(categoryorder="array", categoryarray=area_labels[::-1], title=None)
            fig.update_xaxes(dtick="M12", tickformat="%Y", title=None)
            fig.update_layout(height=320, margin=dict(t=50, b=20))
            st.plotly_chart(fig, width="stretch")

        # Download of all missing areas for one year
        year = st.selectbox("Year to complete", weather_years(), key="home_weather_year")
        stored_for_year = set(zip(
            stored_weather.loc[stored_weather["year"] == year, "area_type"],
            stored_weather.loc[stored_weather["year"] == year, "area_nr"],
        )) if not stored_weather.empty else set()
        missing_regions = [region for region in expected_regions if region not in stored_for_year]

        if not missing_regions:
            st.success(f"All {len(expected_regions)} areas are stored for {year}.")
        else:
            n_cells, calls, minutes = weather_bulk_cost(missing_regions, year)
            missing_labels = ", ".join(f"{area_type} {nr}" for area_type, nr in missing_regions)
            st.info(
                f"**{len(missing_regions)} areas missing for {year}:** {missing_labels}.\n\n"
                f"Downloading them takes about {math.ceil(minutes) + 1} minutes ({n_cells} unique grid cells, "
                f"about {calls:,.0f} of the free API's {openmeteo.CALLS_PER_DAY:,} calls per day). "
                "Grid cells shared by two areas are downloaded once. Stay on this page while it downloads. "
                "If a limit is reached, the downloaded cells are kept, and the next click continues from there."
            )

            if st.button(f"Download all missing areas for {year}", type="primary"):
                bar = st.progress(0.0, text="Starting the download...")

                def show_progress(done, total):
                    bar.progress(done / total, text=f"{done} of {total} grid cells downloaded")

                try:
                    download_and_store_all_weather(missing_regions, year, progress=show_progress)
                except openmeteo.RateLimitError as error:
                    st.warning(f"The API limit is reached: {error}")
                    st.stop()
                except (openmeteo.OpenMeteoError, requests.RequestException) as error:
                    st.error(f"Could not download from Open-Meteo: {error}")
                    st.stop()

                st.toast(f"All missing areas for {year} are downloaded and stored.", icon="✅")
                st.rerun()

with st.expander("Database connection", expanded=not status["connected"]):   # opens by itself if the test failed
    button_column, box_column = st.columns([1, 3], vertical_alignment="center")

    with button_column:
        # kwargs passes manual=True to run_connection_test, so the result remembers that it was a manual test.
        # st.button returns True in the run right after it was clicked, so the toast only shows after a manual test
        if st.button("Test connection", on_click=run_connection_test, kwargs={"manual": True}):
            if status["connected"]:
                st.toast(f"Connection tested: {tested_at}. Connected.", icon="✅")
            else:
                st.toast(f"Connection tested: {tested_at}. Not connected.", icon="❌")

    # Box to the right of the button, shown as long as the last test was a manual one (gone after a reload)
    with box_column:
        if status["manual"]:
            if status["connected"]:
                st.success(f"Manually tested: {tested_at}. Connected.")
            else:
                st.error(f"Manually tested: {tested_at}. Not connected.")

    details = status["details"]
    if not status["connected"]:
        st.error(f"Connection tested: {tested_at}. Could not connect to MongoDB: {details}")
    else:
        st.success(f"Connection tested: {tested_at}. Connected to MongoDB (the server answered and the login worked).")
        st.write("Collections:", details["collections"] if details["collections"] else "none yet")
        # Being connected doesn't mean the data is there, so the collection the Cross-border page reads is checked too
        if details["flow_documents"]:
            st.success(f"Cross-border data found: {details['flow_documents']:,} documents in `{FLOWS_COLLECTION}`.")
        else:
            st.warning(f"No documents in `{FLOWS_COLLECTION}`. Run the ENTSO-E part of the notebook first.")