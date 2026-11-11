# The "Fetch latest data" panels: a check that is free and instant, and if something is missing, a second
# button that downloads it with a progress bar. One panel per data source, used on the pages and on Home.
#
# A button is only True in the run right after it is clicked, so the result of a check is kept in
# st.session_state until the download button is clicked. The check also remembers what was checked, and is
# thrown away if the selection changes, so a download never uses a check made for another selection

import requests
import streamlit as st

from utils.data import (
    check_crossborder, check_reservoirs, check_weather, download_crossborder, download_missing_weather, openmeteo,
    refresh_reservoirs,
)


# The stored check for one panel, or None if there is none, or if it was made for another selection
def _stored_check(key, request):
    stored = st.session_state.get(key)
    if stored is None or stored["request"] != request:
        return None
    return stored


# ---------------------------------------------------------------------------------------------
# Reservoir data (NVE's API): nothing to download as such, the cache is just cleared and NVE asked again
# ---------------------------------------------------------------------------------------------
def reservoir_panel(key):
    state_key = f"updates_{key}_reservoirs"

    with st.container(border=True):
        if st.button("Fetch latest data", key=f"{state_key}_check",
                     help="Checks whether NVE has published a newer week than the one in the app"):
            st.session_state[state_key] = {"request": None, "result": check_reservoirs()}

        stored = _stored_check(state_key, None)
        if stored is None:
            st.caption("Reservoir data from NVE, published every Wednesday at 13:00.")
            return

        result = stored["result"]
        if not result["available"]:
            st.warning("NVE's API did not answer.")
        elif result["newer_expected"]:
            st.info(
                f"The app has data up to the week ending {result['latest_week']:%d.%m.%Y}. NVE's next publication was "
                f"{result['next_publication']:%d.%m.%Y %H:%M}, so a newer week is probably out."
            )
            if st.button("Download missing", key=f"{state_key}_download", type="primary"):
                refresh_reservoirs()
                del st.session_state[state_key]
                st.rerun()
        else:
            st.success(
                f"Up to date: the latest week ends {result['latest_week']:%d.%m.%Y}. "
                f"The next one is published {result['next_publication']:%d.%m.%Y %H:%M}."
            )


# ---------------------------------------------------------------------------------------------
# Cross-border flow (ENTSO-E, via MongoDB): checks the last hour stored, and fetches what is new from ENTSO-E.
# The app goes straight from ENTSO-E to MongoDB (see ind320.entsoe). The Oblig2 notebook goes through Cassandra and Spark
# ---------------------------------------------------------------------------------------------
def crossborder_panel(key):
    state_key = f"updates_{key}_crossborder"

    with st.container(border=True):
        if not st.session_state["mongo_status"]["connected"]:
            st.warning("Not connected to MongoDB, so the cross-border data can't be checked.")
            return

        if st.button("Fetch latest data", key=f"{state_key}_check",
                     help="Checks the last hour of cross-border flow stored in MongoDB"):
            st.session_state[state_key] = {"request": None, "result": check_crossborder()}

        stored = _stored_check(state_key, None)
        if stored is None:
            st.caption("Cross-border flow from ENTSO-E, stored in MongoDB.")
            return

        result = stored["result"]
        if result["available"]:
            (first_year, first_month), _ = result["period"]
            stored_text = f"Stored from {first_month:02d}.{first_year} to {result['last_hour'].tz_convert('Europe/Oslo'):%d.%m.%Y %H:00}."
        else:
            stored_text = "Nothing is stored yet."

        if not result["newer_expected"]:
            st.success(f"Up to date. {stored_text}")
            return

        behind = f" about {result['behind'].days} days behind" if result["behind"] is not None else ""
        st.info(f"{stored_text} That is{behind}, so there is newer data at ENTSO-E." if behind
                else f"{stored_text} The last two years can be fetched from ENTSO-E.")

        if not result["has_token"]:
            st.warning("The app has no ENTSO-E token, so it can't fetch new data. Add `[entsoe]` with `token = \"...\"` "
                       "to the secrets (.streamlit/secrets.toml, or Settings → Secrets on Streamlit Cloud).")
            return

        st.caption("Fetches all 9 connections in both directions from the start of the newest stored month, "
                   "and replaces those months. Usually under a minute.")
        if st.button("Download missing", key=f"{state_key}_download", type="primary"):
            bar = st.progress(0.0, text="Starting the download...")

            def show_progress(done, total):
                bar.progress(done / total, text=f"{done} of {total} series fetched from ENTSO-E")

            try:
                start, end, n_documents = download_crossborder(progress=show_progress)
            except Exception as error:   # the token, the network, ENTSO-E's own errors...
                st.error(f"Could not fetch from ENTSO-E: {error}")
                return

            del st.session_state[state_key]
            st.toast(f"Fetched {start:%d.%m.%Y} to {end:%d.%m.%Y}: {n_documents} monthly documents stored.", icon="✅")
            st.rerun()

            
# ---------------------------------------------------------------------------------------------
# Weather (Open-Meteo, via MongoDB): checks the given areas, years and number of locations,
# shows what is missing and what it costs, and downloads it with a progress bar
# ---------------------------------------------------------------------------------------------
def weather_panel(key, regions, years, points_per_area):
    state_key = f"updates_{key}_weather"
    request = (tuple(regions), tuple(years), points_per_area)

    with st.container(border=True):
        if not st.session_state["mongo_status"]["connected"]:
            st.warning("Not connected to MongoDB, so the weather data can't be checked or stored.")
            return

        if st.button("Fetch latest data", key=f"{state_key}_check",
                     help="Checks which of the chosen areas and years are stored, and what the rest would cost"):
            missing, cost = check_weather(regions, years, points_per_area)
            st.session_state[state_key] = {"request": request, "missing": missing, "cost": cost}

        stored = _stored_check(state_key, request)
        if stored is None:
            st.caption("Weather from Open-Meteo (ERA5), stored in MongoDB per area, year and number of locations.")
            return

        missing, cost = stored["missing"], stored["cost"]
        if missing.empty:
            st.success(f"Everything is stored: {len(regions) * len(years)} area-years with {points_per_area:,} locations.")
            return

        # What is missing, and why
        table = missing.assign(area=missing["area_type"] + " " + missing["area_nr"].astype(str))
        st.write(f"**{len(missing)} of {len(regions) * len(years)} area-years are missing** "
                 f"({points_per_area:,} locations):")
        st.dataframe(table[["area", "year", "reason"]], hide_index=True, width="stretch")

        # What it costs, and a warning if it is more than one day of the free API
        st.caption(
            f"About {cost['cells']:,} grid cells and {cost['calls']:,.0f} API calls (the free limit is "
            f"{openmeteo.CALLS_PER_DAY:,} per day), about {cost['minutes']:.0f} minutes. "
            "Grid cells shared by several areas in the same year are downloaded once. Stay on this page while it downloads."
        )
        if cost["days"] > 1:
            st.warning(
                f"This is about {cost['days']} days of the free API. It downloads one year at a time and stores each year "
                "when it is done, so when the daily limit is reached it stops, and the next download continues from there."
            )

        if st.button("Download missing", key=f"{state_key}_download", type="primary"):
            bar = st.progress(0.0, text="Starting the download...")

            def show_progress(fraction, text):
                bar.progress(min(max(fraction, 0.0), 1.0), text=text)

            try:
                download_missing_weather(missing, points_per_area, progress=show_progress)
            except openmeteo.RateLimitError as error:
                st.warning(f"The API limit is reached: {error} The years that finished are stored.")
                del st.session_state[state_key]
                return
            except (openmeteo.OpenMeteoError, requests.RequestException) as error:
                st.error(f"Could not download from Open-Meteo: {error}")
                return

            # Done: the check is out of date now, so it is thrown away, and the page is drawn again with the new data
            del st.session_state[state_key]
            st.rerun()