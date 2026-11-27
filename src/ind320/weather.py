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
        "variables": list(openmeteo.HOURLY_VARIABLES),
        "settings": openmeteo.settings_code(),
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
# Why a stored document is not complete, or "" if it is: it must have every current variable,
# come from the current API settings, and cover the whole year up to 31 December 23:00
def incomplete_reason(variables, settings, year, last_hour):
    reasons = []
    if settings != openmeteo.settings_code():
        reasons.append("other API settings")
    stored_variables = variables if isinstance(variables, list) else []
    lacking = [variable for variable in openmeteo.HOURLY_VARIABLES if variable not in stored_variables]
    if lacking:
        reasons.append("missing " + ", ".join(lacking))
    if pd.isna(last_hour) or pd.Timestamp(last_hour) < pd.Timestamp(f"{int(year)}-12-31 23:00"):
        reasons.append("incomplete year")
    return "; ".join(reasons)


# What is stored: one row per region, year and number of locations, with the variables, the API settings,
# the first and last hour, and whether it is complete (see incomplete_reason)
def stored_weather(db):
    columns = ["region", "area_type", "area_nr", "year", "points_per_area", "variables", "settings",
               "first_hour", "last_hour", "stored_at"]
    documents = db[COLLECTION].find({}, {"_id": 0, **{column: 1 for column in columns}})
    stored = pd.DataFrame(list(documents), columns=columns)
    stored["reason"] = [
        incomplete_reason(row.variables, row.settings, row.year, row.last_hour) for row in stored.itertuples()
    ]
    stored["complete"] = stored["reason"] == ""
    return stored.sort_values(["area_type", "area_nr", "year", "points_per_area"]).reset_index(drop=True)


# What is missing for the given regions, years and number of locations: one row per region and year that is
# not stored, or stored but not complete, with the reason. Empty table if everything is there
def missing_weather(db, regions, years, points_per_area=areas.POINTS_PER_AREA):
    stored = stored_weather(db)
    stored = stored[stored["points_per_area"] == points_per_area]
    by_key = {(row.region, int(row.year)): row for row in stored.itertuples()}

    rows = []
    for year in years:
        for region in regions:
            row = by_key.get((region, int(year)))
            reason = "not stored" if row is None else row.reason
            if reason:
                area_type, area_nr = parse_region_id(region)
                rows.append({"region": region, "area_type": area_type, "area_nr": area_nr,
                             "year": int(year), "reason": reason})
    return pd.DataFrame(rows, columns=["region", "area_type", "area_nr", "year", "reason"])


# Every variable a document might hold, including ones that are no longer downloaded (for the migration below)
KNOWN_VARIABLES = [*openmeteo.HOURLY_VARIABLES, "snow_depth"]


# One-time update of documents stored before the key and the records were added. Safe to run more than once:
#   - points_per_area: documents without it were all made with 100 locations
#   - variables: set from the variable fields each document actually holds
#   - settings: documents without it were all downloaded with today's API settings
# The old unique index (area, year) is removed, since it would stop the same area and year from being
# stored with another number of locations. Returns how many documents were updated
def migrate_weather_documents(db):
    collection = db[COLLECTION]
    updated = collection.update_many(
        {"points_per_area": {"$exists": False}}, {"$set": {"points_per_area": areas.POINTS_PER_AREA}}
    ).modified_count

    # variables: added one at a time, only for documents that hold that field
    without_variables = {"variables": {"$exists": False}}
    to_record = list(collection.find(without_variables, {"_id": 1, **{variable: 1 for variable in KNOWN_VARIABLES}}))
    for document in to_record:
        held = [variable for variable in KNOWN_VARIABLES if variable in document]
        collection.update_one({"_id": document["_id"]}, {"$set": {"variables": held}})
    updated += len(to_record)

    updated += collection.update_many(
        {"settings": {"$exists": False}}, {"$set": {"settings": openmeteo.settings_code()}}
    ).modified_count

    for name, index in collection.index_information().items():
        if [field for field, _ in index["key"]] == ["area_type", "area_nr", "year"]:
            collection.drop_index(name)

    collection.create_index(INDEX_KEYS, unique=True)
    return updated



# The weather variables, defined once for the whole project: the name shown, the unit, and how a day and a week are
# summed up (temperature as a mean, the amounts as sums). The pages and the weekly aggregation all read from here
VARIABLES = {
    "temperature_2m": {"name": "Temperature", "unit": "°C", "weekly": "mean"},
    "precipitation": {"name": "Precipitation", "unit": "mm", "weekly": "sum"},
    "rain": {"name": "Rain", "unit": "mm", "weekly": "sum"},
    "snowfall": {"name": "Snowfall", "unit": "cm", "weekly": "sum"},
    "et0_fao_evapotranspiration": {"name": "Evaporation", "unit": "mm", "weekly": "sum"},
}

# How each variable is summed up over a day and a week, and the amounts (which can't be negative)
WEEKLY_AGGREGATION = {variable: info["weekly"] for variable, info in VARIABLES.items()}
AMOUNTS = [variable for variable, info in VARIABLES.items() if info["weekly"] == "sum"]


# The label of a variable: "Precipitation (mm)" for hourly values, "Precipitation (mm per week)" or
# "Temperature (°C, weekly mean)" for weekly values
def variable_label(variable, weekly=False):
    info = VARIABLES[variable]
    if not weekly:
        return f"{info['name']} ({info['unit']})"
    if info["weekly"] == "mean":
        return f"{info['name']} ({info['unit']}, weekly mean)"
    return f"{info['name']} ({info['unit']} per week)"

# NVE's weeks are Norwegian ISO weeks, Monday to Sunday, with the Sunday as date_id
WEEK_TIMEZONE = "Europe/Oslo"


# Aggregates each column of frame by rule ("D" or "W-SUN") as WEEKLY_AGGREGATION says.
# Sums use min_count=1, so a period without any values becomes NaN instead of 0
def _aggregate(frame, rule):
    parts = []
    for column, how in WEEKLY_AGGREGATION.items():
        if column in frame:
            resampled = frame[column].resample(rule)
            parts.append(resampled.mean() if how == "mean" else resampled.sum(min_count=1))
    return pd.concat(parts, axis=1)


# Hourly weather (UTC index, as stored) -> one row per week ending on Sunday, like NVE's date_id.
# The hours are first moved to Norwegian time, so a week runs Monday 00:00 to Sunday 23:59 local time, as NVE's.
# It goes through whole days first: with hourly timestamps, "W-SUN" would put Sunday's hours in the next week.
# Days with fewer than 23 hours (23 is the day the clocks go forward) and weeks with fewer than 7 days are
# dropped, so the first and last week of a year are only kept when they are complete.
# The index has no time zone, so it can be joined directly with the reservoir data
def weekly_weather(hourly):
    local = hourly.tz_convert(WEEK_TIMEZONE)

    hours_per_day = local.iloc[:, 0].resample("D").count()
    daily = _aggregate(local, "D")[hours_per_day >= 23]

    days_per_week = daily.iloc[:, 0].resample("W-SUN").count()
    weekly = _aggregate(daily, "W-SUN")[days_per_week == 7]

    weekly.index = weekly.index.tz_localize(None).normalize()
    weekly.index.name = "date_id"
    return weekly