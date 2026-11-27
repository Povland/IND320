from datetime import date, timedelta

import plotly.express as px
import streamlit as st

from utils.data import load_rates

st.title("Currency")
st.write(
    "Exchange rates from Norges Bank: how many kroner one euro and one US dollar cost. Norges Bank publishes "
    "one rate per business day at about 16:00 Norwegian time. The weekly rates are the average of each week, "
    "with weeks ending on Sunday like NVE's, so they line up with the reservoir data."
)

# ---------------------------------------------------------------------------------------------
# Controls: the period (default the last two years), the currencies, and daily or weekly
# ---------------------------------------------------------------------------------------------
today = date.today()
left, middle, right = st.columns([2, 2, 1])
period = left.date_input(
    "Period", value=(today - timedelta(days=730), today), min_value=date(1995, 1, 1), max_value=today,
    format="DD.MM.YYYY", key="currency_period",
)
currencies = middle.multiselect("Currencies", ["EUR", "USD"], default=["EUR", "USD"], key="currency_currencies")
weekly = right.toggle("Weekly", value=False, key="currency_weekly",
                      help="The average of each week (Monday to Sunday) instead of each business day.")

# date_input gives one date while the second is being picked
if len(period) != 2:
    st.info("Choose the end of the period.")
    st.stop()
if not currencies:
    st.info("Choose at least one currency.")
    st.stop()
start, end = period

rates = load_rates(start, end, weekly)
if rates.empty:
    st.warning("No exchange rates for the chosen period. Norges Bank only publishes rates on business days.")
    st.stop()
rates = rates[currencies]

# ---------------------------------------------------------------------------------------------
# The plot: one line per currency
# ---------------------------------------------------------------------------------------------
resolution = "weekly average" if weekly else "daily"
plot_data = rates.reset_index().melt(id_vars="date", var_name="Currency", value_name="NOK")
fig = px.line(plot_data, x="date", y="NOK", color="Currency",
              title=f"NOK per EUR and USD ({resolution}), {start:%d.%m.%Y} to {end:%d.%m.%Y}",
              labels={"date": "Date", "NOK": "NOK per unit"},
              color_discrete_map={"EUR": "#2a78d6", "USD": "#eb6834"})
fig.update_layout(hovermode="x unified")
st.plotly_chart(fig, width="stretch")

# The latest rate of each currency, and the change over the period
columns = st.columns(len(currencies))
for column, currency in zip(columns, currencies):
    values = rates[currency].dropna()
    if values.empty:
        continue
    change = values.iloc[-1] / values.iloc[0] - 1
    column.metric(f"{currency}, {values.index[-1]:%d.%m.%Y}", f"{values.iloc[-1]:.4f} NOK",
                  delta=f"{change:+.1%} over the period", delta_color="off",
                  help="A higher rate means a weaker krone.")

with st.expander("Show the rates as a table"):
    st.dataframe(rates.style.format("{:.4f}"), width="stretch")

st.caption("Source: Norges Bank, https://www.norges-bank.no/en/topics/Statistics/open-data/")