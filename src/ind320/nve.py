import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = "https://biapi.nve.no/magasinstatistikk/api/Magasinstatistikk"

# API names -> the names used in the rest of the project
COLUMN_NAMES = {
    "dato_Id": "date_id",
    "omrType": "area_type",
    "omrnr": "area_nr",
    "iso_aar": "iso_aar",
    "iso_uke": "iso_week",
    "fyllingsgrad": "filling_degree",
    "kapasitet_TWh": "capacity_TWh",
    "fylling_TWh": "filling_TWh",
    "neste_Publiseringsdato": "next_publishing_date",
    "fyllingsgrad_forrige_uke": "filling_degree_last_week",
    "endring_fyllingsgrad": "filling_degree_change",
}


def fetch_json(endpoint):
    #Fetches raw JSON from an endpoint in NVE's Magasinstatistikk API.
    #Request waits up to 2 minutes and is retried up to 3 times with increasing pauses.

    retry = Retry(
        total=3,
        backoff_factor=2,                          # waits 2, 4, 8 seconds between attempts
        status_forcelist=[500, 502, 503, 504],     # retry on server errors too
        allowed_methods=["GET"],
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))

    response = session.get(
        f"{BASE_URL}/{endpoint}",
        headers={"Accept": "application/json"},
        timeout=(10, 120),                         # 10 s to connect, 120 s to read
    )
    response.raise_for_status()
    return response.json()


def fetch_reservoir_data():
    #Fetches the weekly reservoir statistics, with date_id as a sorted index.
    reservoir_data = pd.DataFrame(fetch_json("HentOffentligData")).rename(columns=COLUMN_NAMES)

    reservoir_data["date_id"] = pd.to_datetime(reservoir_data["date_id"])
    reservoir_data["next_publishing_date"] = pd.to_datetime(reservoir_data["next_publishing_date"])

    return reservoir_data.set_index("date_id").sort_index()


def fetch_areas():
    groups = fetch_json("HentOmr%C3%A5der")
    rows = [area for group in groups for area_list in group.values() for area in area_list]
    return pd.DataFrame(rows)