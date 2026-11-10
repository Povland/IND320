# Seasonal analysis of the reservoir data (weekly filling degree from NVE's Magasinstatistikk).
#   - filling_series: one area's filling degree as a regular weekly series
#   - stl_decomposition: Seasonal-Trend decomposition using LOESS (STL): observed = trend + seasonal + residual
#   - spectrogram: how strong each frequency is over time
# The functions return plotly figures (and the numbers behind them), so the notebook and the app can use them.

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy.signal import spectrogram as scipy_spectrogram
from statsmodels.tsa.seasonal import STL

# The data is weekly. A year is 52.18 weeks on average, and STL needs a whole number of weeks per season
WEEKS_PER_YEAR = 365.25 / 7
PERIOD = 52

LINE_COLOR = "#2a78d6"


# One area's filling degree as a regular weekly series (Sundays, the end of each ISO week).
# Missing weeks are filled by linear interpolation, since STL and the spectrogram need evenly spaced data
def filling_series(reservoirs, area_type, area_nr, column="filling_degree"):
    data = reservoirs[(reservoirs["area_type"] == area_type) & (reservoirs["area_nr"] == area_nr)]
    if data.empty:
        raise ValueError(f"No reservoir data for {area_type} {area_nr}")

    series = data[column].sort_index()
    series = series[~series.index.duplicated()].asfreq("W-SUN").interpolate()
    series.name = f"{area_type} {area_nr}"
    return series


# STL decomposition of a weekly series, plotted as four panels: observed, trend, seasonal, residual.
# seasonal (in years) and trend (in weeks) must be odd, and the trend must be longer than the period.
# Returns the figure and the four components as a table
def stl_decomposition(series, seasonal=13, trend=105, robust=True, period=PERIOD, title=None):
    if seasonal < 3 or seasonal % 2 == 0:
        raise ValueError("seasonal must be an odd number of at least 3")
    if trend <= period or trend % 2 == 0:
        raise ValueError(f"trend must be an odd number larger than the period ({period})")
    if len(series) < 2 * period:
        raise ValueError(f"STL needs at least two full periods ({2 * period} weeks), got {len(series)}")

    result = STL(series, period=period, seasonal=seasonal, trend=trend, robust=robust).fit()
    components = pd.DataFrame({
        "observed": result.observed,
        "trend": result.trend,
        "seasonal": result.seasonal,
        "residual": result.resid,
    }, index=series.index)

    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.05,
                        subplot_titles=["Observed", "Trend", "Seasonal", "Residual"])
    for row, column in enumerate(components.columns, start=1):
        fig.add_scatter(x=components.index, y=components[column], mode="lines", name=column,
                        line=dict(color=LINE_COLOR, width=1), row=row, col=1)
    fig.update_layout(title=title or f"STL decomposition (seasonal = {seasonal}, trend = {trend}, robust = {robust})",
                      height=800, showlegend=False)
    return fig, components


# Spectrogram of a series: the series is cut into windows of window_length samples that overlap by
# window_overlap samples, and the power at each frequency is found for each window (Hann window,
# with each window's mean removed so the level doesn't dominate).
# Frequency is in cycles per year, shown up to max_frequency (None shows all). Power is shown in dB.
# Returns the figure and the power as a table (one row per frequency, one column per window)
def spectrogram(series, window_length=156, window_overlap=117, max_frequency=6, title=None,
                samples_per_year=WEEKS_PER_YEAR):
    if window_overlap >= window_length:
        raise ValueError("window_overlap must be smaller than window_length")
    if window_length > len(series):
        raise ValueError(f"window_length ({window_length}) is longer than the series ({len(series)})")

    values = series.interpolate().to_numpy(dtype=float)
    frequencies, times, power = scipy_spectrogram(
        values, fs=samples_per_year, window="hann", nperseg=window_length,
        noverlap=window_overlap, detrend="constant", scaling="density",
    )

    # times are the window centres in years from the start, turned into dates
    centres = series.index[0] + pd.to_timedelta(times * 365.25, unit="D")
    keep = frequencies <= max_frequency if max_frequency is not None else np.ones(len(frequencies), dtype=bool)
    table = pd.DataFrame(power[keep], index=frequencies[keep], columns=centres)
    table.index.name = "cycles_per_year"

    fig = go.Figure(go.Heatmap(
        x=centres, y=frequencies[keep], z=10 * np.log10(power[keep] + 1e-12),
        colorscale="Viridis", colorbar=dict(title="Power (dB)"),
    ))
    fig.update_layout(title=title or f"Spectrogram (window {window_length} weeks, overlap {window_overlap} weeks)",
                      xaxis_title="Time (window centre)", yaxis_title="Frequency (cycles per year)")
    return fig, table