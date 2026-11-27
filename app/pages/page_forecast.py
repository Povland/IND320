import streamlit as st

from utils.controls import area_type_selector, single_area_selector
from utils.data import run_forecast, available_area_numbers, available_dates, forecast, load_filling_series, load_weekly_weather

st.title("Forecast")
st.write(
    "Forecast of the weekly filling degree of one area with SNARIMAX (online SARIMAX from the River library). "
    "The model learns from the chosen history week by week, then forecasts the coming weeks dynamically: "
    "each forecast is used as input for the next week. Weather can be added as exogenous variables."
)

# The weather variables that can be used, with how they are summed up per week
WEATHER_VARIABLES = {
    "temperature_2m": "Temperature (weekly mean, °C)",
    "precipitation": "Precipitation (weekly sum, mm)",
    "rain": "Rain (weekly sum, mm)",
    "snowfall": "Snowfall (weekly sum, cm)",
    "et0_fao_evapotranspiration": "Evaporation (weekly sum, mm)",
}

# ---------------------------------------------------------------------------------------------
# The area: local choices, starting from the sidebar's choice on the other pages
# ---------------------------------------------------------------------------------------------
left, right = st.columns(2)
with left:
    area_type = area_type_selector("forecast", memory_key="forecast_area_type_memory")
with right:
    area_nr = single_area_selector("forecast", area_type, available_area_numbers(area_type))
label = f"{area_type} {area_nr}"

# Without NVE's data there is nothing to forecast, so the page stops with a message (the rest of the app still works)
weeks = available_dates()
if not weeks:
    st.warning("The reservoir data could not be fetched from NVE right now, so there is nothing to forecast. "
               "Try again in a moment, or see Data status.")
    st.page_link("pages/page_data_status.py", label="See Data status")
    st.stop()

# ---------------------------------------------------------------------------------------------
# Training period and horizon. The last week of training is shared with the map on Home
# (st.session_state["selected_week"]), so both show the same point in time
# ---------------------------------------------------------------------------------------------
st.subheader("Training period and horizon")

# Starts on the shared week if there is one, otherwise on the latest week. Set before the slider is drawn
# (not with value=), to avoid Streamlit's warning about a widget getting its value twice
if st.session_state.get("forecast_train_end") not in weeks:
    shared_week = st.session_state.get("selected_week")
    st.session_state["forecast_train_end"] = shared_week if shared_week in weeks else weeks[-1]


def share_week():
    st.session_state["selected_week"] = st.session_state["forecast_train_end"]


train_end = st.select_slider(
    "Last week of training", options=weeks, key="forecast_train_end", on_change=share_week,
    format_func=lambda date: f"{date:%d.%m.%Y}",
    help="The forecast starts the week after. Choose an earlier week to compare the forecast with what really "
         "happened (a backtest). Shared with the map on Home.",
)
left, right = st.columns(2)
history_years = left.slider(
    "Length of history (years)", min_value=2, max_value=30, value=10, key="forecast_history_years",
    help="How many years back from the last week of training the model learns from. "
         "10 years gave the lowest error in the tests in the notebook.",
)
horizon = right.slider("Horizon (weeks)", min_value=4, max_value=52, value=26, key="forecast_horizon",
                       help="How many weeks after the training period to forecast.")

# ---------------------------------------------------------------------------------------------
# Exogenous variables: weather from MongoDB, only for EL and VASS (no weather polygon for all of Norway)
# ---------------------------------------------------------------------------------------------
st.subheader("Exogenous variables")
exog, exog_lag = None, 0

if area_type == "NO":
    st.caption("There is no weather for all of Norway, so the forecast for NO uses the filling degree only.")
else:
    left, right = st.columns([3, 1])
    chosen = left.multiselect(
        "Weather variables", options=list(WEATHER_VARIABLES), format_func=WEATHER_VARIABLES.get,
        key="forecast_exog", placeholder="None (filling degree only)",
        help="Weekly weather for the area, used as extra inputs to the model. The training can then only use "
             "the weeks where the weather is stored.",
    )
    exog_lag = right.slider("Weather lag (weeks)", min_value=0, max_value=8, value=0, key="forecast_exog_lag",
                            help="Uses the weather this many weeks earlier, e.g. 2: the weather two weeks before.")

    if chosen and not st.session_state["mongo_status"]["connected"]:
        st.warning("Not connected to MongoDB, so the weather can't be read. The forecast uses the filling degree only.")
    elif chosen:
        weekly = load_weekly_weather(area_type, area_nr)
        if weekly.empty:
            st.warning(f"No complete year of weather is stored for {label}. The forecast uses the filling degree only.")
            st.page_link("pages/page_data_status.py", label="Download weather on Data status")
        else:
            exog = weekly[chosen]
            st.caption(f"Weather stored for {label} from {weekly.index[0]:%d.%m.%Y} to {weekly.index[-1]:%d.%m.%Y}. "
                       "The training is limited to this period, so the length of history may be shorter than chosen.")

# ---------------------------------------------------------------------------------------------
# Model settings. The defaults are the best setting from the tests in the notebook
# ---------------------------------------------------------------------------------------------
defaults = forecast.DEFAULTS
with st.expander("Model settings (SNARIMAX)"):
    st.caption("The defaults are the best setting from the tests in the notebook: AR(2) with seasonal differencing "
               "and learning rate 0.01. The season length is fixed at m = 52 weeks (one year of weekly data).")
    columns = st.columns(3)
    p = columns[0].number_input("p: AR order", min_value=0, max_value=8, value=defaults["p"], key="forecast_p",
                                help="How many of the previous weeks are used as inputs.")
    d = columns[1].number_input("d: differencing", min_value=0, max_value=2, value=defaults["d"], key="forecast_d",
                                help="1 makes the model learn the change from the week before.")
    q = columns[2].number_input("q: MA order", min_value=0, max_value=4, value=defaults["q"], key="forecast_q",
                                help="How many of the previous errors are used as inputs.")
    columns = st.columns(3)
    sp = columns[0].number_input("sp: seasonal AR order", min_value=0, max_value=2, value=defaults["sp"],
                                 key="forecast_sp", help="How many of the same weeks in earlier years are used.")
    sd = columns[1].number_input("sd: seasonal differencing", min_value=0, max_value=1, value=defaults["sd"],
                                 key="forecast_sd", help="1 makes the model learn the change from the same week last year.")
    sq = columns[2].number_input("sq: seasonal MA order", min_value=0, max_value=2, value=defaults["sq"],
                                 key="forecast_sq", help="How many of the errors in the same weeks of earlier years are used.")
    learning_rate = st.select_slider("Learning rate", options=[0.001, 0.005, 0.01, 0.02, 0.05, 0.1],
                                     value=defaults["learning_rate"], key="forecast_learning_rate",
                                     help="How big a step the model takes each week. Too big makes it unstable.")

left, right = st.columns(2)
intervals = left.toggle("Show interval", value=True, key="forecast_intervals",
                        help="Two extra models trained on the quantile loss give the lower and upper edge.")
level = right.select_slider("Interval", options=[0.8, 0.9, 0.95], value=0.9, key="forecast_level",
                            format_func=lambda value: f"{value:.0%}", disabled=not intervals)

# ---------------------------------------------------------------------------------------------
# The forecast, cached per set of settings (run_forecast in utils/data.py), so going back to a setting is instant.
# Settings that don't fit the data (too short history, weather missing) give a readable message instead of a crash
# ---------------------------------------------------------------------------------------------
try:
    result, info = run_forecast(
        filling, exog=exog, train_end=train_end, history_weeks=history_years * 52, horizon=horizon,
        exog_lag=exog_lag, p=int(p), d=int(d), q=int(q), m=52, sp=int(sp), sd=int(sd), sq=int(sq),
        learning_rate=learning_rate, intervals=intervals, interval_alpha=round(1 - level, 2),
    )
except ValueError as error:
    st.warning(str(error))
    st.stop()

exog_text = ", ".join(WEATHER_VARIABLES[c].split(" (")[0].lower() for c in info["exog_columns"]) or "no weather"
fig = forecast.forecast_figure(result, info, title=f"{label}: forecast of the filling degree ({exog_text})")
st.plotly_chart(fig, width="stretch")

# The numbers: training period, errors (in percentage points of filling degree) and run time.
# The forecast error is only known in a backtest, where the forecast weeks have been observed
columns = st.columns(4)
columns[0].metric("Training", f"{info['train_weeks']} weeks",
                  help=f"{info['train_start']:%d.%m.%Y} to {info['train_end']:%d.%m.%Y}")
columns[1].metric("Fit error (one week ahead)", f"{info['mae_fit'] * 100:.1f} pp",
                  help="Mean absolute error of the model's forecast for each training week, one week ahead.")
if info["weeks_with_actual"]:
    columns[2].metric(
        "Forecast error", f"{info['mae_forecast'] * 100:.1f} pp",
        delta=f"{(info['mae_forecast'] - info['mae_naive']) * 100:+.1f} pp vs same week last year",
        delta_color="inverse",
        help=f"Mean absolute error over the {info['weeks_with_actual']} forecast weeks that have been observed. "
             "Compared with simply using the same week last year.",
    )
else:
    columns[2].metric("Forecast error", "Not known yet",
                      help="The forecast weeks haven't happened yet. Choose an earlier last week of training to compare.")
    columns[3].metric("Run time", f"{info['seconds']:.2f} s",
                      help="The time it took to train and forecast. Settings already shown are read from the cache.")

# The weather for weeks beyond the stored data is unknown, so the average for that week of the year is used
if info["exog_source"].get("seasonal average"):
    st.caption(f"The weather for {info['exog_source']['seasonal average']} of the forecast weeks is not stored, so "
               "the average for the same week of the year in the training period is used instead.")

with st.expander("Show the forecast as a table"):
    table = result.loc[result["part"] == "forecast"].drop(columns=["part", "fitted"])
    st.dataframe(table.style.format("{:.1%}", na_rep=""), width="stretch")