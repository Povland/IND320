# Weather per area: looks up the area's ERA5 grid cells, downloads them with ind320.openmeteo, and averages them
# over the area. The averages are stored in MongoDB, one document per area, year and number of random locations,
# where the app reads them.
#
# Region identifiers: "NO1"-"NO5" for the price areas (area_type EL), "VASS1"-"VASS3" for the watercourse areas.
# points_per_area is how many random locations were drawn in each area (see ind320.areas). It decides the grid
# cells and their weights, so data made with different numbers is stored separately

from datetime import datetime, timezone

import pandas as pd

from ind320 import areas, openmeteo

COLLECTION = "weather"

# All regions: the five price areas and the three watercourse areas
ALL_REGIONS = ["NO1", "NO2", "NO3", "NO4", "NO5", "VASS1", "VASS2", "VASS3"]

# One document per area, year and number of locations
INDEX_KEYS = [("area_type", 1), ("area_nr", 1), ("year", 1), ("points_per_area", 1)]


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


# The grid cells of one region, with n_points. Computed from the shapefiles for the given number of
# locations (ind320.areas.grid_cells_for), unless a table is given
def region_cells(region, points_per_area=areas.POINTS_PER_AREA, cells=None):
    if cells is None:
        cells = areas.grid_cells_for(points_per_area)
    area_type, area_nr = parse_region_id(region)
    found = cells[(cells["area_type"] == area_type) & (cells["area_nr"] == area_nr)]
    if found.empty:
        raise ValueError(f"No grid cells for {region}")
    return found


# Average over a region, one row per hour. Each cell is weighted by n_points.
# Only cells with a value count in the weights, so a missing value doesn't pull the average down
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
# progress(done, total) is passed on to fetch_cells, for a progress bar in the app
def download_region_weather(region, start, end, points_per_area=areas.POINTS_PER_AREA, cells=None, progress=None):
    found = region_cells(region, points_per_area, cells)
    print(f"{region}: {found['n_points'].sum()} locations in {len(found)} grid cells")
    cell_weather = openmeteo.fetch_cells(zip(found["latitude"], found["longitude"]), start, end, progress=progress)
    return region_average(cell_weather, found)


# The unique grid cells (latitude, longitude) of several regions. EL and VASS cover the same land, so many are shared
def unique_cells(regions, points_per_area=areas.POINTS_PER_AREA, cells=None):
    if cells is None:
        cells = areas.grid_cells_for(points_per_area)
    found = pd.concat([region_cells(region, points_per_area, cells) for region in regions])
    return found[["latitude", "longitude"]].drop_duplicates()


# Downloads several regions at once: every grid cell is downloaded only once, even if it belongs to more than one region.
# The cells are downloaded first (without holding them all in memory), then each region's average is computed
# from its own cells in the cache. Returns {region: hourly average}
def download_regions_weather(regions, start, end, points_per_area=areas.POINTS_PER_AREA, cells=None, progress=None):
    if cells is None:
        cells = areas.grid_cells_for(points_per_area)
    all_cells = unique_cells(regions, points_per_area, cells)
    print(f"{len(regions)} regions: {len(all_cells)} unique grid cells")
    openmeteo.fetch_cells(zip(all_cells["latitude"], all_cells["longitude"]), start, end, progress=progress, load=False)

    averages = {}
    for region in regions:
        found = region_cells(region, points_per_area, cells)
        cell_weather = openmeteo.load_cells(zip(found["latitude"], found["longitude"]), start, end)
        averages[region] = region_average(cell_weather, found)
    return averages


# The MongoDB key of one stored average
def _key(region, year, points_per_area):
    area_type, area_nr = parse_region_id(region)
    return {"area_type": area_type, "area_nr": area_nr, "year": year, "points_per_area": points_per_area}


# Stores one calendar year of a region's average in MongoDB (replaces it if it is already there)
def save_region_weather(db, region, average, points_per_area=areas.POINTS_PER_AREA):
    years = average.index.year.unique()
    if len(years) != 1:
        raise ValueError(f"Store one calendar year at a time, got {list(years)}")
    key = _key(region, int(years[0]), points_per_area)

    document = {
        **key,
        "region": region_id(key["area_type"], key["area_nr"]),
        "n_cells": len(region_cells(region, points_per_area)),
        "time": average.index.to_pydatetime().tolist(),
        **{variable: average[variable].tolist() for variable in openmeteo.HOURLY_VARIABLES},
        "first_hour": average.index[0].to_pydatetime(),
        "last_hour": average.index[-1].to_pydatetime(),
        "source": "ERA5 via Open-Meteo",
        "stored_at": datetime.now(timezone.utc),
    }

    collection = db[COLLECTION]
    collection.create_index(INDEX_KEYS, unique=True)
    collection.replace_one(key, document, upsert=True)


# One region's average for one year from MongoDB, with time (UTC) as the index. None if it isn't stored
def load_region_weather(db, region, year, points_per_area=areas.POINTS_PER_AREA):
    document = db[COLLECTION].find_one(_key(region, year, points_per_area), {"_id": 0})
    if document is None:
        return None

    # MongoDB returns UTC times without time zone info, so they are marked as UTC
    index = pd.DatetimeIndex(pd.to_datetime(document["time"], utc=True), name="time")
    variables = [variable for variable in openmeteo.HOURLY_VARIABLES if variable in document]
    return pd.DataFrame({variable: document[variable] for variable in variables}, index=index)


# What is stored: one row per region, year and number of locations, with the first and last hour
def stored_weather(db):
    columns = ["region", "area_type", "area_nr", "year", "points_per_area", "first_hour", "last_hour", "stored_at"]
    documents = db[COLLECTION].find({}, {"_id": 0, **{column: 1 for column in columns}})
    return pd.DataFrame(list(documents), columns=columns).sort_values(["area_type", "area_nr", "year", "points_per_area"])


# One-time update of documents stored before the number of locations was part of the key:
# they were all made with 100 locations, so they get points_per_area = 100. The old unique index
# (area, year) is removed, since it would stop the same area and year from being stored with another number.
# Safe to run more than once: it only changes documents without the field. Returns how many were updated
def migrate_weather_documents(db):
    collection = db[COLLECTION]
    updated = collection.update_many(
        {"points_per_area": {"$exists": False}}, {"$set": {"points_per_area": areas.POINTS_PER_AREA}}
    ).modified_count

    for name, index in collection.index_information().items():
        if [field for field, _ in index["key"]] == ["area_type", "area_nr", "year"]:
            collection.drop_index(name)

    collection.create_index(INDEX_KEYS, unique=True)
    return updated