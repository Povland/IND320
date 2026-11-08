import streamlit as st


# "About the data" box for the reservoir pages (Reservoir Data and Reservoir Plot)
def reservoir_data_info():
    with st.expander("About the data"):
        st.markdown("""
**Source:** [NVE Magasinstatistikk](https://www.nve.no/energi/analyser-og-statistikk/magasinstatistikk/),
fetched directly from NVE's [API](https://biapi.nve.no/magasinstatistikk/swagger/index.html)
(endpoint `HentOffentligData`) with the module `ind320.nve`.

**Processing:**
1. The app downloads all weeks and all areas in one request, since the API has no date parameters.
   The download is cached for one hour.
2. The column names are translated to English, and `date_id` is used as the index.
3. The areas and the period you choose are cut out of the full dataset in the app.

**Areas:**
- *EL 1–5*: the electricity price areas NO1–NO5, the same division ENTSO-E uses.
- *NO 0*: all of Norway.
- *VASS 1–3*: watercourse areas (Sørøst-, Vest- and Midt-Norge). This is a hydrological division
  and does not match the price areas.

**Time:** The data is weekly. Each date is the Sunday that ends the ISO week.
NVE publishes new numbers on Wednesdays at 13:00.

**Variables:** *Filling degree* is the share of the capacity that is filled, as a fraction (0.72 = 72 %).
*Filling* and *Capacity* are in TWh. *Change from last week* is the difference in filling degree from the week before.
""")