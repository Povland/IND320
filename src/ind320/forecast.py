# Forecasting the weekly filling degree of one area with SNARIMAX from River (online SARIMAX).
#   - forecast_filling: trains on a chosen part of the history and forecasts the coming weeks (dynamic forecast:
#     each forecast is fed back as a lag for the next week), optionally with exogenous variables and an interval
#   - forecast_figure: plotly figure of the result, animated week by week
#
# Weekly resolution: NVE publishes one value per week, so this is the natural resolution, and with m = 52 the
# seasonal part looks one year back. A year is 52.18 weeks on average, so the season drifts by about a day per year,
# which is small compared with the week resolution.
#
# The exogenous variables (weather, currency) must also be known for the weeks that are forecast. When they are
# (a backtest, e.g. training to June 2025 and forecasting the rest of 2025), the observed values are used.
# When they are not (beyond the data), the average for that week of the year over the training period is used.
# The result says which was used

import time

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from river import linear_model, optim, preprocessing, time_series

from ind320.maps import AREA_COLOR, CELL_COLOR

WEEK = "W-SUN"

# The default settings. Placeholders until the tests in Oblig4 pick the best ones
DEFAULTS = dict(p=2, d=0, q=0, m=52, sp=0, sd=1, sq=0, learning_rate=0.01)


# A SNARIMAX model. The regressor is River's default (StandardScaler + LinearRegression), with the learning rate
# as a parameter. alpha=None trains on the squared error (the forecast itself), alpha=0.05 or 0.95 trains on the
# quantile loss, which gives the lower or upper edge of an interval (the bonus task)
def make_model(p, d, q, m, sp, sd, sq, learning_rate=0.01, alpha=None):
    loss = optim.losses.Squared() if alpha is None else optim.losses.Quantile(alpha)
    regressor = preprocessing.StandardScaler() | linear_model.LinearRegression(
        optimizer=optim.SGD(learning_rate), intercept_lr=learning_rate, loss=loss,
    )
    return time_series.SNARIMAX(p=p, d=d, q=q, m=m, sp=sp, sd=sd, sq=sq, regressor=regressor)


# Runs through the training weeks once, in order (online learning). With record=True, the model's forecast for
# each week is stored before it learns that week (the one-step-ahead fit). None until the model has seen enough
# weeks to difference the series (d + m * sd weeks)
def _train(model, values, xs, record=False):
    fitted = []
    for value, x in zip(values, xs):
        if record:
            ready = len(model.y_hist) >= model.differencer.n_required_past_values
            fitted.append(model.forecast(1, xs=[x])[0] if ready else np.nan)
        model.learn_one(value, x)
    return fitted


# The exogenous values for the weeks to forecast: observed if stored, otherwise the training period's average for
# the same week of the year (or the overall average, if that week of the year isn't in the training period)
def _future_exog(exog, train_x, future_weeks):
    weeks_of_year = train_x.index.isocalendar().week.to_numpy()
    seasonal_average = train_x.groupby(weeks_of_year).mean()
    observed = exog.reindex(future_weeks)

    xs, sources = [], []
    for week, row in observed.iterrows():
        if row.notna().all():
            xs.append(row.to_dict())
            sources.append("observed")
        else:
            week_of_year = week.isocalendar().week
            values = seasonal_average.loc[week_of_year] if week_of_year in seasonal_average.index else train_x.mean()
            xs.append(values.to_dict())
            sources.append("seasonal average")
    return xs, sources


# Trains SNARIMAX on the filling degree of one area and forecasts horizon weeks after the training period.
#   filling        weekly filling degree (from seasonal.filling_series), index: Sundays
#   exog           None, or a table of exogenous variables per week (same Sundays), one column per variable.
#                  Which columns are given is the choice of data sources
#   train_end      the last week to train on (default: the last week with all data). The forecast starts after it
#   history_weeks  how many weeks to train on, back from train_end (default: all there is)
#   horizon        how many weeks to forecast
#   exog_lag       weeks the exogenous variables are moved back, e.g. 2: the weather two weeks earlier
#   p, d, q        the non-seasonal AR order, differencing and MA order
#   m, sp, sd, sq  the season length (52 weeks) and the seasonal AR order, differencing and MA order
#   intervals      also trains two quantile models for an interval covering 1 - interval_alpha (e.g. 90 %)
# Raises ValueError with a readable message if the settings or the data don't work together.
# Returns (result, info): result has one row per week (training + forecast) with observed, fitted, forecast,
# lower, upper and part ("train" or "forecast"), and info has the period, the errors and the run time
def forecast_filling(filling, exog=None, train_end=None, history_weeks=None, horizon=26, exog_lag=0,
                     p=DEFAULTS["p"], d=DEFAULTS["d"], q=DEFAULTS["q"], m=DEFAULTS["m"],
                     sp=DEFAULTS["sp"], sd=DEFAULTS["sd"], sq=DEFAULTS["sq"],
                     learning_rate=DEFAULTS["learning_rate"], intervals=False, interval_alpha=0.1):
    started = time.perf_counter()
    y = filling.dropna().asfreq(WEEK).interpolate(limit_direction="both")
    if exog is not None and (exog.empty or exog.shape[1] == 0):
        exog = None

    # The weeks where every exogenous variable has a value (after moving them by exog_lag). Gaps of up to
    # two weeks inside the data are filled in, longer ones are not
    if exog is not None:
        exog = exog.asfreq(WEEK)
        if exog_lag:
            exog = exog.shift(exog_lag)
        exog = exog.interpolate(limit=2, limit_area="inside")
        complete = exog.dropna().index
        if complete.empty:
            raise ValueError("The exogenous variables have no week where all of them have a value.")
        first, last = complete[0], complete[-1]
    else:
        first, last = y.index[0], y.index[-1]

    # The training period: up to train_end, history_weeks back, within both the filling and the exogenous data
    end = min(pd.Timestamp(train_end), y.index[-1]) if train_end is not None else min(y.index[-1], last)
    end = y.index[y.index <= end][-1]
    if end > last:
        raise ValueError(f"The exogenous variables end on {last:%d.%m.%Y}, so the training can't end after that.")
    start = max(y.index[0], first)
    if history_weeks:
        start = max(start, end - pd.Timedelta(weeks=history_weeks - 1))

    train_y = y[start:end]
    warm_up = d + m * sd + max(p, m * sp, q, m * sq)
    if len(train_y) < warm_up + 10:
        raise ValueError(f"Too little training data: {len(train_y)} weeks from {start:%d.%m.%Y} to {end:%d.%m.%Y}, "
                         f"but these settings need at least {warm_up + 10} (about {(warm_up + 10) / 52:.1f} years).")

    future_weeks = pd.date_range(end + pd.Timedelta(weeks=1), periods=horizon, freq=WEEK)
    if exog is not None:
        train_x = exog.reindex(train_y.index)
        if train_x.isna().any().any():
            gaps = train_x.index[train_x.isna().any(axis=1)]
            raise ValueError(f"The exogenous variables are missing for {len(gaps)} weeks in the training period, "
                             f"the first on {gaps[0]:%d.%m.%Y}.")
        xs = train_x.to_dict("records")
        future_xs, sources = _future_exog(exog, train_x, future_weeks)
    else:
        xs, future_xs, sources = [None] * len(train_y), None, ["none"] * horizon

    # The forecast: train once through the weeks, then forecast all the coming weeks in one go (dynamic)
    settings = dict(p=p, d=d, q=q, m=m, sp=sp, sd=sd, sq=sq, learning_rate=learning_rate)
    model = make_model(**settings)
    fitted = _train(model, train_y, xs, record=True)
    forecast = np.clip(model.forecast(horizon, xs=future_xs), 0, 1)

    result = pd.DataFrame(index=train_y.index.append(future_weeks))
    result.index.name = "date_id"
    result["observed"] = y.reindex(result.index)
    result["fitted"] = pd.Series(fitted, index=train_y.index)
    result["forecast"] = pd.Series(forecast, index=future_weeks)
    result["part"] = np.where(result.index <= end, "train", "forecast")

    # The interval: the same model, trained on the quantile loss for the lower and the upper edge.
    # It is approximate: each quantile model also forecasts recursively, from its own earlier forecasts
    if intervals:
        edges = []
        for alpha in (interval_alpha / 2, 1 - interval_alpha / 2):
            edge_model = make_model(**settings, alpha=alpha)
            _train(edge_model, train_y, xs)
            edges.append(np.clip(edge_model.forecast(horizon, xs=future_xs), 0, 1))
        result["lower"] = pd.Series(np.minimum(*edges), index=future_weeks)
        result["upper"] = pd.Series(np.maximum(*edges), index=future_weeks)

    # The errors, in filling degree (0.01 = 1 percentage point). The fit skips the warm-up weeks.
    # The forecast error needs the observed values after train_end, so it is only there in a backtest.
    # Seasonal naive (the same week last year) is the baseline the model should beat
    fit_part = result.loc[result["part"] == "train"].iloc[warm_up:]
    future_part = result.loc[result["part"] == "forecast"]
    actual = future_part["observed"]
    naive = y.shift(52).reindex(future_weeks)
    has_actual = actual.notna()

    info = {
        "train_start": start, "train_end": end, "train_weeks": len(train_y), "horizon": horizon,
        "exog_columns": [] if exog is None else list(exog.columns), "exog_lag": exog_lag,
        "exog_source": pd.Series(sources).value_counts().to_dict(),
        "mae_fit": (fit_part["fitted"] - fit_part["observed"]).abs().mean(),
        "mae_forecast": (future_part["forecast"] - actual)[has_actual].abs().mean() if has_actual.any() else np.nan,
        "mae_naive": (naive - actual)[has_actual].abs().mean() if has_actual.any() else np.nan,
        "weeks_with_actual": int(has_actual.sum()),
        "seconds": time.perf_counter() - started,
        "interval": 1 - interval_alpha if intervals else None,
        **settings,
    }
    return result, info


# The result as a plotly figure: the observed filling degree in the training period, the forecast (orange),
# the observed values after the training period if there are any (grey, dotted), the one-step fit (hidden, can be
# turned on in the legend) and the interval if computed.
# The whole forecast is drawn from the start, so the figure is complete also in the HTML export (which can't play).
# With animate=True, Play draws the forecast again week by week from the first week. Only the forecast traces
# change in each frame, so it plays smoothly.
# The x axis starts three years before the forecast, so the forecast isn't squeezed (zoom out to see all)
def forecast_figure(result, info, title=None, animate=True, height=550, frame_ms=120):
    train = result[result["part"] == "train"]
    future = result[result["part"] == "forecast"]
    last_week, last_value = train.index[-1], train["observed"].iloc[-1]

    # Every forecast trace starts in the last observed week, so the lines are connected
    x = [last_week, *future.index]
    lines = {"forecast": [last_value, *future["forecast"]]}
    has_interval = "upper" in future and future["upper"].notna().any()
    if has_interval:
        lines["upper"] = [last_value, *future["upper"]]
        lines["lower"] = [last_value, *future["lower"]]

    fig = go.Figure()
    fig.add_scatter(x=train.index, y=train["observed"], name="Observed", line=dict(color=AREA_COLOR))
    fig.add_scatter(x=train.index, y=train["fitted"], name="One-step fit", visible="legendonly",
                    line=dict(color=AREA_COLOR, width=1, dash="dot"))
    actual = future["observed"].dropna()
    if not actual.empty:
        fig.add_scatter(x=[last_week, *actual.index], y=[last_value, *actual], name="Observed after training",
                        line=dict(color="gray", dash="dot"))

    # The traces that are animated, in this order: the interval's upper and lower edge (filled between), the forecast
    animated = []
    if has_interval:
        animated.append(len(fig.data))
        fig.add_scatter(x=x, y=lines["upper"], mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip")
        animated.append(len(fig.data))
        fig.add_scatter(x=x, y=lines["lower"], mode="lines", line=dict(width=0), fill="tonexty",
                        fillcolor="rgba(235, 104, 52, 0.2)", name=f"{info['interval']:.0%} interval")
    animated.append(len(fig.data))
    fig.add_scatter(x=x, y=lines["forecast"], name="Forecast", line=dict(color=CELL_COLOR, width=3))

    # The legend to the right of the plot, as a vertical list, so it doesn't overlap the title or the controls
    view_start = max(train.index[0], last_week - pd.Timedelta(weeks=156))
    fig.update_layout(
        title=dict(text=title, x=0, xanchor="left"), height=height, hovermode="x unified",
        xaxis=dict(title="Week", range=[view_start, x[-1]]),
        yaxis=dict(title="Filling degree", range=[0, 1.05], tickformat=".0%"),
        legend=dict(x=1.02, y=1, xanchor="left", yanchor="top"),
        margin=dict(t=60, r=10),
    )

    if animate:
        # Frame k shows the first k forecast weeks. Each frame only holds the new data of the animated traces.
        # The last frame is the whole forecast, the same as the figure shows before Play is pressed
        names = ["upper", "lower", "forecast"] if has_interval else ["forecast"]
        fig.frames = [
            go.Frame(name=str(k), traces=animated,
                     data=[go.Scatter(x=x[:k], y=lines[name][:k]) for name in names])
            for k in range(1, len(x) + 1)
        ]
        # Play starts from the first frame each time (not fromcurrent), so it always replays the whole forecast
        play = dict(frame=dict(duration=frame_ms, redraw=False), fromcurrent=False, transition=dict(duration=0))
        pause = dict(frame=dict(duration=0, redraw=False), mode="immediate", transition=dict(duration=0))
        fig.update_layout(
            updatemenus=[dict(type="buttons", direction="left", x=0, y=-0.15, xanchor="left", yanchor="top",
                              buttons=[dict(label="Play forecast", method="animate", args=[None, play]),
                                       dict(label="Pause", method="animate", args=[[None], pause])])],
            margin=dict(t=60, r=10, b=90),
        )
    return fig