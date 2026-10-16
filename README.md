# IND320 project 2026
Philip A. K. Øvland

- GitHub: https://github.com/Povland/IND320
- Streamlit: https://ind320-2026.streamlit.app/


## Setup

```
uv sync     # dependencies + the ind320 package
docker run --name my_cassandra -p 9042:9042 -d cassandra:latest     # first time (later: docker start my_cassandra)
uv run streamlit run app/streamlit_app.py
```

- Python 3.11 (PySpark 3.5.1 does not support newer versions).
- Spark needs Java 17. On Windows it also needs `winutils.exe` and `hadoop.dll` (Hadoop 3.3.x) in `C:\hadoop\bin`, with `HADOOP_HOME=C:\hadoop`.

## Links

**Data sources**
- NVE Magasinstatistikk API: https://biapi.nve.no/magasinstatistikk/swagger/index.html
- NVE Magasinstatistikk (description): https://www.nve.no/energi/analyser-og-statistikk/magasinstatistikk/
- ENTSO-E API reference: https://documenter.getpostman.com/view/7009892/2s93JtP3F6
- ENTSO-E Transparency Platform: https://transparency.entsoe.eu/
- ENTSO-E security token: https://transparencyplatform.zendesk.com/hc/en-us/articles/12845911031188-How-to-get-security-token

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
| `src/ind320/` | Shared data code (one module per API), installed as a package with `uv sync` |
| `app/` | Streamlit app. `app/utils/data.py` is the app's access point to data |
| `data/reservoirs.csv` | Legacy, only used by Oblig1. The app and Oblig2 use NVE's API |
| `No_sync/` | Secret files for the notebook. **Not in git** (see below) |
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