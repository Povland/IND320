import calendar

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import calendar
import textwrap

import pandas as pd

# Same colours and names for the directions as in the notebook
DIRECTION_COLORS = {"Out of Norway": "#2a78d6", "Into Norway": "#eb6834"}
DIRECTION_LABELS = {"out": "Out of Norway", "in": "Into Norway"}

# The country is the first part of the foreign area code (SE_3 -> SE, DE_LU -> DE)
COUNTRIES = {"SE": "Sweden", "DK": "Denmark", "DE": "Germany", "NL": "Netherlands", "GB": "Great Britain", "FI": "Finland"}

# The three ways of choosing connections, shown as pills at the top
MODES = ["All connections", "Countries", "Connections"]

ALL_MONTHS = 0   # the "All" pill among the months (real months are 1-12)

VIEWS = ["Aggregated", "Separate", "Both"]
PIE_VIEWS = ["Aggregated", "Per connection"]   # Separate and Both would look the same in a pie, so it has its own two
DIRECTIONS = ["Both directions", "Out of Norway", "Into Norway"]
LAYOUTS = ["Same plot", "One plot per connection"]

AXIS_LABELS = {"time": "Time (Norwegian time)", "mwh": "MWh per hour", "direction": "Direction"}


# ---------------------------------------------------------------------------------------------
# Names
# ---------------------------------------------------------------------------------------------

def norwegian_area(connection):          # "NO_4-SE_1" -> "NO_4"
    return connection.split("-")[0]


def foreign_area(connection):            # "NO_4-SE_1" -> "SE_1"
    return connection.split("-")[1]


def country(connection):                 # "NO_4-SE_1" -> "Sweden"
    code = foreign_area(connection).split("_")[0]
    return COUNTRIES.get(code, code)


# "NO 4 – Sweden (SE 1)". The area is only added for countries split into numbered areas (Sweden, Denmark)
def connection_label(connection):
    area = foreign_area(connection)
    foreign = f"{country(connection)} ({area.replace('_', ' ')})" if area[-1].isdigit() else country(connection)
    return f"{norwegian_area(connection).replace('_', ' ')} – {foreign}"


# Area code as shown in short labels: SE_1 -> "SE 1", DE_LU -> "DE-LU"
def _area_code(area):
    return area.replace("_", " ") if area[-1].isdigit() else area.replace("_", "-")


# "NO 4–SE 1". Used in titles, where the full names would get too long
def short_label(connection):
    return f"{_area_code(norwegian_area(connection))}–{_area_code(foreign_area(connection))}"


# Sorted by connection number: the Norwegian area first, then the foreign area
def sort_connections(connections):
    return sorted(connections, key=lambda c: (norwegian_area(c), foreign_area(c)))


# ---------------------------------------------------------------------------------------------
# Choosing connections
# ---------------------------------------------------------------------------------------------

# Pills for how to choose (all, by country, or single connections), and the choice itself under them.
# Everything is ticked from the start in all three.
# Returns the chosen connections, sorted by connection number, and a text describing them for the titles
def connection_chooser(connections):
    connections = sort_connections(connections)
    mode = st.pills("Choose", options=MODES, selection_mode="single", default=MODES[0], key="connection_mode")

    if mode is None:   # the pill was clicked again, so nothing is chosen
        return [], ""

    if mode == "All connections":
        return connections, "All connections"

    if mode == "Connections":
        # One checkbox per connection, one under the other, sorted by connection number
        keys = {c: f"pick_{c}" for c in connections}
        for key in keys.values():
            st.session_state.setdefault(key, True)

        ticked = [c for c, key in keys.items() if st.session_state[key]]
        summary = "All" if len(ticked) == len(connections) else f"{len(ticked)} of {len(connections)}"
        with st.popover(f"Connections: {summary}"):
            for connection, key in keys.items():
                st.checkbox(connection_label(connection), key=key)

        chosen = [c for c, key in keys.items() if st.session_state[key]]
        if len(chosen) == len(connections):
            text = "All connections"
        elif len(chosen) <= 3:
            text = ", ".join(connection_label(c) for c in chosen)
        else:
            text = f"{len(chosen)} of {len(connections)} connections"
        return chosen, text

    return _country_chooser(connections)


# One checkbox per country (alphabetical). Ticking a country includes all its connections.
# Countries with more than one connection get a small dropdown on the right to untick some of them,
# greyed out until the country is ticked
def _country_chooser(connections):
    chosen, parts = [], []

    for name in sorted({country(c) for c in connections}):
        members = [c for c in connections if country(c) == name]
        tick_column, dropdown_column = st.columns([2, 1], vertical_alignment="center")
        st.session_state.setdefault(f"country_{name}", True)   # every country is ticked from the start
        ticked = tick_column.checkbox(name, key=f"country_{name}")

        included = members
        if len(members) > 1:
            keys = {c: f"country_{name}_{c}" for c in members}
            for key in keys.values():
                st.session_state.setdefault(key, True)

            current = [c for c, key in keys.items() if st.session_state[key]]
            summary = f"All {len(members)}" if len(current) == len(members) else f"{len(current)} of {len(members)}"
            with dropdown_column.popover(summary, disabled=not ticked):
                for connection, key in keys.items():
                    st.checkbox(connection_label(connection), key=key)
            included = [c for c, key in keys.items() if st.session_state[key]]

        if ticked and included:
            chosen += included
            # The whole country by name, or the country with the connections that are included
            parts.append(name if included == members else f"{name} ({', '.join(short_label(c) for c in included)})")

    chosen = [c for c in connections if c in chosen]
    return chosen, ", ".join(parts)


# ---------------------------------------------------------------------------------------------
# Choosing years and months
# ---------------------------------------------------------------------------------------------

# Popover with one checkbox per year, all ticked from the start. Untick the others to see just one year
def year_selector(years):
    keys = {year: f"year_{year}" for year in years}
    for key in keys.values():
        st.session_state.setdefault(key, True)

    ticked = [year for year, key in keys.items() if st.session_state[key]]
    if len(ticked) == len(years):
        summary = "All"
    elif not ticked:
        summary = "None"
    else:
        summary = years_text(ticked)

    with st.popover(f"Years: {summary}"):
        for year, key in keys.items():
            st.checkbox(str(year), key=key)

    return [year for year, key in keys.items() if st.session_state[key]]


# Month pills with an "All" pill first. Every month (and All) is ticked from the start.
# Ticking All ticks every month, unticking All unticks everything.
# Unticking one month also unticks All, and ticking every month by hand ticks All too.
# The previous selection is kept, so the callback can tell what was just clicked
def month_selector(available_months, key):
    options = [ALL_MONTHS] + list(available_months)
    previous_key = f"{key}_previous"

    if key not in st.session_state:
        st.session_state[key] = list(options)

    # Removes months that don't exist for the chosen connections and years (the widget fails on unknown options)
    selection = [m for m in st.session_state[key] if m in options]
    # All means every month, also months that came with newly chosen connections or years
    if ALL_MONTHS in selection:
        selection = list(options)
    st.session_state[key] = selection
    st.session_state[previous_key] = selection

    def update_all_pill():
        new = set(st.session_state[key] or [])
        old = set(st.session_state[previous_key])
        months = set(available_months)

        if ALL_MONTHS in new and ALL_MONTHS not in old:      # All was ticked
            new = months | {ALL_MONTHS}
        elif ALL_MONTHS in old and ALL_MONTHS not in new:    # All was unticked
            new = set()
        elif months <= new:                                  # every month is ticked
            new.add(ALL_MONTHS)
        else:                                                # at least one month is unticked
            new.discard(ALL_MONTHS)

        st.session_state[key] = [option for option in options if option in new]

    st.pills(
        "Months",
        options=options,
        selection_mode="multi",
        format_func=lambda month: "All" if month == ALL_MONTHS else calendar.month_name[month],
        key=key,
        on_change=update_all_pill,
    )
    return [m for m in st.session_state[key] if m != ALL_MONTHS]


# ---------------------------------------------------------------------------------------------
# Smart titles
# ---------------------------------------------------------------------------------------------

# "2025", "2024–2026" if the years follow each other, otherwise "2024, 2026"
def years_text(years):
    years = sorted(years)
    if len(years) == 1:
        return str(years[0])
    if years == list(range(years[0], years[-1] + 1)):
        return f"{years[0]}–{years[-1]}"
    return ", ".join(str(year) for year in years)


# Describes the chosen months and years: just the years if all months are chosen,
# a range of months if they follow each other, otherwise a list
def months_text(chosen_months, available_months, years):
    period = years_text(years)
    chosen = sorted(chosen_months)
    if chosen == sorted(available_months):
        return period
    if chosen == list(range(chosen[0], chosen[-1] + 1)):
        if len(chosen) == 1:
            return f"{calendar.month_name[chosen[0]]} {period}"
        return f"{calendar.month_name[chosen[0]]}–{calendar.month_name[chosen[-1]]} {period}"
    return ", ".join(calendar.month_abbr[m] for m in chosen) + f" {period}"


# ---------------------------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------------------------

# Mixes a colour with white. amount 0 = the colour itself, 1 = white. Used for the connection lines under the total
def _lighter(hex_color, amount):
    red, green, blue = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return "rgb({}, {}, {})".format(*(round(c + (255 - c) * amount) for c in (red, green, blue)))

# Title on several lines: a short headline first, then the details (which connections), wrapped to the given width.
# The space above the chart grows with the number of lines, so the title never runs into the chart
def _apply_title(fig, headline, details, width):
    lines = [headline] + textwrap.wrap(details, width)
    fig.update_layout(title_text="<br>".join(lines), margin={"t": 40 + 24 * len(lines)})


# Aggregated: Out/Into pie. Per connection: two rings, Out/Into inside and the connections outside
def pie_chart(totals, view, headline, details):
    if view == "Aggregated":
        by_direction = totals.groupby("direction", as_index=False)["gwh"].sum()
        fig = px.pie(
            by_direction, names="direction", values="gwh",
            color="direction", color_discrete_map=DIRECTION_COLORS,
        )
        fig.update_traces(texttemplate="%{percent:.1%}<br>%{value:,.0f} GWh")
    else:
        fig = px.sunburst(
            totals, path=["direction", "label"], values="gwh",
            color="direction", color_discrete_map=DIRECTION_COLORS,
        )
        fig.update_traces(
            texttemplate="%{label}<br>%{value:,.0f} GWh",
            hovertemplate="%{label}: %{value:,.0f} GWh (%{percentParent:.1%} of %{parent})<extra></extra>",
        )

    _apply_title(fig, headline, details, width=45)   # the pie only gets half the page
    return fig


# Hourly flow. order = the connection labels in the order they were chosen
def line_chart(hourly, view, layout, headline, details, order):
    total = hourly.groupby(["time", "direction"], as_index=False)["mwh"].sum()

    # Aggregated: the chosen connections added together, one line per direction
    if view == "Aggregated":
        fig = px.line(
            total, x="time", y="mwh", color="direction",
            color_discrete_map=DIRECTION_COLORS, labels=AXIS_LABELS,
        )
        fig.update_traces(line={"width": 1.2})
        fig.update_layout(hovermode="x unified")

    # One small plot per connection (and one for the total in Both), each with its own y-axis
    elif layout == "One plot per connection":
        parts = [hourly.assign(series=hourly["label"])]
        series_order = list(order)
        if view == "Both":
            parts.insert(0, total.assign(series="Total"))
            series_order = ["Total"] + series_order

        fig = px.line(
            pd.concat(parts, ignore_index=True), x="time", y="mwh", color="direction",
            facet_row="series", category_orders={"series": series_order},
            color_discrete_map=DIRECTION_COLORS, labels=AXIS_LABELS,
            height=max(400, 200 * len(series_order)),
        )
        fig.for_each_annotation(lambda annotation: annotation.update(text=annotation.text.split("=", 1)[-1]))
        fig.update_yaxes(matches=None, title_text="")
        fig.update_traces(line={"width": 1.2})
        fig.update_layout(hovermode="x unified")
        headline += " (MWh per hour)"   # the y-axis titles are removed, so the unit goes in the title

    # Same plot: each connection as a thin line in a lighter shade of its direction's colour.
    # In Both, the total is drawn last, so it lies on top as a thick line
    else:
        fig = go.Figure()
        for direction, color in DIRECTION_COLORS.items():
            if direction not in set(hourly["direction"]):   # the direction is filtered away
                continue
            for i, label in enumerate(order):
                part = hourly[(hourly["direction"] == direction) & (hourly["label"] == label)]
                shade = _lighter(color, (0.25 if view == "Both" else 0) + 0.45 * i / max(len(order) - 1, 1))
                fig.add_trace(go.Scatter(
                    x=part["time"], y=part["mwh"], mode="lines", name=f"{direction}: {label}",
                    legendgroup=direction, line={"color": shade, "width": 1},
                ))
            if view == "Both":
                part = total[total["direction"] == direction]
                fig.add_trace(go.Scatter(
                    x=part["time"], y=part["mwh"], mode="lines", name=f"{direction}: total",
                    legendgroup=direction, line={"color": color, "width": 2.2},
                ))
        fig.update_layout(xaxis_title=AXIS_LABELS["time"], yaxis_title=AXIS_LABELS["mwh"], hovermode="closest")

    _apply_title(fig, headline, details, width=110)   # the plot gets the whole width
    return fig