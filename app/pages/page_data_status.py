import pandas as pd
import plotly.express as px
import streamlit as st

from utils.data import (
    DEFAULT_POINTS, FLOWS_COLLECTION, LAST_DOWNLOAD, POINT_OPTIONS, check_crossborder, check_currency,
    check_reservoirs, download_crossborder, fresh_stored_weather, load_reservoir_data, load_stored_weather,
    refresh_data, refresh_rates, refresh_reservoirs, run_connection_test, weather, weather_years,
)
from utils.updates import crossborder_panel, weather_panel

st.title("Data status")
st.write("The one place to see and fetch all the data: whether the database answers, how new the data from each "
         "source is, when it was last downloaded, and downloads of what is missing.")

# All areas that can have weather data: EL 1-5 and VASS 1-3 (no weather polygon for all of Norway).
# Taken from ind320.weather, not from the reservoir data, so the list is right even when NVE doesn't answer
expected_regions = [weather.parse_region_id(region) for region in weather.ALL_REGIONS]
area_labels = {f"{area_type} {nr}": (area_type, nr) for area_type, nr in expected_regions}


# A time as text, in Norwegian time, or a fallback when it isn't known
def as_time(timestamp, fallback="Not known"):
    if timestamp is None or pd.isna(timestamp):
        return fallback
    timestamp = pd.Timestamp(timestamp)
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_convert("Europe/Oslo")
    return f"{timestamp:%d.%m.%Y %H:%M}"


# ---------------------------------------------------------------------------------------------
# 1. The database connection: a button to test it, a line with the latest result, and the details.
#    The test runs automatically when the app is loaded (streamlit_app.py), and again with the button.
#    The details open by themselves after a manual test, or if the connection failed
# ---------------------------------------------------------------------------------------------
st.subheader("Database connection")

# The test runs as a callback (on_click), so it is done before the page is drawn,
# and the status read here is already the new one
status = st.session_state["mongo_status"]
connected = status["connected"]
tested_at = f"{status['tested_at']:%d.%m.%Y %H:%M:%S}"
tested_how = "manually" if status["manual"] else "automatically on load"

button_column, status_column = st.columns([1, 4], vertical_alignment="center")
with button_column:
    st.button("Test connection", on_click=run_connection_test, kwargs={"manual": True}, key="home_test_connection")
with status_column:
    if connected:
        st.success(f"Connected to MongoDB. Last tested {tested_how}: {tested_at}.")
    else:
        st.error(f"Not connected to MongoDB. Last tested {tested_how}: {tested_at}.")

details = status["details"]
with st.expander("Connection details" if connected else "Connection error", expanded=status["manual"] or not connected):
    if not connected:
        st.error(f"Could not connect to MongoDB: {details}")
        st.caption("Check the secrets (.streamlit/secrets.toml, or Settings, Secrets on Streamlit Cloud), "
                   "and that this computer's IP address is allowed under Network Access in MongoDB Atlas.")
    else:
        st.write("The server answered and the login worked.")
        st.write("Collections:", details["collections"] if details["collections"] else "none yet")
        # Being connected doesn't mean the data is there, so the collection the Cross-border page reads is checked too
        if details["flow_documents"]:
            st.success(f"Cross-border data found: {details['flow_documents']:,} documents in `{FLOWS_COLLECTION}`.")
        else:
            st.warning(f"No documents in `{FLOWS_COLLECTION}`. Fetch them under Data sources below.")


# ---------------------------------------------------------------------------------------------
# 2. Data sources: one card per source with its status, how new its data is and when it was last downloaded.
#    The check runs by itself when the page is opened (and again with "Check all sources"): it asks each source
#    or MongoDB directly. "Fetch latest from all sources" downloads what is new, then checks again.
#    The weather is only checked there, since a year for all areas takes 1-1.5 hours: it has its own box below
# ---------------------------------------------------------------------------------------------
st.subheader("Data sources")


# Checks every source. Each check is caught on its own, so one source that doesn't answer doesn't stop the others
def check_all_sources():
    results = {"checked_at": pd.Timestamp.now(tz="Europe/Oslo")}

    def safely(check):
        try:
            return check()
        except Exception as error:   # the network, the API, MongoDB...
            return {"available": False, "error": str(error)}

    results["nve"] = safely(check_reservoirs)
    results["norgesbank"] = safely(check_currency)
    results["entsoe"] = safely(check_crossborder) if connected else None
    results["weather"] = safely(fresh_stored_weather) if connected else None
    return results


# Downloads the newest data from every source that can be fetched quickly, one step at a time in a status box,
# then checks everything again. A source that fails is reported in the box, and the others still run
def fetch_all_sources():
    with st.status("Fetching the latest data from all sources...", expanded=True) as box:
        st.write("NVE: downloading the reservoir statistics again...")
        refresh_reservoirs()
        load_reservoir_data()

        st.write("Norges Bank: clearing the cached rates, so the Currency page fetches them again...")
        refresh_rates()

        if not connected:
            st.write("ENTSO-E and Open-Meteo: skipped, not connected to MongoDB.")
        else:
            st.write("ENTSO-E: checking the newest stored hour...")
            try:
                result = check_crossborder()
                if not result["has_token"]:
                    st.write("ENTSO-E: skipped, the app has no ENTSO-E token.")
                elif result["newer_expected"]:
                    bar = st.progress(0.0, text="Fetching from ENTSO-E...")
                    start, end, n_documents = download_crossborder(
                        progress=lambda done, total: bar.progress(done / total, text=f"{done} of {total} series"))
                    st.write(f"ENTSO-E: fetched {start:%d.%m.%Y} to {end:%d.%m.%Y}, {n_documents} monthly documents.")
                else:
                    st.write("ENTSO-E: already up to date.")
            except Exception as error:
                st.write(f"ENTSO-E: could not fetch: {error}")
            st.write("Open-Meteo: checked below. Missing years are downloaded in the weather box, "
                     "since a year for all areas takes 1-1.5 hours.")

        st.write("Checking all sources again...")
        st.session_state["data_status_check"] = check_all_sources()
        box.update(label="Fetched the latest data from all sources", state="complete", expanded=False)


# Opens the weather download box below
def open_download_box():
    st.session_state["home_open_download"] = True

# Opens the cross-border download box below
def open_flow_box():
    st.session_state["data_status_open_flow"] = True

check_column, fetch_column, refresh_column = st.columns([1, 1.3, 3], vertical_alignment="center")
with check_column:
    check_now = st.button("Check all sources", key="data_status_check_button",
                          help="Asks every source again how new its data is. Free and quick")
with fetch_column:
    fetch_now = st.button("Fetch latest from all sources", type="primary", key="data_status_fetch_all",
                          help="Downloads NVE again, fresh rates from Norges Bank and new cross-border flow from ENTSO-E")
with refresh_column:
    if st.button("Clear all cached data", on_click=refresh_data, key="home_refresh_all",
                 help="Throws away everything the app has cached, so every page reads its data fresh"):
        st.toast("Cached data cleared.")

if fetch_now:
    fetch_all_sources()
elif check_now or "data_status_check" not in st.session_state:
    with st.spinner("Checking all data sources..."):
        st.session_state["data_status_check"] = check_all_sources()

checked = st.session_state["data_status_check"]
st.caption(f"Last checked {as_time(checked['checked_at'])}.")

STATUS = {
    "ok": ":green[● Up to date]",
    "newer": ":orange[● Newer data available]",
    "incomplete": ":orange[● Not complete]",
    "error": ":red[● Not reachable]",
    "offline": ":red[● Database not connected]",
}

nve_column, weather_column, entsoe_column, bank_column = st.columns(4)

# NVE: an API, the app keeps a copy in its cache for an hour. New week every Wednesday at 13:00
with nve_column, st.container(border=True, height="stretch"):
    st.markdown("**Reservoirs (NVE)**")
    st.caption("Weekly filling degree since 1995, straight from NVE's API.")
    result = checked["nve"]
    if not result.get("available"):
        st.markdown(STATUS["error"])
        if result.get("error"):
            st.caption(result["error"])
    else:
        st.markdown(STATUS["newer"] if result["newer_expected"] else STATUS["ok"])
        st.markdown(f"Data up to: **week ending {result['latest_week']:%d.%m.%Y}**")
        st.markdown(f"Next publication: **{as_time(result['next_publication'])}**")
    st.markdown(f"Last downloaded: **{as_time(LAST_DOWNLOAD.get('nve'), 'Not since the app started')}**")
    if st.button("Fetch now", key="data_status_fetch_nve"):
        refresh_reservoirs()
        load_reservoir_data()
        st.session_state["data_status_check"] = check_all_sources()
        st.rerun()

# Open-Meteo: stored in MongoDB per area and year. Complete when every area has the newest complete year
with weather_column, st.container(border=True, height="stretch"):
    st.markdown("**Weather (Open-Meteo)**")
    st.caption(f"Hourly ERA5 weather per area, stored in MongoDB ({DEFAULT_POINTS} locations per area).")
    stored = checked["weather"]
    if stored is None:
        st.markdown(STATUS["offline"])
    elif isinstance(stored, dict):
        st.markdown(STATUS["error"])
        st.caption(stored.get("error", ""))
    else:
        complete = stored[(stored["points_per_area"] == DEFAULT_POINTS) & stored["complete"]]
        areas_per_year = complete.groupby("year").apply(lambda group: len(set(zip(group["area_type"], group["area_nr"]))))
        full_years = sorted(int(year) for year, n in areas_per_year.items() if n == len(expected_regions))
        newest_year = weather_years()[0]
        newest_complete = int(areas_per_year.get(newest_year, 0))

        st.markdown(STATUS["ok"] if newest_complete == len(expected_regions) else STATUS["incomplete"])
        st.markdown(f"All areas stored: **{', '.join(map(str, full_years)) if full_years else 'no year yet'}**")
        st.markdown(f"{newest_year}: **{newest_complete} of {len(expected_regions)} areas**")
        last_stored = pd.to_datetime(stored["stored_at"], utc=True).max() if not stored.empty else None
        st.markdown(f"Last downloaded: **{as_time(last_stored)}**")
        incomplete = stored[~stored["complete"]]
        if not incomplete.empty:
            st.caption(f"{len(incomplete)} stored area-years are incomplete. Download them again in the box below.")
    st.button("Download weather", key="data_status_open_weather", on_click=open_download_box,
              help="Opens the weather download box below", disabled=not connected)

# ENTSO-E: stored in MongoDB per connection, month and direction. Behind if the last hour is over 3 hours old
with entsoe_column, st.container(border=True, height="stretch"):
    st.markdown("**Cross-border flow (ENTSO-E)**")
    st.caption("Hourly power flow on the 9 connections to the neighbouring countries, stored in MongoDB.")
    result = checked["entsoe"]
    if result is None:
        st.markdown(STATUS["offline"])
    elif result.get("error"):
        st.markdown(STATUS["error"])
        st.caption(result["error"])
    elif not result["available"]:
        st.markdown(STATUS["incomplete"])
        st.markdown("Nothing stored yet.")
    else:
        (first_year, first_month), _ = result["period"]
        st.markdown(STATUS["newer"] if result["newer_expected"] else STATUS["ok"])
        st.markdown(f"Stored from: **{first_month:02d}.{first_year}**")
        st.markdown(f"Data up to: **{as_time(result['last_hour'])}**")
        st.markdown(f"Last downloaded: **{as_time(result.get('stored_at'), 'Before this was recorded')}**")
        if not result["has_token"]:
            st.caption("The app has no ENTSO-E token, so it can't fetch new data.")
    st.button("Download cross-border flow", key="data_status_open_flow_button", on_click=open_flow_box,
              help="Opens the cross-border download box below", disabled=not connected)

# Norges Bank: an API, asked directly by the check. A new rate every business day at about 16:00
with bank_column, st.container(border=True, height="stretch"):
    st.markdown("**Currency (Norges Bank)**")
    st.caption("Daily EUR and USD rates, straight from Norges Bank's API.")
    result = checked["norgesbank"]
    if not result.get("available"):
        st.markdown(STATUS["error"])
        if result.get("error"):
            st.caption(result["error"])
    else:
        st.markdown(STATUS["ok"])
        st.markdown(f"Latest rate: **{result['latest_day']:%d.%m.%Y}**")
        st.caption("New rates every business day at about 16:00.")
    st.markdown(f"Last downloaded: **{as_time(LAST_DOWNLOAD.get('norgesbank'), 'Not since the app started')}**")
    if st.button("Fetch now", key="data_status_fetch_bank"):
        refresh_rates()
        st.session_state["data_status_check"] = check_all_sources()
        st.rerun()

# The cross-border download has a progress bar, so it uses the same panel as the Cross-border flow page
with st.expander("Fetch cross-border flow (ENTSO-E)", expanded=st.session_state.get("data_status_open_flow", False)):
    crossborder_panel("data_status")
# ---------------------------------------------------------------------------------------------
# 3. Download weather data, in a box that opens with the weather card's button.
#    Choose the areas, the years and the number of locations. The bars show what is stored for that number,
#    and the panel below checks what is missing and downloads it
# ---------------------------------------------------------------------------------------------
with st.expander("Download weather data", expanded=st.session_state.get("home_open_download", False)):
    if not connected:
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