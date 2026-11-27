# Sliding window correlation between a weather property and a reservoir variable, both weekly (weeks ending Sunday).
#   - sliding_correlation: the correlation in a window that slides one week at a time, with the weather lagged
#   - lag_correlations: the correlation over the whole period for each lag, to see which lag fits best
#   - correlation_figure: the two series and the sliding correlation, in three panels with a shared time axis

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from ind320.maps import AREA_COLOR, CELL_COLOR

WEEK = "W-SUN"


# The two series on the same weeks, with the weather moved lag weeks forward: with lag 3, each week's reservoir value
# is paired with the weather three weeks earlier (rain and snowmelt take time to reach the reservoirs).
# Only weeks where both have a value are kept
def _aligned(weather, reservoir, lag=0):
    weather = weather.asfreq(WEEK).shift(lag)
    reservoir = reservoir.asfreq(WEEK)
    return pd.concat({"weather": weather, "reservoir": reservoir}, axis=1).dropna()


# The Pearson correlation in a window of `window` weeks, sliding one week at a time. Each value is the correlation
# of the window that ends that week. The first window - 1 weeks have no value (the window isn't full yet)
def sliding_correlation(weather, reservoir, window=13, lag=0):
    aligned = _aligned(weather, reservoir, lag)
    if len(aligned) < window:
        raise ValueError(f"Only {len(aligned)} weeks with both series, but the window is {window} weeks.")
    correlation = aligned["weather"].rolling(window, min_periods=window).corr(aligned["reservoir"])
    return correlation.rename("correlation"), aligned


# The correlation over the whole period for each lag from 0 to max_lag weeks
def lag_correlations(weather, reservoir, max_lag=12):
    values = {}
    for lag in range(max_lag + 1):
        aligned = _aligned(weather, reservoir, lag)
        values[lag] = aligned["weather"].corr(aligned["reservoir"]) if len(aligned) > 2 else float("nan")
    return pd.Series(values, name="correlation").rename_axis("lag_weeks")


# Three panels with a shared time axis: the weather (already lagged, so it lines up with what it is compared with),
# the reservoir variable, and the sliding correlation between -1 and 1 with a line at 0
def correlation_figure(correlation, aligned, weather_label, reservoir_label, window, lag, title=None, height=700):
    lag_text = f", {lag} weeks earlier" if lag else ""
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.06,
                        subplot_titles=[f"{weather_label}{lag_text}", reservoir_label,
                                        f"Correlation in a {window}-week sliding window"])
    fig.add_scatter(x=aligned.index, y=aligned["weather"], name=weather_label, line=dict(color=CELL_COLOR), row=1, col=1)
    fig.add_scatter(x=aligned.index, y=aligned["reservoir"], name=reservoir_label, line=dict(color=AREA_COLOR), row=2, col=1)
    fig.add_scatter(x=correlation.index, y=correlation, name="Correlation", line=dict(color="#2e9e6a", width=2),
                    row=3, col=1)
    fig.add_hline(y=0, line=dict(color="gray", dash="dot"), row=3, col=1)
    fig.update_yaxes(range=[-1, 1], row=3, col=1)
    fig.update_layout(title=title, height=height, showlegend=False, hovermode="x unified", margin=dict(t=80))
    return fig