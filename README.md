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

**The notebook** (`notebooks/Oblig2.ipynb`) also needs Cassandra and Spark:
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
| `notebooks/screenshot_entsoe_unexpected_error.png` | Screenshot of an ENTSO-E error, shown in the Oblig2 log |
| `src/ind320/` | Shared data code (one module per API), installed as a package with `uv sync` |
| `app/streamlit_app.py` | Entry point of the app: the page list, the connection test on load and the version in the sidebar |
| `app/pages/` | One file per page: Home, Reservoir Data, Reservoir Plot, Cross-border flow and About |
| `app/utils/data.py` | The app's access point to data: NVE's API and MongoDB, with caching |
| `app/utils/controls.py` | Shared controls for the two reservoir pages (area type, areas, period) |
| `app/utils/crossborder.py` | Choosers, titles and figures for the Cross-border flow page |
| `app/utils/about.py` | All text about the data and the project, shared by the About page and the info boxes, plus the app version |
| `data/reservoirs.csv` | Legacy, only used by Oblig1. The app and Oblig2 use NVE's API |
| `No_sync/` | Secret files for the notebook. **Not in git** (see below) |
| `.streamlit/secrets.toml` | Secrets for the Streamlit app. **Not in git** (see below) |
| `notebooks/Oblig3.ipynb` | Part 3: shapefiles from NVE Atlas, random locations per area and weather data from Open-Meteo |
| `src/ind320/openmeteo.py` | Open-Meteo download. Explains how the free API limit is handled (fewer locations, one request per ERA5 grid cell, pacing) |
| `data/Budområder.zip`, `data/NVE_Region.zip`, `data/Norge_N5000.zip` | Shapefiles from NVE Atlas: price areas, NVE regions (merged into the VASS areas) and land of Norway. See `data/data_info` |
| `data/weather_<region>_<year>.parquet` | Local backup of the weather data, made by Oblig3. **Not in git** |

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