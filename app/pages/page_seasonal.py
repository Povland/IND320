import streamlit as st

from utils.controls import get_global_selection, single_area_selector
from utils.data import load_filling_series, seasonal

st.title("Seasonality & Spectrum")
st.write(
    "How the filling degree of one area is built up over time. The type of area, the areas and the period "
    "are chosen in the sidebar, and the area to analyse below, among those chosen."
)

# The global selection from the sidebar. The area to analyse is chosen among the areas ticked there
selection = get_global_selection()
area_type = selection["area_type"]
if not selection["area_numbers"]:
    st.info("No areas selected. Choose one or more areas in the sidebar.")
    st.stop()

area_nr = single_area_selector("seasonality", area_type, selection["area_numbers"])
label = f"{area_type} {area_nr}"

series = load_filling_series(area_type, area_nr, selection["start"], selection["end"])
if series.empty:
    st.warning(f"No reservoir data for {label} in the chosen period.")
    st.stop()

st.caption(
    f"{label}: {len(series)} weeks, {series.index[0]:%d.%m.%Y} to {series.index[-1]:%d.%m.%Y} "
    "(the period is set in the sidebar)."
)

stl_tab, spectrogram_tab = st.tabs(["STL decomposition", "Spectrogram"])

# ---------------------------------------------------------------------------------------------
# STL: observed = trend + seasonal + residual
# ---------------------------------------------------------------------------------------------
with stl_tab:
    st.write(
        "STL splits the filling degree into a slow **trend**, a **seasonal** pattern that repeats every year, "
        "and a **residual**: what is left when the trend and the season are taken out."
    )

    # Named seasonal_window and not seasonal, so the module ind320.seasonal isn't hidden
    left, middle, right = st.columns(3)
    seasonal_window = left.number_input(
        "Seasonal smoother (years, odd)", min_value=3, max_value=51, value=13, step=2, key="stl_seasonal",
        help="How many years the seasonal value for a given week is smoothed over. "
             "Small lets the seasonal pattern change from year to year, large keeps it almost fixed.",
    )
    trend_window = middle.number_input(
        "Trend smoother (weeks, odd)", min_value=53, max_value=521, value=105, step=2, key="stl_trend",
        help="How wide the trend is smoothed. Must be longer than one year (52 weeks), "
             "otherwise the trend takes over the seasonal pattern.",
    )
    robust = right.checkbox(
        "Robust", value=True, key="stl_robust",
        help="Down-weights unusual weeks, so a single dry or wet year doesn't shift what counts as normal.",
    )

    # The function checks the parameters (odd, trend longer than a year, at least two years of data)
    # and raises ValueError with a readable message, which is shown here instead of crashing
    try:
        fig, components = seasonal.stl_decomposition(
            series, seasonal=int(seasonal_window), trend=int(trend_window), robust=robust,
            title=f"{label}: STL decomposition of the filling degree",
        )
    except ValueError as error:
        st.warning(str(error))
    else:
        st.plotly_chart(fig, width="stretch")

        # How much each part varies (standard deviation, in percentage points of filling degree)
        spread = components.std() * 100
        columns = st.columns(4)
        columns[0].metric("Observed", f"{spread['observed']:.1f} pp")
        columns[1].metric("Trend", f"{spread['trend']:.1f} pp")
        columns[2].metric("Seasonal", f"{spread['seasonal']:.1f} pp")
        columns[3].metric("Residual", f"{spread['residual']:.1f} pp")
        st.caption("Standard deviation of each part, in percentage points (pp) of the filling degree.")

# ---------------------------------------------------------------------------------------------
# Spectrogram: which frequencies are strong, and when
# ---------------------------------------------------------------------------------------------
with spectrogram_tab:
    st.write(
        "The spectrogram cuts the series into overlapping windows and shows how strong each frequency is in each "
        "window. The yearly cycle is at **1 cycle per year**."
    )

    left, right = st.columns(2)
    window_length = left.slider(
        "Window length (weeks)", min_value=52, max_value=520, value=156, step=1, key="spectrogram_window",
        help="Longer windows give sharper frequencies, but blur when things change.",
    )
    overlap_percent = right.slider(
        "Window overlap (%)", min_value=0, max_value=95, value=75, step=5, key="spectrogram_overlap",
        help="How much each window shares with the previous one. More overlap gives a smoother picture over time.",
    )
    # The overlap in weeks follows the window length, so it is always smaller than the window
    window_overlap = min(round(window_length * overlap_percent / 100), window_length - 1)

    try:
        fig, power = seasonal.spectrogram(
            series, window_length=window_length, window_overlap=window_overlap,
            title=f"{label}: spectrogram of the filling degree",
        )
    except ValueError as error:
        st.warning(f"{error}. Choose a shorter window or a longer period in the sidebar.")
    else:
        st.plotly_chart(fig, width="stretch")

        resolution = seasonal.WEEKS_PER_YEAR / window_length
        step = window_length - window_overlap
        st.caption(
            f"Window {window_length} weeks ({window_length / seasonal.WEEKS_PER_YEAR:.1f} years), "
            f"overlap {window_overlap} weeks. Frequency resolution {resolution:.2f} cycles per year, "
            f"a new window every {step} weeks, {power.shape[1]} windows in total."
        )