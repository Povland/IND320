import calendar

import plotly.express as px
import streamlit as st

from utils.data import load_connections, load_hourly_flows, load_months, load_yearly_totals, load_years

st.title("Cross-border flows")
st.write(
    "Physical power flows between Norway and its neighbouring countries, from ENTSO-E. "
    "Choose a connection and a year on the left, and which months to show on the right."
)

# Same colours and names for the directions as in the notebook
DIRECTION_COLORS = {"Out of Norway": "#2a78d6", "Into Norway": "#eb6834"}
DIRECTION_LABELS = {"out": "Out of Norway", "in": "Into Norway"}

try:
    connections = load_connections()
except Exception as error:   # missing secrets, network, IP not allowed in Atlas...
    st.error(f"Could not read from MongoDB: {error}")
    st.stop()

if not connections:
    st.warning("No cross-border data in MongoDB yet. Run the ENTSO-E part of the notebook first.")
    st.stop()

left, right = st.columns(2)

# Left side: connection (radio buttons) and year (dropdown), with a pie chart of the year's total
with left:
    connection = st.radio("Connection", options=connections, horizontal=True)
    years = load_years(connection)
    # 2025 is the default, since it is the only full year in the data
    year = st.selectbox("Year", options=years, index=years.index(2025) if 2025 in years else len(years) - 1)

    totals = load_yearly_totals(connection, year)
    totals["direction"] = totals["direction"].map(DIRECTION_LABELS)

    pie = px.pie(
        totals,
        names="direction",
        values="gwh",
        color="direction",
        color_discrete_map=DIRECTION_COLORS,
        title=f"Total flow on {connection} in {year} (GWh)",
    )
    pie.update_traces(texttemplate="%{percent:.1%}<br>%{value:,.0f} GWh")
    st.plotly_chart(pie, width="stretch")

    # 2024 and 2026 are not full years in the data
    months_in_year = load_months(connection, year)
    if len(months_in_year) < 12:
        st.caption(
            f"Note: {year} only has data for {calendar.month_name[months_in_year[0]]}"
            f"–{calendar.month_name[months_in_year[-1]]}."
        )

# Right side: which months to include (pills), with a line plot of the hourly flow
with right:
    chosen_months = st.pills(
        "Months",
        options=months_in_year,
        selection_mode="multi",
        default=[months_in_year[0]],
        format_func=lambda month: calendar.month_abbr[month],
        key=f"months_{connection}_{year}",   # own selection per connection and year
    )

    if not chosen_months:
        st.info("No months selected. Choose one or more months above.")
    else:
        hourly = load_hourly_flows(connection, year, tuple(sorted(chosen_months)))
        hourly["direction"] = hourly["direction"].map(DIRECTION_LABELS)

        line = px.line(
            hourly,
            x="time",
            y="mwh",
            color="direction",
            color_discrete_map=DIRECTION_COLORS,
            title=f"Hourly flow on {connection}, {year}",
            labels={"time": "Time (Norwegian time)", "mwh": "MWh per hour", "direction": "Direction"},
        )
        line.update_traces(line={"width": 1.2})
        line.update_layout(hovermode="x unified")
        st.plotly_chart(line, width="stretch")

# Where the data comes from
with st.expander("About the data"):
    st.markdown("""
**Source:** [ENTSO-E Transparency Platform](https://transparency.entsoe.eu/), physical cross-border flows,
fetched through the ENTSO-E API with the Python library `entsoe-py`.

**Processing (in the notebook `notebooks/Oblig2.ipynb`):**
1. Hourly flows for the last two years were fetched for Norway's 9 cross-border connections, both directions.
   Connections that report every 15 minutes were averaged to one value per hour (MW over one hour = MWh).
2. The data was stored in a local Cassandra database using Spark.
3. Spark extracted the relevant columns and grouped them into one document per connection, year, month and direction.
4. The documents were stored in MongoDB, which this page reads from.

**Directions:** "Out of Norway" is flow from the Norwegian price area to the foreign area, "Into Norway" the opposite.
Times are shown in Norwegian time. 2024 and 2026 are partial years (the data covers October 2024 to October 2026).
""")