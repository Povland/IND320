# Hourly weather data from Open-Meteo's Historical Weather API (ERA5 reanalysis).
#
# Strategy for the API limit:
# The free API allows 600 calls per minute, 5000 per hour and 10000 per day. A request counts as
# n_locations x (n_days / 14) x (n_variables / 10) calls, so one location for a year with 6 variables
# is about 16 calls. 
# 
# Four things keep the download fast and inside the limit:
#   1. One request per ERA5 grid cell, not per location: ERA5 is a 0.25° grid, and all locations in
#      a cell get the same data. cell_selection=nearest makes the API use exactly the cell asked for
#      (the default picks a "suitable" land cell nearby), and elevation=nan turns off the adjustment
#      of temperature to each point's exact height, so the data is the cell's own value.
#   2. Several cells per request (comma-separated coordinates). This does not save quota, since the
#      weight is multiplied by the number of locations, but it gives far fewer requests.
#   3. Pacing: each request is filled up to about 500 calls, and the pause after it keeps the download
#      under the minute limit. If the whole job is more than one hour's limit, it is paced by the hour.
#   4. Each cell is saved as a file as soon as it arrives (data/weather_cells/). A new run skips cells
#      that are already there, so a stopped download continues where it left off, and a second run
#      costs no API calls at all.

import time
from pathlib import Path

import pandas as pd
import requests

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

# One file per grid cell and time interval: data/weather_cells/<start>-<end>/<lat>_<lon>.parquet
CACHE_PATH = Path(__file__).resolve().parents[2] / "data" / "weather_cells"

# Hourly variables, chosen for what fills and empties the reservoirs
HOURLY_VARIABLES = [
    "temperature_2m",               # °C, decides rain or snow, and when the snow melts
    "precipitation",                # mm, rain + snow (as water)
    "rain",                         # mm, reaches the reservoirs right away
    "snowfall",                     # cm, stays on the ground until it melts
    "snow_depth",                   # m, snow stored on the ground
    "et0_fao_evapotranspiration",   # mm, water lost to evaporation
]

# ERA5 is a 0.25° grid (~25 km)
ERA5_GRID = 0.25

# Limits of the free API, in weighted calls
CALLS_PER_MINUTE = 600
CALLS_PER_HOUR = 5000
CALLS_PER_DAY = 10000

# Each request is filled up to this weight, safely under the minute limit
MAX_BATCH_WEIGHT = 500


# Raised when the hourly or daily limit is reached. Downloaded cells are kept, so the download can be run again later
class RateLimitError(RuntimeError):
    pass


# Rounds coordinates to the nearest ERA5 grid point
def snap_to_grid(values):
    return ((values / ERA5_GRID).round() * ERA5_GRID).round(2)


# How many API calls a request counts as: n_locations x (n_days / 14) x (n_variables / 10)
def call_weight(n_locations, start, end):
    n_days = (pd.Timestamp(end) - pd.Timestamp(start)).days + 1
    return n_locations * (n_days / 14) * (len(HOURLY_VARIABLES) / 10)


# Where one grid cell's data for one time interval is stored
def cell_file(latitude, longitude, start, end, cache_dir=CACHE_PATH):
    interval = f"{pd.Timestamp(start):%Y%m%d}-{pd.Timestamp(end):%Y%m%d}"
    return cache_dir / interval / f"{latitude:.2f}_{longitude:.2f}.parquet"


# Fetches hourly ERA5 data for several grid cells in one request. Time is in UTC, like the rest of the project.
# Returns a list of (latitude, longitude, hourly table), in the same order as the coordinates.
# The minute limit is waited out (up to 3 times). The hourly and daily limits raise RateLimitError
def fetch_batch(session, coordinates, start, end):
    params = {
        "latitude": ",".join(f"{lat:.2f}" for lat, _ in coordinates),
        "longitude": ",".join(f"{lon:.2f}" for _, lon in coordinates),
        "start_date": pd.Timestamp(start).date().isoformat(),
        "end_date": pd.Timestamp(end).date().isoformat(),
        "hourly": ",".join(HOURLY_VARIABLES),
        "models": "era5",
        "timezone": "GMT",
        "cell_selection": "nearest",
        "elevation": ",".join(["nan"] * len(coordinates)),
    }

    for attempt in range(3):
        response = session.get(ARCHIVE_URL, params=params, timeout=(10, 300))
        if response.status_code != 429:
            break
        try:
            reason = response.json().get("reason", "")
        except ValueError:
            reason = response.text
        if "Minutely" not in reason:
            raise RateLimitError(f"{reason} Downloaded cells are kept, so run again later to continue.")
        print("  Minute limit reached, waiting 60 s ...")
        time.sleep(60)
    response.raise_for_status()

    # One location gives one object, several give a list
    results = response.json()
    if isinstance(results, dict):
        results = [results]

    batch = []
    for (latitude, longitude), result in zip(coordinates, results):
        hourly = pd.DataFrame(result["hourly"])
        hourly["time"] = pd.to_datetime(hourly["time"], utc=True)
        batch.append((latitude, longitude, hourly))
    return batch


# Reads already downloaded grid cells from the files, one table with latitude and longitude columns
def load_cells(coordinates, start, end, cache_dir=CACHE_PATH):
    frames = []
    for latitude, longitude in coordinates:
        hourly = pd.read_parquet(cell_file(latitude, longitude, start, end, cache_dir))
        hourly.insert(1, "latitude", latitude)
        hourly.insert(2, "longitude", longitude)
        frames.append(hourly)
    return pd.concat(frames, ignore_index=True)


# Downloads hourly ERA5 data for a list of (latitude, longitude) grid points and returns all of them.
# Cells that are already stored are skipped. Each new cell is saved as soon as it arrives.
# progress(done, total) is called after each request, so the app can show a progress bar later
def fetch_cells(coordinates, start, end, cache_dir=CACHE_PATH, progress=None):
    coordinates = sorted({(round(lat, 2), round(lon, 2)) for lat, lon in coordinates})
    missing = [cell for cell in coordinates if not cell_file(*cell, start, end, cache_dir).exists()]
    total = call_weight(len(missing), start, end)

    print(f"{len(coordinates)} grid cells: {len(coordinates) - len(missing)} already downloaded, "
          f"{len(missing)} to download (about {total:,.0f} API calls)")
    if total > CALLS_PER_DAY:
        raise ValueError(f"About {total:,.0f} API calls is more than the daily limit of {CALLS_PER_DAY}. "
                         "Use a shorter interval or fewer cells")

    # As many cells per request as fit under MAX_BATCH_WEIGHT
    batch_size = max(1, int(MAX_BATCH_WEIGHT // call_weight(1, start, end)))

    # If the whole job fits within one hour's limit, only the minute limit matters. Otherwise pace by the hour
    if total <= 0.9 * CALLS_PER_HOUR:
        calls_per_second = CALLS_PER_MINUTE / 60
    else:
        calls_per_second = CALLS_PER_HOUR / 3600

    session = requests.Session()
    for i in range(0, len(missing), batch_size):
        batch = missing[i:i + batch_size]
        for latitude, longitude, hourly in fetch_batch(session, batch, start, end):
            path = cell_file(latitude, longitude, start, end, cache_dir)
            path.parent.mkdir(parents=True, exist_ok=True)
            hourly.to_parquet(path)

        done = i + len(batch)
        print(f"  {done}/{len(missing)} downloaded")
        if progress:
            progress(done, len(missing))
        if done < len(missing):
            time.sleep(call_weight(len(batch), start, end) / calls_per_second)

    return load_cells(coordinates, start, end, cache_dir)