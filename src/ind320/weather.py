# Weather per area: looks up the area's ERA5 grid cells, downloads them with ind320.openmeteo, and averages them
# over the area. The averages are stored in MongoDB, one document per area and year, where the app reads them.
#
# Region identifiers: "NO1"-"NO5" for the price areas (area_type EL), "VASS1"-"VASS3" for the watercourse areas

from datetime import datetime, timezone

import pandas as pd

from ind320 import areas, openmeteo

COLLECTION = "weather"


# "NO3" -> ("EL", 3), "VASS1" -> ("VASS", 1). Spaces and lower case are accepted ("no 3")
def parse_region_id(region):
    region = region.replace(" ", "").upper()
    if region.startswith("VASS"):
        return "VASS", int(region[4:])
    if region.startswith("NO"):
        return "EL", int(region[2:])
    raise ValueError(f"Unknown region: {region}. Use NO1-NO5 or VASS1-VASS3")


# ("EL", 3) -> "NO3", ("VASS", 1) -> "VASS1"
def region_id(area_type, area_nr):
    return f"NO{area_nr}" if area_type == "EL" else f"{area_type}{area_nr}"


# The grid cells of one region, with n_points (from data/grid_cells.csv unless a table is given)
def region_cells(region, cells=None):
    if cells is None:
        cells = areas.load_grid_cells()
    area_type, area_nr = parse_region_id(region)
    found = cells[(cells["area_type"] == area_type) & (cells["area_nr"] == area_nr)]
    if found.empty:
        raise ValueError(f"No grid cells for {region}")
    return found


# Average over a region, one row per hour. Each cell is weighted by n_points.
# Only cells with a value count in the weights, so a missing value doesn't pull the average down.
# A variable without any values (like snow_depth for era5) becomes NaN
def region_average(cell_weather, cells):
    data = cell_weather.merge(cells[["latitude", "longitude", "n_points"]], on=["latitude", "longitude"])

    averages = {}
    for variable in openmeteo.HOURLY_VARIABLES:
        values = pd.to_numeric(data[variable], errors="coerce")       # None -> NaN
        weights = data["n_points"].where(values.notna(), 0)
        weighted_sum = (values.fillna(0) * weights).groupby(data["time"]).sum()
        averages[variable] = weighted_sum / weights.groupby(data["time"]).sum()
    return pd.DataFrame(averages)


# The download function: region identifier + time interval -> the region's grid cells -> hourly ERA5 data,
# averaged over the region. Cells already downloaded are read from the cache instead.
# progress(done, total) is passed on to fetch_cells, for a progress bar in the app later
def download_region_weather(region, start, end, cells=None, progress=None):
    found = region_cells(region, cells)
    print(f"{region}: {found['n_points'].sum()} locations in {len(found)} grid cells")
    cell_weather = openmeteo.fetch_cells(zip(found["latitude"], found["longitude"]), start, end, progress=progress)
    return region_average(cell_weather, found)


# Stores one calendar year of a region's average in MongoDB (replaces it if it is already there)
def save_region_weather(db, region, average):
    area_type, area_nr = parse_region_id(region)
    years = average.index.year.unique()
    if len(years) != 1:
        raise ValueError(f"Store one calendar year at a time, got {list(years)}")
    year = int(years[0])

    document = {
        "region": region_id(area_type, area_nr),
        "area_type": area_type,
        "area_nr": area_nr,
        "year": year,
        "time": average.index.to_pydatetime().tolist(),
        **{variable: average[variable].tolist() for variable in openmeteo.HOURLY_VARIABLES},
        "first_hour": average.index[0].to_pydatetime(),
        "last_hour": average.index[-1].to_pydatetime(),
        "source": "ERA5 via Open-Meteo",
        "stored_at": datetime.now(timezone.utc),
    }

    collection = db[COLLECTION]
    key = {"area_type": area_type, "area_nr": area_nr, "year": year}
    collection.create_index([("area_type", 1), ("area_nr", 1), ("year", 1)], unique=True)
    collection.replace_one(key, document, upsert=True)


# One region's average for one year from MongoDB, with time (UTC) as the index. None if it isn't stored
def load_region_weather(db, region, year):
    area_type, area_nr = parse_region_id(region)
    document = db[COLLECTION].find_one({"area_type": area_type, "area_nr": area_nr, "year": year}, {"_id": 0})
    if document is None:
        return None

    # MongoDB returns UTC times without time zone info, so they are marked as UTC
    index = pd.DatetimeIndex(pd.to_datetime(document["time"], utc=True), name="time")
    variables = [variable for variable in openmeteo.HOURLY_VARIABLES if variable in document]
    return pd.DataFrame({variable: document[variable] for variable in variables}, index=index)


# What is stored: one row per region and year, with the first and last hour
def stored_weather(db):
    columns = ["region", "area_type", "area_nr", "year", "first_hour", "last_hour", "stored_at"]
    documents = db[COLLECTION].find({}, {"_id": 0, **{column: 1 for column in columns}})
    return pd.DataFrame(list(documents), columns=columns).sort_values(["area_type", "area_nr", "year"])