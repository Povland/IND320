import pandas as pd
from entsoe import EntsoePandasClient
from entsoe.exceptions import NoMatchingDataError
from entsoe.mappings import NEIGHBOURS

from ind320.config import load_env

# ENTSO-E reports in local time. Everything is converted to UTC before it is stored
TIMEZONE = "Europe/Oslo"

NORWEGIAN_AREAS = ["NO_1", "NO_2", "NO_3", "NO_4", "NO_5"]

# Cross-border connections: Norwegian price area -> foreign neighbour.
# Taken from entsoe-py's list of neighbours, skipping connections between two Norwegian areas.
# Result: NO_1-SE_3, NO_2-DE_LU, NO_2-DK_1, NO_2-NL, NO_2-GB, NO_3-SE_2, NO_4-SE_2, NO_4-FI, NO_4-SE_1
CONNECTIONS = [
    (norwegian, foreign)
    for norwegian in NORWEGIAN_AREAS
    for foreign in NEIGHBOURS[norwegian]
    if not foreign.startswith("NO_")
]

COLUMNS = ["time", "connection", "norwegian_area", "foreign_area", "direction", "mwh"]


# Creates an ENTSO-E client with the token from No_sync/entsoe.env (ENTSOE_TOKEN=...)
def get_client():
    token = load_env("entsoe.env")["ENTSOE_TOKEN"]
    return EntsoePandasClient(api_key=token)


# Start and end of the last two years, from midnight today in Norwegian time
def last_two_years():
    end = pd.Timestamp.now(tz=TIMEZONE).normalize()
    start = end - pd.DateOffset(years=2)
    return start, end


# Turns a flow series (MW) into one row per hour with energy in MWh.
# Some borders report every 15 minutes, others every hour. The mean MW over an hour equals the energy in MWh for that hour, so resampling makes all borders comparable.
def to_hourly_rows(flow, norwegian_area, foreign_area, direction):
    hourly = flow.resample("1h").mean().dropna()
    return pd.DataFrame({
        "time": hourly.index.tz_convert("UTC"),
        "connection": f"{norwegian_area}-{foreign_area}",
        "norwegian_area": norwegian_area,
        "foreign_area": foreign_area,
        "direction": direction,          # "out" = from Norway, "in" = into Norway
        "mwh": hourly.to_numpy(),
    })


# Fetches physical cross-border flows to and from Norway, one row per hour, connection and direction. Defaults to the last two years and all connections
def fetch_crossborder_flows(start=None, end=None, connections=CONNECTIONS, client=None):
    if start is None or end is None:
        start, end = last_two_years()
    client = client or get_client()

    frames = []
    for norwegian_area, foreign_area in connections:
        # Each connection has two directions, fetched as two separate series
        for from_area, to_area, direction in [
            (norwegian_area, foreign_area, "out"),
            (foreign_area, norwegian_area, "in"),
        ]:
            print(f"Fetching {from_area} -> {to_area} ...")
            try:
                flow = client.query_crossborder_flows(from_area, to_area, start=start, end=end)
            except NoMatchingDataError:
                print(f"  No data for {from_area} -> {to_area}, skipping")
                continue
            frames.append(to_hourly_rows(flow, norwegian_area, foreign_area, direction))

    return pd.concat(frames, ignore_index=True)[COLUMNS]