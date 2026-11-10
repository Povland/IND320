# IND320 project 2026
Philip A. K. Øvland

- GitHub: https://github.com/Povland/IND320
- Streamlit: https://ind320-2026.streamlit.app/


## Setup

**The app** only needs the dependencies and `.streamlit/secrets.toml` (see *Secret files* below):
```
uv sync     # dependencies + the ind320 package
uv run streamlit run app/streamlit_app.py
```

**The Oblig3 notebook** (`notebooks/Oblig3.ipynb`) only needs the dependencies and `No_sync/atlas-credentials.env`.

**The Oblig2 notebook** (`notebooks/Oblig2.ipynb`) also needs Cassandra and Spark:
```
docker run --name my_cassandra -p 9042:9042 -d cassandra:latest     # first time (later: docker start my_cassandra)
```
- Python 3.11 (PySpark 3.5.1 does not support newer versions).
- Spark needs Java 17. On Windows it also needs `winutils.exe` and `hadoop.dll` (Hadoop 3.3.x) in `C:\hadoop\bin`, with `HADOOP_HOME=C:\hadoop`.

## Version

The app version is set by hand in `pyproject.toml` (`version = "3.00"`), with one major number per assignment.
It is shown at the bottom of the sidebar and on the About page.

## Links

**Data sources**
- NVE Magasinstatistikk API: https://biapi.nve.no/magasinstatistikk/swagger/index.html
- NVE Magasinstatistikk (description): https://www.nve.no/energi/analyser-og-statistikk/magasinstatistikk/
- ENTSO-E API reference: https://documenter.getpostman.com/view/7009892/2s93JtP3F6
- ENTSO-E Transparency Platform: https://transparency.entsoe.eu/
- ENTSO-E security token: https://transparencyplatform.zendesk.com/hc/en-us/articles/12845911031188-How-to-get-security-token
- Open-Meteo Historical Weather API (ERA5): https://open-meteo.com/en/docs/historical-weather-api
- NVE Atlas (shapefiles): https://atlas.nve.no

**Services**
- MongoDB Atlas: https://cloud.mongodb.com/
- Streamlit Community Cloud: https://share.streamlit.io/
- Streamlit secrets on Community Cloud: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management

**Tools**
- uv: https://docs.astral.sh/uv/
- Docker Desktop: https://www.docker.com/products/docker-desktop/
- Cassandra Docker image: https://hub.docker.com/_/cassandra
- Spark Cassandra Connector: https://github.com/datastax/spark-cassandra-connector
- winutils for Windows (Hadoop): https://github.com/cdarlint/winutils
- entsoe-py (ENTSO-E client): https://github.com/EnergieID/entsoe-py

## Structure

| Path | Contents |
|---|---|
| `notebooks/Oblig1.ipynb` | Part 1: reservoir data from CSV |
| `notebooks/Oblig2.ipynb` | Part 2: NVE and ENTSO-E APIs, Cassandra, Spark and MongoDB |
| `notebooks/Oblig2.html`, `notebooks/Oblig2.pdf` | Oblig2 exported as HTML and PDF |
| `notebooks/Oblig3.ipynb` | Part 3: areas and random locations, weather from Open-Meteo, SPC, LOF, STL and spectrogram |
| `notebooks/Oblig3.html` | Oblig3 exported as HTML |
| `notebooks/screenshot_entsoe_unexpected_error.png` | Screenshot of an ENTSO-E error, shown in the Oblig2 log |
| `src/ind320/` | All the logic, used by both the notebooks and the app. Installed as a package with `uv sync` |
| `src/ind320/nve.py`, `entsoe.py` | NVE's and ENTSO-E's APIs |
| `src/ind320/areas.py` | The shapefiles: price areas and VASS areas, clipped to land, random locations, ERA5 grid cells |
| `src/ind320/openmeteo.py` | Open-Meteo download. Explains how the free API limit is handled (one request per grid cell, several cells per request, pacing, a cache per cell) |
| `src/ind320/weather.py` | Weather per area: the download function (region + interval), the weighted average, and the MongoDB store |
| `src/ind320/anomalies.py` | Outliers with SPC (DCT high-pass filter) and anomalies with LOF |
| `src/ind320/seasonal.py` | STL decomposition and spectrogram of the filling degree |
| `src/ind320/config.py` | Reads the secret files in `No_sync/` |
| `app/streamlit_app.py` | Entry point of the app: the page list, the connection test on load, the global selection in the sidebar and the version |
| `app/pages/` | One file per page: Home, Reservoir Data, Reservoir Plot, Seasonality & Spectrum, Weather Outliers, Cross-border flow and About |
| `app/utils/data.py` | The app's access point to data: NVE's API, MongoDB and the weather downloads, with caching |
| `app/utils/controls.py` | The global selection in the sidebar (area type, areas, period) and the local selectors on the pages |
| `app/utils/crossborder.py` | Choosers, titles and figures for the Cross-border flow page |
| `app/utils/about.py` | All text about the data and the project, shared by the About page and the info boxes, plus the app version |
| `data/data_info` | Where each file in `data/` comes from and what it is used for |
| `data/reservoirs.csv` | Legacy, only used by Oblig1. The app and Oblig2 use NVE's API |
| `data/Budområder.zip`, `data/NVE_Region.zip`, `data/Norge_N5000.zip` | Shapefiles from NVE Atlas: price areas, NVE regions (merged into the VASS areas) and land cover of Norway |
| `data/grid_cells.csv` | The ERA5 grid cells of each area, with how many random locations fell in each. Made once by Oblig3, read by the app |
| `data/weather_cells/` | Downloaded weather per grid cell and year, a local cache so a stopped download can continue. **Not in git** |
| `No_sync/` | Secret files for the notebooks. **Not in git** (see below) |
| `.streamlit/secrets.toml` | Secrets for the Streamlit app. **Not in git** (see below) |

## Secret files

These files are listed in `.gitignore` and never pushed to GitHub. Create them yourself to run the project:

**`No_sync/atlas-credentials.env`** (MongoDB, used by the notebook)
```
MONGODB_USERNAME=...
MONGODB_PASSWORD=...
MONGODB_URI=mongodb+srv://...
```

**`No_sync/entsoe.env`** (ENTSO-E token, used by the notebook)
```
ENTSOE_TOKEN=...
```

**`.streamlit/secrets.toml`** (MongoDB, used by the Streamlit app)
```toml
[mongo]
uri = "mongodb+srv://..."
database = "ind320"
```
On Streamlit Community Cloud, the same content is pasted into the app's Settings → Secrets.
The app also writes to MongoDB (the weather downloads), so the user in the URI needs read and write access to the database.