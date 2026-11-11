# Hourly weather data from Open-Meteo's Historical Weather API (ERA5 reanalysis).
#
# Strategy for the API limit:
# The free API allows 600 calls per minute, 5000 per hour and 10000 per day. A request counts as
# n_locations x (n_days / 14) x (n_variables / 10) calls, so one location for a year with 5 variables
# is about 13 calls. Four things keep the download fast and inside the limit:
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
#      costs no API calls at all. The cache folder is named after the API settings, and a file only
#      counts as downloaded if it has all the current variables, so changing either never mixes in old data.
#
# Errors: the minute limit is waited out, and server errors or empty answers are tried again.
# The hourly and daily limits raise RateLimitError, and anything else unusable raises OpenMeteoError,
# with what Open-Meteo answered in the message.
# If Open-Meteo can't deliver a request (e.g. its own timeout), the request is split in two and tried again,
# down to single cells, so one heavy request or one bad cell doesn't stop the whole download.

import hashlib
import time
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import requests
import uuid

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

# The settings that decide what the API returns, apart from the variables
API_SETTINGS = {
    "models": "era5",
    "timezone": "GMT",
    "cell_selection": "nearest",
    "elevation": "nan",
}

# Downloaded cells: data/weather_cells/<settings code>/<start>-<end>/<lat>_<lon>.parquet.
# The settings code is a short hash of API_SETTINGS, so files downloaded with other settings are never mixed in.
# The variables are checked in each file (a parquet file records its columns), so a file that lacks one of
# HOURLY_VARIABLES counts as not downloaded, and a file with extra variables is still used
# Each file is written under a temporary name and renamed when complete, so a stopped download never leaves a broken file
CACHE_PATH = Path(__file__).resolve().parents[2] / "data" / "weather_cells"

# Hourly variables, chosen for what fills and empties the reservoirs.
# snow_depth was tried, but is empty (None) for the era5 model, so it was removed
HOURLY_VARIABLES = [
    "temperature_2m",               # °C, decides rain or snow, and when the snow melts
    "precipitation",                # mm, rain + snow (as water)
    "rain",                         # mm, reaches the reservoirs right away
    "snowfall",                     # cm, stays on the ground until it melts
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


# Raised when Open-Meteo doesn't give usable data. The message says what it answered
class OpenMeteoError(RuntimeError):
    pass


# Raised when the hourly or daily limit is reached. Downloaded cells are kept, so the download can be run again later
class RateLimitError(OpenMeteoError):
    pass


# The reason Open-Meteo gives in an error response, or the start of the text if it isn't JSON
def _reason(response):
    try:
        return response.json().get("reason", "")
    except ValueError:
        return response.text[:200]


# Rounds coordinates to the nearest ERA5 grid point
def snap_to_grid(values):
    return ((values / ERA5_GRID).round() * ERA5_GRID).round(2)


# How many API calls a request counts as: n_locations x (n_days / 14) x (n_variables / 10)
def call_weight(n_locations, start, end):
    n_days = (pd.Timestamp(end) - pd.Timestamp(start)).days + 1
    return n_locations * (n_days / 14) * (len(HOURLY_VARIABLES) / 10)


# A short code for the API settings, used as the cache folder name. The same settings always give the same code
def settings_code():
    text = "&".join(f"{key}={value}" for key, value in sorted(API_SETTINGS.items()))
    return hashlib.sha1(text.encode()).hexdigest()[:8]


# Where one grid cell's data for one time interval is stored
def cell_file(latitude, longitude, start, end, cache_dir=CACHE_PATH):
    interval = f"{pd.Timestamp(start):%Y%m%d}-{pd.Timestamp(end):%Y%m%d}"
    return cache_dir / settings_code() / interval / f"{latitude:.2f}_{longitude:.2f}.parquet"


# Whether a cell is downloaded with every one of the current variables. The columns are read from the
# file's schema, without reading the data, so this is fast even for many cells.
# A file that can't be read (e.g. from an older version that was stopped while writing) counts as not downloaded,
# so it is downloaded again and replaced
def is_cached(latitude, longitude, start, end, cache_dir=CACHE_PATH):
    path = cell_file(latitude, longitude, start, end, cache_dir)
    if not path.exists():
        return False
    try:
        names = pq.read_schema(path).names
    except (OSError, ValueError):     # pyarrow's errors for broken or half-written files
        return False
    return set(HOURLY_VARIABLES) <= set(names)


# Fetches hourly ERA5 data for several grid cells in one request. Time is in UTC, like the rest of the project.
# Returns a list of (latitude, longitude, hourly table), in the same order as the coordinates
def fetch_batch(session, coordinates, start, end):
    params = {
        "latitude": ",".join(f"{lat:.2f}" for lat, _ in coordinates),
        "longitude": ",".join(f"{lon:.2f}" for _, lon in coordinates),
        "start_date": pd.Timestamp(start).date().isoformat(),
        "end_date": pd.Timestamp(end).date().isoformat(),
        "hourly": ",".join(HOURLY_VARIABLES),
        **API_SETTINGS,
        # elevation is one value per location when there are several
        "elevation": ",".join([API_SETTINGS["elevation"]] * len(coordinates)),
    }

    # Up to 4 attempts: the minute limit is waited out, and server errors or empty answers are tried again.
    # The hourly and daily limits stop the download (RateLimitError), since waiting would take too long
    for attempt in range(4):
        response = session.get(ARCHIVE_URL, params=params, timeout=(10, 300))

        if response.status_code == 429:
            reason = _reason(response)
            if "Minutely" not in reason:
                raise RateLimitError(f"{reason} Downloaded cells are kept, so run again later to continue.")
            print("  Minute limit reached, waiting 60 s ...")
            time.sleep(60)
            continue

        if response.status_code >= 500 or not response.content:
            print(f"  Open-Meteo answered {response.status_code} with {len(response.content)} bytes, trying again in 30 s ...")
            time.sleep(30)
            continue

        break

    response.raise_for_status()

    # One location gives one object, several give a list. Anything else is shown in the error
    try:
        results = response.json()
    except ValueError:
        raise OpenMeteoError(
            f"Open-Meteo did not answer with data (status {response.status_code}): {response.text[:200]!r}"
        ) from None
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
        # Only the time and the current variables are read, so extra columns in older files are left out
        hourly = pd.read_parquet(cell_file(latitude, longitude, start, end, cache_dir), columns=["time", *HOURLY_VARIABLES])
        hourly.insert(1, "latitude", latitude)
        hourly.insert(2, "longitude", longitude)
        frames.append(hourly)
    return pd.concat(frames, ignore_index=True)


# Downloads one batch of cells and saves each cell as a file.
# If Open-Meteo can't deliver (OpenMeteoError, e.g. its own timeout while streaming the data), the batch is split
# in two and each half is tried on its own, down to single cells. This works around requests that are too heavy,
# and isolates a single cell that won't download. The hourly and daily limits (RateLimitError) are not split
def _download_batch(session, batch, start, end, cache_dir):
    try:
        results = fetch_batch(session, batch, start, end)
    except RateLimitError:
        raise
    except OpenMeteoError as error:
        if len(batch) == 1:
            latitude, longitude = batch[0]
            raise OpenMeteoError(f"Grid cell {latitude}, {longitude} could not be downloaded: {error}") from None
        half = len(batch) // 2
        print(f"  {error}\n  Trying again as two smaller requests ({half} and {len(batch) - half} cells) ...")
        _download_batch(session, batch[:half], start, end, cache_dir)
        _download_batch(session, batch[half:], start, end, cache_dir)
        return

    # Each cell is written under a temporary name and renamed when the file is complete. The rename is a single step,
    # so the real name only ever holds a whole file. The random part keeps two sessions writing the same cell apart
    for latitude, longitude, hourly in results:
        path = cell_file(latitude, longitude, start, end, cache_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f"{path.stem}.{uuid.uuid4().hex}.tmp")
        hourly.to_parquet(temporary)
        temporary.replace(path)


# Downloads hourly ERA5 data for a list of (latitude, longitude) grid points and returns all of them.
# Cells that are already stored are skipped. Each new cell is saved as soon as it arrives.
# progress(done, total) is called after each request, so the app can show a progress bar
# load=False downloads without reading the cells back (used for many regions at once, see weather.py)
def fetch_cells(coordinates, start, end, cache_dir=CACHE_PATH, progress=None, load=True):
    coordinates = sorted({(round(lat, 2), round(lon, 2)) for lat, lon in coordinates})
    missing = [cell for cell in coordinates if not is_cached(*cell, start, end, cache_dir)]
    total = call_weight(len(missing), start, end)

    print(f"{len(coordinates)} grid cells: {len(coordinates) - len(missing)} already downloaded, "
          f"{len(missing)} to download (about {total:,.0f} API calls)")
    # A job bigger than the daily limit is started anyway: it downloads as much as the limit allows, then stops
    # with RateLimitError. The downloaded cells are kept, so the next run continues from there
    if total > CALLS_PER_DAY:
        print(f"  More than one day's limit ({CALLS_PER_DAY:,} calls): this will stop when the limit is reached, "
              "and continue from there on the next run")

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
        _download_batch(session, batch, start, end, cache_dir)

        done = i + len(batch)
        print(f"  {done}/{len(missing)} downloaded")
        if progress:
            progress(done, len(missing))
        if done < len(missing):
            time.sleep(call_weight(len(batch), start, end) / calls_per_second)

    # load=False only downloads, so a large job doesn't have to hold all the cells in memory at once
    if not load:
        return None
    return load_cells(coordinates, start, end, cache_dir)