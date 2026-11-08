import calendar

import streamlit as st

from utils.about import crossborder_data_info
from utils.crossborder import (
    DIRECTION_LABELS, DIRECTIONS, LAYOUTS, PIE_VIEWS, VIEWS,
    connection_chooser, connection_label, line_chart, month_selector, months_text, pie_chart,
    year_selector, years_text,
)
from utils.data import load_connections, load_hourly_flows, load_months, load_yearly_totals, load_years

st.title("Cross-border flow")
st.write(
    "Physical power flows between Norway and its neighbouring countries, from ENTSO-E. "
    "On the left, choose all connections, one or more countries, or single connections, one or more years, "
    "and both directions or just one. On the right, choose the months. The hourly flow for the chosen months is shown below. "
    "With several connections, the pie chart and the plot can each show them added together or one by one."
)

PIE_VIEW_HELP = (
    "Aggregated: the chosen connections added together. "
    "Per connection: Out/Into Norway in the middle, split into the connections in the outer ring."
)
PLOT_VIEW_HELP = (
    "Aggregated: the chosen connections added together. Separate: each connection on its own. "
    "Both: the total and each connection."
)

try:
    connections = load_connections()
except Exception as error:   # missing secrets, network, IP not allowed in Atlas...
    st.error(f"Could not read from MongoDB: {error}")
    st.stop()

if not connections:
    st.warning("No cross-border data in MongoDB yet. Run the ENTSO-E part of the notebook first.")
    st.stop()


# Adds "added together" to the title text when several connections are summed in that chart
def title_text(selection, view, chosen):
    return f"{selection}, added together" if view == "Aggregated" and len(chosen) > 1 else selection


left, right = st.columns(2)

# Left side: which connections, which years, which direction, and a pie chart of the total
with left:
    chosen, selection = connection_chooser(connections)

    if not chosen:
        st.info("No connections chosen. Pick All connections, tick a country, or tick connections in the list.")
        st.stop()

    connections_key = tuple(chosen)   # tuple, so the loaders can cache on it
    chosen_years = year_selector(load_years(connections_key))

    if not chosen_years:
        st.info("No years chosen. Tick one or more years above.")
        st.stop()

    years_key = tuple(chosen_years)

    # Both directions, or just one. Applies to the pie chart and the plot
    direction = st.radio("Direction", options=DIRECTIONS, horizontal=True, key="direction")
    one_direction = direction != DIRECTIONS[0]
    shown_directions = [direction] if one_direction else list(DIRECTION_LABELS.values())
    # Goes into the headlines: "Total flow out of Norway in 2025", or nothing extra when both directions are shown
    direction_text = f" {direction[0].lower()}{direction[1:]}" if one_direction else ""

    totals = load_yearly_totals(connections_key, years_key)
    totals["direction"] = totals["direction"].map(DIRECTION_LABELS)
    totals["label"] = totals["connection"].map(connection_label)
    totals = totals[totals["direction"].isin(shown_directions)]

    pie_headline = f"Total flow{direction_text} in {years_text(chosen_years)} (GWh)"

    if one_direction and len(chosen) == 1:
        # One connection in one direction: nothing to split, so the total is shown as a number instead of a pie
        st.metric(f"{pie_headline}: {selection}", f"{totals['gwh'].sum():,.0f} GWh")
    else:
        # With one direction, Aggregated would be a single slice, so the pie shows the connections instead.
        # With both directions, the view can be chosen (only for two or more connections, since one would look the same)
        if one_direction:
            pie_view = "Per connection"
        elif len(chosen) > 1:
            pie_view = st.radio("Pie chart view", options=PIE_VIEWS, horizontal=True, help=PIE_VIEW_HELP, key="pie_view")
        else:
            pie_view = "Aggregated"

        st.plotly_chart(
            pie_chart(totals, pie_view, headline=pie_headline, details=title_text(selection, pie_view, chosen)),
            width="stretch",
        )

    # 2024 and 2026 are not full years in the data. Lists each chosen year that is missing months
    partial = []
    for year in chosen_years:
        months_of_year = load_months(connections_key, (year,))
        if len(months_of_year) < 12:
            partial.append(f"{year} ({calendar.month_name[months_of_year[0]]}–{calendar.month_name[months_of_year[-1]]})")
    if partial:
        st.caption("Note: partial years in the data: " + ", ".join(partial) + ".")

    available_months = load_months(connections_key, years_key)

# Right side: which months to include (pills), with "All" first. The months apply to every chosen year
with right:
    # Small style change: shows the month pills as a list going down instead of side by side.
    # Only applies inside the container with the key month_pills, so the pills at the top stay side by side
    st.markdown(
        "<style>.st-key-month_pills .stButtonGroup div:has(> button) "
        "{ flex-direction: column; align-items: flex-start; }</style>",
        unsafe_allow_html=True,
    )
    with st.container(key="month_pills"):
        # One selection for the whole page, kept when the connections or years change
        chosen_months = month_selector(available_months, key="months")

# Below the columns: line plot of the hourly flow, across the whole width of the page
if not chosen_months:
    st.info("No months selected. Choose one or more months above, or All.")
else:
    hourly = load_hourly_flows(connections_key, years_key, tuple(sorted(chosen_months)))
    hourly["direction"] = hourly["direction"].map(DIRECTION_LABELS)
    hourly["label"] = hourly["connection"].map(connection_label)
    hourly = hourly[hourly["direction"].isin(shown_directions)]

    # Own view for the plot, and the layout when there are connections to lay out (Separate and Both)
    plot_view, layout = "Aggregated", LAYOUTS[0]
    if len(chosen) > 1:
        view_column, layout_column = st.columns(2)
        with view_column:
            plot_view = st.radio("Plot view", options=VIEWS, horizontal=True, help=PLOT_VIEW_HELP, key="plot_view")
        with layout_column:
            if plot_view != "Aggregated":
                layout = st.radio(
                    "Plot layout",
                    options=LAYOUTS,
                    horizontal=True,
                    help="Same plot: the connections as thin lines (under the total in Both). "
                         "One plot per connection: small plots under each other, each with its own scale.",
                    key="plot_layout",
                )

    order = [connection_label(c) for c in chosen]
    st.plotly_chart(
        line_chart(
            hourly,
            plot_view,
            layout,
            headline=f"Hourly flow{direction_text}, {months_text(chosen_months, available_months, chosen_years)}",
            details=title_text(selection, plot_view, chosen),
            order=order,
        ),
        width="stretch",
    )

# Where the data comes from. The text is shared with the About page (utils/about.py)
crossborder_data_info()