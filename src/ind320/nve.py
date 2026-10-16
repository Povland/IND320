import pandas as pd
import requests

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
    """Fetches raw JSON from an endpoint in NVE's Magasinstatistikk API."""
    response = requests.get(
        f"{BASE_URL}/{endpoint}",
        headers={"Accept": "application/json"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def fetch_reservoir_data():
    """Fetches the weekly reservoir statistics, with date_id as a sorted index."""
    reservoir_data = pd.DataFrame(fetch_json("HentOffentligData")).rename(columns=COLUMN_NAMES)

    reservoir_data["date_id"] = pd.to_datetime(reservoir_data["date_id"])
    reservoir_data["next_publishing_date"] = pd.to_datetime(reservoir_data["next_publishing_date"])

    return reservoir_data.set_index("date_id").sort_index()


def fetch_areas():
    """Fetches the areas (land, elspot, vassdrag) as one table."""
    return pd.DataFrame(fetch_json("HentOmr%C3%A5der"))