import plotly.express as px
import streamlit as st

from utils.controls import get_global_selection, single_area_selector
from utils.data import (
    correlation, load_reservoir_period, load_weekly_weather, run_lag_correlations, run_sliding_correlation, seasonal,
    weather,
)

st.title("Weather vs reservoirs")
st.write(
    "How one weather property and the reservoirs move together over time. The correlation is computed in a window "
    "that slides one week at a time, so it shows when the relation is strong and when it is weak. "
    "The weather can be lagged, since rain and snowmelt take time to reach the reservoirs."
)

# The reservoir variables. The weather variables come from ind320.weather.VARIABLES
RESERVOIR_VARIABLES = {
    "filling_degree_change": "Change in filling degree from last week",
    "filling_degree": "Filling degree",
}

# The weather is stored in MongoDB
if not st.session_state["mongo_status"]["connected"]:
    st.warning("Not connected to MongoDB, so the weather data can't be read. See Data status.")
    st.stop()

# The global selection: the type of area and the area among those ticked in the sidebar. No weather for NO
selection = get_global_selection()
area_type = selection["area_type"]
if area_type == "NO":
    st.info("There is no weather for all of Norway. Choose price areas (EL) or watercourse areas (VASS) in the sidebar.")
    st.stop()
if not selection["area_numbers"]:
    st.info("No areas selected. Choose one or more areas in the sidebar.")
    st.stop()

# ---------------------------------------------------------------------------------------------
# Controls: the area, the two variables, the lag and the window
# ---------------------------------------------------------------------------------------------
left, middle, right = st.columns(3)
with left:
    area_nr = single_area_selector("correlation", area_type, selection["area_numbers"])
# Precipitation first: what fills the reservoirs
weather_variable = middle.selectbox("Weather property", list(weather.VARIABLES),
                                    index=list(weather.VARIABLES).index("precipitation"),
                                    format_func=lambda v: weather.variable_label(v, weekly=True),
                                    key="correlation_weather")
reservoir_variable = right.selectbox("Reservoir variable", list(RESERVOIR_VARIABLES),
                                     format_func=RESERVOIR_VARIABLES.get, key="correlation_reservoir",
                                     help="The weekly change is the natural one to compare with the weather: "
                                          "a wet week should raise the filling that week.")
left, right = st.columns(2)
lag = left.slider("Lag (weeks)", min_value=0, max_value=12, value=0, key="correlation_lag",
                  help="Compares each week's reservoir value with the weather this many weeks earlier.")
window = right.slider("Window length (weeks)", min_value=4, max_value=52, value=13, key="correlation_window",
                      help="How many weeks each correlation is computed over. Short windows react quickly "
                           "but are noisy, long windows are smoother.")
label = f"{area_type} {area_nr}"

# ---------------------------------------------------------------------------------------------
# The data: weekly weather from MongoDB (all stored complete years), and the reservoir variable from NVE.
# The period is where both exist, within the sidebar's period
# ---------------------------------------------------------------------------------------------
weekly = load_weekly_weather(area_type, area_nr)
if weekly.empty:
    st.warning(f"No complete year of weather is stored for {label}.")
    st.page_link("pages/page_data_status.py", label="Download weather on Data status")
    st.stop()

reservoirs = load_reservoir_period(area_type, [area_nr], selection["start"], selection["end"])
if reservoirs.empty:
    st.warning(f"No reservoir data for {label} in the period chosen in the sidebar.")
    st.stop()
reservoir_series = seasonal.filling_series(reservoirs, area_type, area_nr, column=reservoir_variable)
weather_series = weekly[weather_variable]

try:
    sliding, aligned = run_sliding_correlation(weather_series, reservoir_series, window=window, lag=lag)
except ValueError as error:
    st.warning(f"{error} The weather is stored from {weekly.index[0]:%d.%m.%Y} to {weekly.index[-1]:%d.%m.%Y}, "
               "so check the period in the sidebar.")
    st.stop()

st.caption(f"{label}: {len(aligned)} weeks with both series, {aligned.index[0]:%d.%m.%Y} to "
           f"{aligned.index[-1]:%d.%m.%Y} (where the stored weather and the sidebar's period overlap).")

fig = correlation.correlation_figure(
    sliding, aligned, weather.variable_label(weather_variable, weekly=True), RESERVOIR_VARIABLES[reservoir_variable],
    window, lag,
    title=f"{label}: {weather.VARIABLES[weather_variable]['name'].lower()} vs "
          f"{RESERVOIR_VARIABLES[reservoir_variable].lower()}",
)
st.plotly_chart(fig, width="stretch")

columns = st.columns(3)
columns[0].metric("Correlation over the whole period", f"{aligned['weather'].corr(aligned['reservoir']):+.2f}")
columns[1].metric("Strongest positive window", f"{sliding.max():+.2f}",
                  help=f"The window ending {sliding.idxmax():%d.%m.%Y}.")
columns[2].metric("Strongest negative window", f"{sliding.min():+.2f}",
                  help=f"The window ending {sliding.idxmin():%d.%m.%Y}.")

# ---------------------------------------------------------------------------------------------
# Which lag fits best: the correlation over the whole period for lags 0 to 12 weeks
# ---------------------------------------------------------------------------------------------
with st.expander("Which lag fits best?"):
    by_lag = run_lag_correlations(weather_series, reservoir_series, max_lag=12).reset_index()
    lag_fig = px.bar(by_lag, x="lag_weeks", y="correlation", labels={"lag_weeks": "Lag (weeks)",
                     "correlation": "Correlation"}, title="Correlation over the whole period, by lag")
    lag_fig.update_yaxes(range=[-1, 1])
    st.plotly_chart(lag_fig, width="stretch")
    best = by_lag.loc[by_lag["correlation"].abs().idxmax()]
    st.caption(f"The strongest correlation is at a lag of {int(best['lag_weeks'])} weeks ({best['correlation']:+.2f}). "
               "A lag that fits well is a candidate for the weather lag on the Forecast page.")