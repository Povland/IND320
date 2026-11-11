# Areas and random locations for the weather download.
#
# The two divisions in NVE's Magasinstatistikk:
#   - EL 1-5: the electricity price areas (Budområder.zip)
#   - VASS 1-3: the watercourse areas, made by merging NVE's five regions (NVE_Region.zip):
#     East = RS + RØ (1), West = RV (2), North = RM + RN (3)
# Both are clipped to land (Norge_N5000.zip without the sea), and random locations are sampled inside each.
# The locations are snapped to the ERA5 grid, which gives one row per area and grid cell (grid_cells).
# The app computes the grid cells itself with grid_cells_for (cached), for any number of locations.

from functools import lru_cache
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from ind320.openmeteo import snap_to_grid

# data/ in the project root (src/ind320/areas.py -> two levels up)
DATA_PATH = Path(__file__).resolve().parents[2] / "data"

PRICE_AREAS_FILE = "Budområder.zip"
REGIONS_FILE = "NVE_Region.zip"
LAND_FILE = "Norge_N5000.zip"

# NVE's five regions -> the three watercourse areas (VASS area_nr)
REGION_TO_VASS = {"RS": 1, "RØ": 1, "RV": 2, "RM": 3, "RN": 3}

# Sampling. A fixed seed and a fixed order of the areas give the same locations every time
POINTS_PER_AREA = 100
SEED = 320
# The numbers of random locations per area that can be chosen in the app
POINT_OPTIONS = [100, 200, 500, 1000]


# Price areas and watercourse areas in one table: area_type, area_nr, n_vertices, geometry (EPSG:25833)
def load_areas(data_path=DATA_PATH):
    # The NVE_Region zip has no encoding file, so utf-8 is set by hand (otherwise "RØ" is garbled)
    price_areas = gpd.read_file(data_path / PRICE_AREAS_FILE)
    regions = gpd.read_file(data_path / REGIONS_FILE, encoding="utf-8")

    # Price areas: "NO 1" -> area_nr 1
    price_areas["area_type"] = "EL"
    price_areas["area_nr"] = price_areas["budomr"].str.replace("NO", "").str.strip().astype(int)

    # Watercourse areas: the regions merged into VASS 1-3.
    # Every region must get a number, otherwise dissolve silently drops it
    regions["area_nr"] = regions["REGION"].map(REGION_TO_VASS)
    missing = regions.loc[regions["area_nr"].isna(), "REGION"].tolist()
    if missing:
        raise ValueError(f"NVE regions without a VASS number: {missing}")
    vass_areas = regions.dissolve(by="area_nr").reset_index()
    vass_areas["area_type"] = "VASS"
    vass_areas["area_nr"] = vass_areas["area_nr"].astype(int)

    columns = ["area_type", "area_nr", "geometry"]
    areas = pd.concat([price_areas[columns], vass_areas[columns]], ignore_index=True)

    # Number of points (vertices) in each outline. Long coastlines with fjords and islands need many
    areas["n_vertices"] = areas.geometry.count_coordinates()
    return gpd.GeoDataFrame(areas, crs=price_areas.crs)


# Clips the areas to land. Norge_N5000 is a land cover map (forest, open land, lakes, glaciers and sea),
# so the sea ("Havflate") is removed first. Lakes and glaciers are kept: what falls there reaches the rivers too
def clip_to_land(areas, data_path=DATA_PATH):
    land = gpd.read_file(data_path / LAND_FILE, encoding="utf-8")
    land = land[land["OBJTYPE"] != "Havflate"].to_crs(areas.crs)

    clipped = gpd.clip(areas, land)
    clipped["n_vertices_clipped"] = clipped.geometry.count_coordinates()

    # gpd.clip can change the row order, and the sampling depends on the order, so it is sorted back
    return clipped.sort_values(["area_type", "area_nr"]).reset_index(drop=True)


# Random locations inside each area: points are drawn in the area's bounding box and only those inside are kept.
# Sampled in meters (EPSG:25833), so the points are evenly spread, then converted to latitude and longitude
def sample_locations(areas, points_per_area=POINTS_PER_AREA, seed=SEED):
    rng = np.random.default_rng(seed)
    samples = []

    for area_type, area_nr, polygon in zip(areas["area_type"], areas["area_nr"], areas.geometry):
        min_x, min_y, max_x, max_y = polygon.bounds
        xs, ys = [], []
        while len(xs) < points_per_area:
            x = rng.uniform(min_x, max_x, points_per_area)
            y = rng.uniform(min_y, max_y, points_per_area)
            inside = shapely.contains_xy(polygon, x, y)
            xs.extend(x[inside])
            ys.extend(y[inside])

        samples.append(gpd.GeoDataFrame(
            {"area_type": area_type, "area_nr": area_nr},
            index=range(points_per_area),
            geometry=gpd.points_from_xy(xs[:points_per_area], ys[:points_per_area]),
            crs=areas.crs,
        ))

    locations = pd.concat(samples, ignore_index=True).to_crs(4326)
    locations["lat"] = locations.geometry.y
    locations["lon"] = locations.geometry.x
    return locations


# One row per area and ERA5 grid cell, with how many of the area's locations fell in the cell.
# n_points is the weight of the cell when averaging over the area
def grid_cells(locations):
    snapped = pd.DataFrame({
        "area_type": locations["area_type"],
        "area_nr": locations["area_nr"],
        "latitude": snap_to_grid(locations["lat"]),
        "longitude": snap_to_grid(locations["lon"]),
    })
    return (
        snapped.value_counts()
        .rename("n_points")
        .reset_index()
        .sort_values(["area_type", "area_nr", "latitude", "longitude"])
        .reset_index(drop=True)
    )


# The whole chain: areas -> clipped to land -> locations -> grid cells.
# Returns all three, so the notebook can show each step
def build_grid_cells(data_path=DATA_PATH, points_per_area=POINTS_PER_AREA, seed=SEED):
    areas = clip_to_land(load_areas(data_path), data_path)
    locations = sample_locations(areas, points_per_area, seed)
    return areas, locations, grid_cells(locations)


# ---------------------------------------------------------------------------------------------
# Cached versions, used by the app and the download. Reading and clipping the shapefiles takes a few seconds,
# and the result never changes, so it is done once per process. lru_cache is part of Python, so this works
# both in the notebook and in the app. The cached tables are never handed out directly, only copies, so a
# caller that adds a column doesn't change them for everyone else
# ---------------------------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _land_areas():
    return clip_to_land(load_areas())


# The areas clipped to land (EL 1-5 and VASS 1-3), computed once
def land_areas():
    return _land_areas().copy()


@lru_cache(maxsize=None)
def _grid_cells_for(points_per_area, seed):
    return grid_cells(sample_locations(_land_areas(), points_per_area, seed))


# The grid cells of every area for a given number of random locations per area, computed once per number.
# Same shapefiles, same order, same seed: this gives exactly the same cells as build_grid_cells (checked in Oblig3)
def grid_cells_for(points_per_area=POINTS_PER_AREA, seed=SEED):
    return _grid_cells_for(points_per_area, seed).copy()