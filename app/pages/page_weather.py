import streamlit as st

from utils.controls import area_type_selector, single_area_selector, year_selector
from utils.data import anomalies, available_area_numbers, available_weather_years, load_region_weather

st.title("Weather Outliers")
st.write(
    "Hourly weather for one area and one year (ERA5 via Open-Meteo), averaged over the area. "
    "Outliers in the precipitation are found with SPC, and anomalies in the temperature with LOF."
)
st.caption(
    "The area starts from the choice in the sidebar, but can be changed here without changing the sidebar. "
    "The period in the sidebar is not used: the analyses use one whole year."
)

# The weather data is stored in MongoDB, so nothing can be shown without the connection
if not st.session_state["mongo_status"]["connected"]:
    st.warning("Not connected to MongoDB, so the weather data can't be read. See *Database connection* on Home.")
    st.stop()

# Local choices. The area type has no NO, since there is no weather polygon for all of Norway.
# The page's own memory key makes it start from the global type without changing it
left, middle, right = st.columns(3)
with left:
    area_type = area_type_selector("weather", allowed=["EL", "VASS"], memory_key="weather_area_type_memory")
with middle:
    area_nr = single_area_selector("weather", area_type, available_area_numbers(area_type))
label = f"{area_type} {area_nr}"

years = available_weather_years(area_type, area_nr)
if not years:
    st.info(f"No weather data stored for {label} yet. For now it is downloaded and stored from the notebook (Oblig3).")
    st.stop()
with right:
    year = year_selector("weather", years)

data = load_region_weather(area_type, area_nr, year)
if data is None or data.empty:
    st.warning(f"Could not load the weather data for {label} {year}.")
    st.stop()

st.caption(f"{label} {year}: {len(data):,} hours, {data.index[0]:%d.%m.%Y %H:%M} to {data.index[-1]:%d.%m.%Y %H:%M} (UTC).")

spc_tab, lof_tab = st.tabs(["Outliers: precipitation (SPC)", "Anomalies: temperature (LOF)"])

# ---------------------------------------------------------------------------------------------
# SPC on the precipitation: DCT high-pass filter, robust boundaries from the whole year
# ---------------------------------------------------------------------------------------------
with spc_tab:
    st.write(
        "The slow variation (season) is removed with a DCT high-pass filter. The boundaries are the median "
        "± a number of robust standard deviations of what is left, estimated from the whole year, with the "
        "season added back, so they follow it in the plot. Points outside are outliers."
    )

    left, right = st.columns(2)
    cutoff_days = left.slider(
        "DCT cut-off (days)", min_value=7, max_value=180, value=30, step=1, key="spc_cutoff",
        help="Variation slower than this counts as season and is removed before the boundaries are found.",
    )
    n_std = right.slider(
        "Number of standard deviations", min_value=1.5, max_value=5.0, value=3.0, step=0.5, key="spc_n_std",
        help="How far from the median a value must be to count as an outlier. 3 is the classic SPC limit.",
    )

    fig, summary, outliers = anomalies.spc_outliers(
        data["precipitation"], cutoff_days=cutoff_days, n_std=n_std,
        title=f"{label} {year}: hourly precipitation with SPC outliers", unit="mm",
    )
    st.plotly_chart(fig, width="stretch")

    columns = st.columns(4)
    columns[0].metric("Outlier hours", f"{summary['n_outliers']:,}")
    columns[1].metric("Share of the year", f"{summary['share_outliers']:.1%}")
    columns[2].metric("Above / below", f"{summary['n_above']} / {summary['n_below']}")
    columns[3].metric("Robust std", f"{summary['satv_robust_std']:.3f} mm")

    st.caption(
        "Precipitation can't be negative, so the lower boundary is rarely crossed, and the long tail of heavy rain "
        "gives many more outliers than SPC expects for normally distributed data. One rain event can give several "
        "outlier hours in a row."
    )
    with st.expander(f"The {summary['n_outliers']} outlier hours"):
        st.dataframe(outliers.round(3), width="stretch")

# ---------------------------------------------------------------------------------------------
# LOF on the temperature
# ---------------------------------------------------------------------------------------------
with lof_tab:
    st.write(
        "The Local Outlier Factor compares how densely packed each hour's neighbourhood is (in time and temperature) "
        "with its neighbours' neighbourhoods. Hours that stand out from the hours around them are marked as anomalies."
    )

    left, right = st.columns(2)
    contamination_percent = left.slider(
        "Share of anomalies (%)", min_value=0.1, max_value=10.0, value=1.0, step=0.1, key="lof_contamination",
        help="LOF always marks this share of the hours: it ranks the hours, but doesn't decide whether any are unusual.",
    )
    n_neighbors = right.slider(
        "Number of neighbours", min_value=5, max_value=100, value=20, step=1, key="lof_neighbors",
        help="How many nearby hours each hour is compared with.",
    )

    fig, summary, outliers = anomalies.lof_anomalies(
        data["temperature_2m"], contamination=contamination_percent / 100, n_neighbors=n_neighbors,
        title=f"{label} {year}: hourly temperature with LOF anomalies", unit="°C",
    )
    st.plotly_chart(fig, width="stretch")

    columns = st.columns(4)
    columns[0].metric("Anomalies", f"{summary['n_outliers']:,}")
    columns[1].metric("Share of the year", f"{summary['share_outliers']:.1%}")
    columns[2].metric("Coldest / warmest", f"{summary['min_outlier_value']:.1f} / {summary['max_outlier_value']:.1f} °C")
    columns[3].metric("Highest LOF score", f"{summary['max_lof_score']:.2f}")

    with st.expander(f"The {summary['n_outliers']} anomalies, most unusual first"):
        st.dataframe(outliers.round(3), width="stretch")