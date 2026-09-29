from pathlib import Path

import pandas as pd
import streamlit as st

DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "reservoirs.csv"

@st.cache_data
# To cashe the data loading function, we can use the @st.cache_data decorator
# This will store the results of the function in a cache, and the function will return whats in the cache
def load_reservoir_data():
    #loads data from csv file
    reservoir_data = pd.read_csv(DATA_PATH)

    # Renaming headers
    reservoir_data.columns = ["date_id", "area_type", "area_nr", "iso_aar", "iso_week", "filling_degree", "capacity_TWh", "filling_TWh", "next_publishing_date", "filling_degree_last_week", "filling_degree_change"]
    
    # Sets date_id as datetime and sets it as index
    reservoir_data["date_id"] = pd.to_datetime(reservoir_data["date_id"])
    reservoir_data = reservoir_data.set_index("date_id")

    # Sorts the dataframe by index (date_id) in ascending order
    reservoir_data = reservoir_data.sort_index()

    # Returns data
    return reservoir_data