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


# Creates an ENTSO-E client. The token is given by the app (from st.secrets), or read from No_sync/entsoe.env
# (ENTSOE_TOKEN=...) when it isn't, as in the notebook
def get_client(token=None):
    if token is None:
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


# Fetches physical cross-border flows to and from Norway, one row per hour, connection and direction. Defaults to the last two years and all connections.
# progress(done, total) is called after each series (each connection has two, one per direction), for a progress bar in the app
def fetch_crossborder_flows(start=None, end=None, connections=CONNECTIONS, client=None, progress=None):
    if start is None or end is None:
        start, end = last_two_years()
    client = client or get_client()

    frames = []
    total = len(connections) * 2
    done = 0
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
            else:
                frames.append(to_hourly_rows(flow, norwegian_area, foreign_area, direction))

            done += 1
            if progress:
                progress(done, total)

    if not frames:
        return pd.DataFrame(columns=COLUMNS)
    return pd.concat(frames, ignore_index=True)[COLUMNS]


# ---------------------------------------------------------------------------------------------
# Storing in MongoDB without Cassandra and Spark (used by the app).
# The Oblig2 notebook goes ENTSO-E -> Cassandra -> Spark -> MongoDB. The app goes straight from ENTSO-E to
# MongoDB, grouping the hours with pandas, since an update is only a month or two of data. The documents
# have the same format, so the Cross-border page reads both the same way:
# one document per connection, year, month and direction (in Norwegian time), with the hours as lists
# (time in UTC, mwh) and the month's total (total_mwh)
# ---------------------------------------------------------------------------------------------

FLOWS_COLLECTION = "crossborder_flows"
FLOW_KEY = ["connection", "year", "month", "direction"]


# Groups hourly flows (from fetch_crossborder_flows) into one document per connection, year, month and direction
def monthly_documents(flows):
    if flows.empty:
        return []
    local = flows["time"].dt.tz_convert(TIMEZONE)
    grouped = flows.assign(year=local.dt.year, month=local.dt.month).sort_values("time").groupby(FLOW_KEY)

    documents = []
    for (connection, year, month, direction), group in grouped:
        documents.append({
            "connection": connection,
            "year": int(year),
            "month": int(month),
            "direction": direction,
            "total_mwh": float(group["mwh"].sum()),
            "time": [time.to_pydatetime() for time in group["time"]],
            "mwh": group["mwh"].astype(float).tolist(),
        })
    return documents


# Stores the documents, replacing any that are already there for the same connection, year, month and direction
def save_monthly_documents(collection, documents):
    for document in documents:
        collection.replace_one({key: document[key] for key in FLOW_KEY}, document, upsert=True)
    collection.create_index([("connection", 1), ("year", 1), ("month", 1)])


# The newest (year, month) stored, or None if the collection is empty
def latest_month(collection):
    document = collection.find_one({}, {"_id": 0, "year": 1, "month": 1}, sort=[("year", -1), ("month", -1)])
    return None if document is None else (document["year"], document["month"])


# The last hour stored (UTC), or None if the collection is empty. Only the last hour of each document in the
# newest month is read ($slice), not the whole lists
def last_stored_hour(collection):
    latest = latest_month(collection)
    if latest is None:
        return None
    documents = collection.find(
        {"year": latest[0], "month": latest[1]}, {"_id": 0, "mwh": 0, "time": {"$slice": -1}},
    )
    hours = [pd.Timestamp(document["time"][-1], tz="UTC") for document in documents if document.get("time")]
    return max(hours) if hours else None


# Brings the collection up to date: fetches from the start of the newest stored month (which is usually only
# partly stored) up to now, and replaces those months. If nothing is stored, it fetches the last two years.
# Returns (start, end, number of documents stored)
def update_crossborder(collection, client, progress=None):
    end = pd.Timestamp.now(tz=TIMEZONE).floor("h")
    latest = latest_month(collection)
    if latest is None:
        start, end = last_two_years()
    else:
        start = pd.Timestamp(year=latest[0], month=latest[1], day=1, tz=TIMEZONE)

    flows = fetch_crossborder_flows(start, end, client=client, progress=progress)
    documents = monthly_documents(flows)
    save_monthly_documents(collection, documents)
    return start, end, len(documents)