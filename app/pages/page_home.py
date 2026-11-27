import streamlit as st

from utils.data import (
    available_dates, load_area_shapes, load_filling_at, load_filling_series, load_reservoir_period, maps,
)

st.title("Norway's reservoirs, weather and power")
st.write(
    "A dashboard for Norway's hydropower reservoirs: how full they are, how the weather over the price and "
    "watercourse areas fills and empties them, how power flows to and from the neighbouring countries, "
    "and a forecast of the coming months. Made for IND320 (Data til beslutning) at NMBU."
)

# If the database didn't answer when the app was loaded, say so here, with a link to the details.
# The reservoir data (NVE) and the currency (Norges Bank) still work without it
if not st.session_state["mongo_status"]["connected"]:
    st.warning("Not connected to MongoDB, so the weather and cross-border data can't be read right now. "
               "The reservoir data and the currency still work.")
    st.page_link("pages/page_data_status.py", label="See Data status")

# ---------------------------------------------------------------------------------------------
# The teaser: the price areas' filling degree in the latest week on a small map without controls,
# and a few numbers for all of Norway
# ---------------------------------------------------------------------------------------------
weeks = available_dates()
if not weeks:
    st.warning("The reservoir data could not be fetched from NVE right now.")
else:
    latest = weeks[-1]
    st.subheader(f"The reservoirs right now (week ending {latest:%d.%m.%Y})")
    map_column, numbers_column = st.columns([3, 2], gap="large")

    with map_column:
        filling, _ = load_filling_at("EL", latest)
        fig = maps.selection_map(load_area_shapes("EL"), filling, label="Filling degree", zmin=0, zmax=1,
                                 height=420, dark=st.context.theme.type == "dark")
        st.plotly_chart(fig, width="stretch", key="home_teaser",
                        config={"displayModeBar": False, "scrollZoom": False})
        st.page_link("pages/page_map.py", label="Open the full map")

    with numbers_column:
        # All of Norway: the filling degree, the change from last week, and the median for the same ISO week
        # in all earlier years (what is normal for this time of year)
        norway, _ = load_filling_at("NO", latest)
        this_week = load_reservoir_period("NO", [0], latest, latest)
        history = load_filling_series("NO", 0, weeks[0], weeks[-1])
        iso = history.index.isocalendar()
        same_week = history[(iso["week"] == iso["week"].iloc[-1]) & (iso["year"] != iso["year"].iloc[-1])]

        if not norway.empty:
            value = norway.iloc[0]
            change = this_week["filling_degree_change"].iloc[0] if not this_week.empty else None
            st.metric("All of Norway", f"{value:.0%}",
                      delta=f"{change * 100:+.1f} pp from last week" if change is not None else None)
            if not same_week.empty:
                median = same_week.median()
                st.metric("Normal for this week (median since 1995)", f"{median:.0%}",
                          delta=f"{(value - median) * 100:+.1f} pp now vs normal", delta_color="off")

        # The five price areas, smaller
        st.caption("Price areas: " + ", ".join(f"EL {nr} {filling[nr]:.0%}" for nr in sorted(filling.index)))

# ---------------------------------------------------------------------------------------------
# The pages, grouped as in the menu, each with a line about what it shows
# ---------------------------------------------------------------------------------------------
st.subheader("What you can do")
explore, anomalies, predict = st.columns(3)

with explore, st.container(border=True):
    st.markdown("**Explore**")
    st.page_link("pages/page_map.py", label="Map of Norway")
    st.caption("The areas coloured by filling degree or weather, week by week. Click to select an area.")
    st.page_link("pages/page_reservoirs.py", label="Reservoirs")
    st.caption("The filling degree over time, compared between areas, and played week by week on a map.")
    st.page_link("pages/page_cross_border.py", label="Cross-border flow")
    st.caption("Power to and from Sweden, Finland, Denmark, Germany, the Netherlands and Britain.")
    st.page_link("pages/page_currency.py", label="Currency")
    st.caption("EUR and USD in NOK from Norges Bank.")
    st.page_link("pages/page_seasonal.py", label="Seasonality & Spectrum")
    st.caption("How the filling degree is built up: trend, season and the rest.")

with anomalies, st.container(border=True):
    st.markdown("**Anomalies**")
    st.page_link("pages/page_weather.py", label="Weather Outliers")
    st.caption("Unusual hours in the weather of one area and year, found with SPC and LOF.")

with predict, st.container(border=True):
    st.markdown("**Predict**")
    st.page_link("pages/page_correlation.py", label="Weather vs reservoirs")
    st.caption("When and how strongly the weather and the reservoirs move together, with a lag.")
    st.page_link("pages/page_forecast.py", label="Forecast")
    st.caption("The filling degree for the coming months, with SARIMAX and optionally the weather.")

# ---------------------------------------------------------------------------------------------
# Where the data comes from
# ---------------------------------------------------------------------------------------------
st.subheader("Data sources")
st.markdown(
    "- **NVE Magasinstatistikk:** weekly reservoir filling since 1995, straight from NVE's API.\n"
    "- **Open-Meteo (ERA5):** hourly weather, averaged over each area and stored in MongoDB.\n"
    "- **ENTSO-E:** hourly cross-border flows, stored in MongoDB.\n"
    "- **Norges Bank:** daily exchange rates, straight from the API."
)
st.caption("More about the data, how it is processed and its limitations is on About. "
           "What is stored, and downloads of more weather, are on Data status.")