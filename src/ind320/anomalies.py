# Outlier and anomaly detection for the weather data.
#   - spc_outliers: high-pass filter with the Discrete Cosine Transform (DCT), then Statistical Process Control (SPC) boundaries from robust statistics (median and MAD) of what is left (the SATV)
#   - lof_anomalies: Local Outlier Factor (LOF)
# Both take a time series with a regular time index and return (plotly figure, summary, outlier table), so the notebook and the Streamlit app can use them the same way.

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from scipy.fft import dct, idct
from sklearn.neighbors import LocalOutlierFactor

# For normally distributed data, the standard deviation is 1.4826 x MAD
MAD_TO_STD = 1.4826

LINE_COLOR = "#2a78d6"
OUTLIER_COLOR = "#eb6834"
BOUNDARY_COLOR = "#555555"


# Splits a series into a slow part (season and trend) and a fast part (SATV) with the DCT.
# Coefficient k has a period of 2N/k samples, so everything slower than cutoff_days has k < 2N / (cutoff in samples).
# Those coefficients make the slow part. The rest, original minus slow part, is the SATV (a high-pass filter)
def split_dct(series, cutoff_days=30):
    values = series.interpolate().bfill().ffill().to_numpy(dtype=float)   # the DCT can't handle gaps
    n = len(values)
    step_hours = (series.index[1] - series.index[0]) / pd.Timedelta(hours=1)
    cutoff_samples = cutoff_days * 24 / step_hours
    k_cut = int(np.ceil(2 * n / cutoff_samples))

    low = dct(values, norm="ortho")
    low[k_cut:] = 0                       # keep only the slow waves
    trend = idct(low, norm="ortho")
    return trend, values - trend, k_cut


# A line plot of a series, the base of both figures below
def _series_figure(series, title, unit, name):
    fig = go.Figure()
    fig.add_scatter(x=series.index, y=series.to_numpy(dtype=float), mode="lines", name=name,
                    line=dict(color=LINE_COLOR, width=1))
    fig.update_layout(title=title, xaxis_title="Time (UTC)", yaxis_title=unit,
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    return fig


# Outliers with SPC on the SATV. The boundaries are the median of the SATV +- n_std robust standard deviations, with the slow part added back, so they follow the season in the plot. The SATV itself is not plotted
def spc_outliers(series, cutoff_days=30, n_std=3.0, title=None, unit=""):
    trend, satv, k_cut = split_dct(series, cutoff_days)

    center = np.median(satv)
    robust_std = MAD_TO_STD * np.median(np.abs(satv - center))
    upper = trend + center + n_std * robust_std
    lower = trend + center - n_std * robust_std

    values = series.to_numpy(dtype=float)
    is_outlier = (values > upper) | (values < lower)

    fig = _series_figure(series, title or f"SPC outliers (DCT cut-off {cutoff_days} days, {n_std:g} std)",
                         unit, "Hourly average")
    boundary_line = dict(color=BOUNDARY_COLOR, width=1, dash="dash")
    fig.add_scatter(x=series.index, y=upper, mode="lines", line=boundary_line, legendgroup="boundaries",
                    name=f"SPC boundaries (±{n_std:g} robust std)")
    fig.add_scatter(x=series.index, y=lower, mode="lines", line=boundary_line, legendgroup="boundaries",
                    showlegend=False)
    fig.add_scatter(x=series.index[is_outlier], y=values[is_outlier], mode="markers",
                    marker=dict(color=OUTLIER_COLOR, size=5), name=f"Outliers ({is_outlier.sum()})")

    outliers = pd.DataFrame({"value": values, "lower": lower, "upper": upper}, index=series.index)[is_outlier]
    outliers["side"] = np.where(outliers["value"] > outliers["upper"], "above", "below")

    summary = pd.Series({
        "n_values": len(series),
        "n_outliers": int(is_outlier.sum()),
        "share_outliers": is_outlier.mean(),
        "n_above": int((outliers["side"] == "above").sum()),
        "n_below": int((outliers["side"] == "below").sum()),
        "cutoff_days": cutoff_days,
        "dct_coefficients_removed": k_cut,
        "n_std": n_std,
        "satv_median": center,
        "satv_robust_std": robust_std,
    })
    return fig, summary, outliers


# Anomalies with the Local Outlier Factor. contamination is the share marked as anomalies.
# include_time=True: the features are (time, value), both standardized, so a value is compared with values close in time. include_time=False: only the value, so the rarest values of the whole period stand out
def lof_anomalies(series, contamination=0.01, n_neighbors=20, include_time=True, title=None, unit=""):
    values = series.interpolate().bfill().ffill().to_numpy(dtype=float)

    def standardize(x):
        return (x - x.mean()) / x.std()

    if include_time:
        days = ((series.index - series.index[0]) / pd.Timedelta(days=1)).to_numpy(dtype=float)
        features = np.column_stack([standardize(days), standardize(values)])
    else:
        features = standardize(values).reshape(-1, 1)

    lof = LocalOutlierFactor(n_neighbors=n_neighbors, contamination=contamination)
    is_outlier = lof.fit_predict(features) == -1
    scores = -lof.negative_outlier_factor_        # higher = more anomalous

    fig = _series_figure(series, title or f"LOF anomalies ({contamination:.1%} of the values, {n_neighbors} neighbours)",
                         unit, "Hourly average")
    fig.add_scatter(x=series.index[is_outlier], y=values[is_outlier], mode="markers",
                    marker=dict(color=OUTLIER_COLOR, size=5), name=f"LOF anomalies ({is_outlier.sum()})")

    outliers = pd.DataFrame({"value": values, "lof_score": scores}, index=series.index)[is_outlier]
    outliers = outliers.sort_values("lof_score", ascending=False)

    summary = pd.Series({
        "n_values": len(series),
        "n_outliers": int(is_outlier.sum()),
        "share_outliers": is_outlier.mean(),
        "contamination": contamination,
        "n_neighbors": n_neighbors,
        "include_time": include_time,
        "min_outlier_value": outliers["value"].min(),
        "max_outlier_value": outliers["value"].max(),
        "max_lof_score": outliers["lof_score"].max(),
    })
    return fig, summary, outliers