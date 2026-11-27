import streamlit as st

from utils.about import weather_data_info
from utils.controls import area_type_selector, single_area_selector, year_selector
from utils.data import (
    DEFAULT_POINTS, POINT_OPTIONS, anomalies, available_area_numbers, available_weather_years,
    load_area_shape, load_region_cells, load_region_weather, maps, weather_years,
)
from utils.updates import weather_panel

WEATHER_VARIABLES = {
    "temperature_2m": ("Temperature", "°C"),
    "precipitation": ("Precipitation", "mm"),
    "rain": ("Rain", "mm"),
    "snowfall": ("Snowfall", "cm"),
    "et0_fao_evapotranspiration": ("Evaporation", "mm"),
}
AMOUNTS = {"precipitation", "rain", "snowfall", "et0_fao_evapotranspiration"}
# Dropdown for one weather property. Local: each tab has its own key, so they are remembered separately
def variable_selector(key, default):
    return st.selectbox("Weather property", list(WEATHER_VARIABLES), index=list(WEATHER_VARIABLES).index(default),
                        format_func=lambda v: WEATHER_VARIABLES[v][0], key=key)


st.title("Weather Outliers")
st.write(
    "Hourly weather for one area and one year (ERA5 via Open-Meteo), averaged over the area. "
    "Outliers are found with SPC and anomalies with LOF, for the weather property chosen in each tab."
)
st.caption(
    "The area starts from the choice in the sidebar, but can be changed here without changing the sidebar. "
    "The period in the sidebar is not used: the analyses use one whole year."
)

# The weather data is stored in MongoDB, so nothing can be shown without the connection
if not st.session_state["mongo_status"]["connected"]:
    st.warning("Not connected to MongoDB, so the weather data can't be read. See *Database connection* on Home.")
    st.stop()

# ---------------------------------------------------------------------------------------------
# Local choices: type of area (no NO, since there is no weather polygon for all of Norway), area, number of
# random locations and year. The page's own memory key makes the type start from the global one without changing it
# ---------------------------------------------------------------------------------------------
left, middle, right = st.columns(3)
with left:
    area_type = area_type_selector("weather", allowed=["EL", "VASS"], memory_key="weather_area_type_memory")
with middle:
    area_nr = single_area_selector("weather", area_type, available_area_numbers(area_type))
label = f"{area_type} {area_nr}"

points = st.select_slider(
    "Random locations in the area",
    options=POINT_OPTIONS, value=DEFAULT_POINTS, key="weather_points",
    help="More locations cover the area better, but give more grid cells to download. "
         "Each number is stored separately, so changing it doesn't overwrite anything.",
)

# All complete years can be chosen. The ones stored and complete for this area and number of locations are marked
complete_years = set(available_weather_years(area_type, area_nr, points))
with right:
    year = year_selector(
        "weather", weather_years(),
        format_func=lambda y: f"{y} (stored)" if y in complete_years else str(y),
    )

# ---------------------------------------------------------------------------------------------
# The area on a map with its grid cells, and the "Fetch latest data" panel: it checks whether the chosen
# area, year and number of locations is stored and complete, and if not, downloads it with a progress bar.
# The map changes with the slider before anything is downloaded, so you can see what you would pay for
# ---------------------------------------------------------------------------------------------
with st.spinner("Preparing the map (the first time takes a few seconds)..."):
    shape = load_area_shape(area_type, area_nr)
    cells = load_region_cells(area_type, area_nr, points)

map_column, info_column = st.columns([3, 2], gap="large")

with map_column:
    st.plotly_chart(maps.area_map(shape, cells), width="stretch")
    st.caption("Each dot is an ERA5 grid cell. The bigger the dot, the more of the random locations fell in it, "
               "and the more it counts in the area's average.")

with info_column:
    st.metric("Random locations", f"{points:,}")
    st.metric("ERA5 grid cells", f"{len(cells):,}", help="Locations in the same grid cell get the same weather, "
              "so each cell is downloaded only once.")

    if year in complete_years:
        st.success(f"Weather for **{label} {year}** with {points:,} locations is stored.")
    else:
        st.info(f"Weather for **{label} {year}** with {points:,} locations is not stored, or not complete. "
                "Press *Fetch latest data* below to see what is missing and what it costs.")

# Without complete data there is nothing to analyse yet. The panel is drawn here, since the page stops before the bottom
if year not in complete_years:
    weather_panel("weather", [(area_type, area_nr)], [year], points)
    weather_data_info()
    st.stop()
    
data = load_region_weather(area_type, area_nr, year, points)
if data is None or data.empty:
    st.warning(f"Could not load the weather data for {label} {year}.")
    st.stop()

st.caption(
    f"{label} {year}, {points:,} locations in {len(cells):,} grid cells: {len(data):,} hours, "
    f"{data.index[0]:%d.%m.%Y %H:%M} to {data.index[-1]:%d.%m.%Y %H:%M} (UTC)."
)

spc_tab, lof_tab = st.tabs(["Outliers (SPC)", "Anomalies (LOF)"])

# ---------------------------------------------------------------------------------------------
# SPC: DCT high-pass filter, robust boundaries from the whole year. Temperature by default
# ---------------------------------------------------------------------------------------------
with spc_tab:
    st.write(
        "The slow variation (season) is removed with a DCT high-pass filter. The boundaries are the median "
        "± a number of robust standard deviations of what is left (the seasonally adjusted variation, SATV), "
        "estimated from the whole year, with the season added back, so they follow it in the plot. "
        "Points outside are outliers."
    )

    variable_column, cutoff_column, std_column = st.columns(3)
    with variable_column:
        spc_variable = variable_selector("spc_variable", "temperature_2m")
    spc_name, spc_unit = WEATHER_VARIABLES[spc_variable]
    cutoff_days = cutoff_column.slider(
        "DCT cut-off (days)", min_value=7, max_value=180, value=30, step=1, key="spc_cutoff",
        help="Variation slower than this counts as season and is removed before the boundaries are found.",
    )
    n_std = std_column.slider(
        "Number of standard deviations", min_value=1.5, max_value=5.0, value=3.0, step=0.5, key="spc_n_std",
        help="How far from the median a value must be to count as an outlier. 3 is the classic SPC limit.",
    )

    fig, summary, outliers = anomalies.spc_outliers(
        data[spc_variable], cutoff_days=cutoff_days, n_std=n_std,
        title=f"{label} {year}: hourly {spc_name.lower()} with SPC outliers", unit=spc_unit,
    )
    st.plotly_chart(fig, width="stretch")

    columns = st.columns(4)
    columns[0].metric("Outlier hours", f"{summary['n_outliers']:,}")
    columns[1].metric("Share of the year", f"{summary['share_outliers']:.1%}")
    columns[2].metric("Above / below", f"{summary['n_above']} / {summary['n_below']}")
    columns[3].metric("Robust std", f"{summary['satv_robust_std']:.3f} {spc_unit}")

    # The amounts can't be negative and have long tails, which SPC's symmetric boundaries don't fit well
    if spc_variable in AMOUNTS:
        st.caption(
            f"{spc_name} can't be negative, so the lower boundary is rarely crossed, and the long tail of the "
            "large values gives many more outliers than SPC expects for normally distributed data. One event can "
            "give several outlier hours in a row. Temperature fits SPC better."
        )
    with st.expander(f"The {summary['n_outliers']} outlier hours"):
        st.dataframe(outliers.round(3), width="stretch")


# ---------------------------------------------------------------------------------------------
# LOF: compares each hour's neighbourhood (in time and value) with its neighbours'. Precipitation by default
# ---------------------------------------------------------------------------------------------
with lof_tab:
    st.write(
        "The Local Outlier Factor compares how densely packed each hour's neighbourhood is (in time and value) "
        "with its neighbours' neighbourhoods. Hours that stand out from the hours around them are marked as anomalies."
    )

    variable_column, share_column, neighbours_column = st.columns(3)
    with variable_column:
        lof_variable = variable_selector("lof_variable", "precipitation")
    lof_name, lof_unit = WEATHER_VARIABLES[lof_variable]
    contamination_percent = share_column.slider(
        "Share of anomalies (%)", min_value=0.1, max_value=10.0, value=1.0, step=0.1, key="lof_contamination",
        help="LOF always marks this share of the hours: it ranks the hours, but doesn't decide whether any are unusual.",
    )
    n_neighbors = neighbours_column.slider(
        "Number of neighbours", min_value=5, max_value=100, value=20, step=1, key="lof_neighbors",
        help="How many nearby hours each hour is compared with.",
    )

    fig, summary, outliers = anomalies.lof_anomalies(
        data[lof_variable], contamination=contamination_percent / 100, n_neighbors=n_neighbors,
        title=f"{label} {year}: hourly {lof_name.lower()} with LOF anomalies", unit=lof_unit,
    )
    st.plotly_chart(fig, width="stretch")

    columns = st.columns(4)
    columns[0].metric("Anomalies", f"{summary['n_outliers']:,}")
    columns[1].metric("Share of the year", f"{summary['share_outliers']:.1%}")
    columns[2].metric("Lowest / highest", f"{summary['min_outlier_value']:.1f} / {summary['max_outlier_value']:.1f} {lof_unit}")
    columns[3].metric("Highest LOF score", f"{summary['max_lof_score']:.2f}")

    with st.expander(f"The {summary['n_outliers']} anomalies, most unusual first"):
        st.dataframe(outliers.round(3), width="stretch")

# Checks whether the chosen area, year and number of locations is stored and complete, and downloads it if not
weather_panel("weather", [(area_type, area_nr)], [year], points)

weather_data_info()