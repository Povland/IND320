# Hourly weather data from Open-Meteo's Historical Weather API (ERA5 reanalysis).
#
# Strategy for the API limit:
# The free API allows 600 calls per minute, 5000 per hour and 10000 per day, and long requests
# count as more than one call (about 1 call per 14 days of data). One location for a full year
# is therefore about 26 calls, and 1000 locations per region would be about 26,000 calls,
# far more than one day's limit. Three things keep the download inside the limit:
#   1. Fewer locations: the notebook samples 100 random locations per area instead of 1000.
#   2. One request per ERA5 grid cell: ERA5 is a 0.25° grid, and all points in a cell get the
#      same data. The locations are snapped to the nearest grid point (snap_to_grid) and each
#      cell is fetched once. The caller keeps count of how many locations fell in each cell,
#      so the cells can be weighted when averaging. elevation=nan turns off Open-Meteo's
#      temperature adjustment to each point's exact height, so nothing is lost by snapping.
#   3. Pacing: fetch_weather estimates the total number of calls before it starts, refuses
#      if it is over the daily limit, and waits between requests to stay under the hourly
#      limit. If the limit is hit anyway (HTTP 429), it waits a minute and tries again.


import time

import pandas as pd
import requests

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

# Hourly variables, chosen for what fills and empties the reservoirs
HOURLY_VARIABLES = [
    "temperature_2m",               # °C, decides rain or snow, and when the snow melts
    "precipitation",                # mm, rain + snow (as water)
    "rain",                         # mm, reaches the reservoirs right away
    "snowfall",                     # cm, stays on the ground until it melts
    "snow_depth",                   # m, snow stored on the ground
    "et0_fao_evapotranspiration",   # mm, water lost to evaporation
]

# ERA5 is a 0.25° grid (~25 km). Points in the same cell get the same data
ERA5_GRID = 0.25

# Free API: 600 calls per minute, 5000 per hour and 10000 per day.
# Requests longer than 14 days or with more than 10 variables count as more than one call
CALLS_PER_HOUR = 5000
CALLS_PER_DAY = 10000


# Rounds coordinates to the nearest ERA5 grid point
def snap_to_grid(values):
    return ((values / ERA5_GRID).round() * ERA5_GRID).round(2)


# How many API calls one location counts as, for the given period.
# Counted on the safe side: never less than 1 per 14 days, even with fewer than 10 variables
def call_weight(start, end):
    n_days = (pd.Timestamp(end) - pd.Timestamp(start)).days + 1
    return max(n_days / 14, 1) * max(len(HOURLY_VARIABLES) / 10, 1)


# Fetches hourly ERA5 data for one location. Time is in UTC, like the rest of the project.
# If the rate limit is hit (HTTP 429), it waits a minute and tries again, up to 3 times
def fetch_location(session, latitude, longitude, start, end):
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": pd.Timestamp(start).date().isoformat(),
        "end_date": pd.Timestamp(end).date().isoformat(),
        "hourly": ",".join(HOURLY_VARIABLES),
        "models": "era5",
        "timezone": "GMT",
        # Turns off Open-Meteo's adjustment of temperature to the exact point's elevation,
        # so every point in a grid cell gets the cell's own value (as in ERA5 itself)
        "elevation": "nan",
    }
    for attempt in range(4):
        response = session.get(ARCHIVE_URL, params=params, timeout=(10, 120))
        if response.status_code != 429:
            break
        print("  Rate limit reached, waiting 60 s ...")
        time.sleep(60)
    response.raise_for_status()

    hourly = pd.DataFrame(response.json()["hourly"])
    hourly["time"] = pd.to_datetime(hourly["time"], utc=True)
    hourly.insert(1, "latitude", latitude)
    hourly.insert(2, "longitude", longitude)
    return hourly


# Fetches hourly ERA5 data for a list of (latitude, longitude) pairs, one request per location.
# The requests are spread out so the total stays under the hourly limit
def fetch_weather(coordinates, start, end):
    weight = call_weight(start, end)
    total = weight * len(coordinates)
    pause = weight * 3600 / CALLS_PER_HOUR

    print(f"{len(coordinates)} locations, about {total:,.0f} API calls, "
          f"about {len(coordinates) * pause / 60:.0f} minutes")
    if total > CALLS_PER_DAY:
        raise ValueError(f"About {total:,.0f} API calls is more than the daily limit of {CALLS_PER_DAY}. "
                         "Use a shorter period or fewer locations")

    session = requests.Session()
    frames = []
    for i, (latitude, longitude) in enumerate(coordinates, start=1):
        print(f"Fetching {i}/{len(coordinates)}: {latitude}, {longitude}")
        frames.append(fetch_location(session, latitude, longitude, start, end))
        if i < len(coordinates):
            time.sleep(pause)

    return pd.concat(frames, ignore_index=True)