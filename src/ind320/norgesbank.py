# Exchange rates from Norges Bank's open data API (SDMX), no token needed.
#   - fetch_rates: daily rates (NOK per 1 unit of each currency) for a period
#   - weekly_rates: the same, averaged per week ending on Sunday, so it lines up with NVE's weeks
# Norges Bank publishes one rate per business day at about 16:00 Norwegian time. The dates are Norwegian
# business days without a time of day, so there is no time zone to convert (see the timezone part of Oblig4)

from io import StringIO

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = "https://data.norges-bank.no/api/data/EXR"

# The currencies used in the project. Norges Bank quotes about 40
CURRENCIES = ["EUR", "USD"]

# The columns needed from Norges Bank's CSV. The CSV has many more (frequency, tenor, labels, ...)
REQUIRED_COLUMNS = {"BASE_CUR", "TIME_PERIOD", "OBS_VALUE"}


# Raised when Norges Bank doesn't give usable data. The message says what was wrong
class NorgesBankError(RuntimeError):
    pass


# A session that retries up to 3 times with increasing pauses, as for NVE (nve.py)
def _session():
    retry = Retry(
        total=3,
        backoff_factor=2,                          # waits 2, 4, 8 seconds between attempts
        status_forcelist=[500, 502, 503, 504],     # retry on server errors too
        allowed_methods=["GET"],
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


# Daily exchange rates from Norges Bank: one row per business day, one column per currency (NOK per 1 unit).
# start and end are dates (strings or timestamps). The key "B.EUR+USD.NOK.SP" means:
# B = business days, EUR+USD = the currencies, NOK = quoted in kroner, SP = spot rate
def fetch_rates(start, end, currencies=CURRENCIES):
    key = f"B.{'+'.join(currencies)}.NOK.SP"
    params = {
        "format": "csv",
        "startPeriod": f"{pd.Timestamp(start):%Y-%m-%d}",
        "endPeriod": f"{pd.Timestamp(end):%Y-%m-%d}",
        "locale": "en",                            # English labels and decimal point (not comma)
    }

    response = _session().get(f"{BASE_URL}/{key}", params=params, timeout=(10, 60))
    # 404 is Norges Bank's answer when there is no data in the period (e.g. only a weekend)
    if response.status_code == 404:
        return pd.DataFrame(columns=currencies, dtype=float)
    response.raise_for_status()

    # sep=None lets pandas find the separator itself (Norges Bank's CSV has used ";")
    raw = pd.read_csv(StringIO(response.text), sep=None, engine="python")
    missing = REQUIRED_COLUMNS - set(raw.columns)
    if missing:
        raise NorgesBankError(f"Unexpected answer from Norges Bank, missing columns: {sorted(missing)}. "
                              f"Columns received: {list(raw.columns)}")

    raw["TIME_PERIOD"] = pd.to_datetime(raw["TIME_PERIOD"])
    raw["OBS_VALUE"] = pd.to_numeric(raw["OBS_VALUE"], errors="coerce")

    # Some currencies are quoted per 100 units (UNIT_MULT = 2). EUR and USD are per 1, but this keeps it right
    if "UNIT_MULT" in raw.columns:
        raw["OBS_VALUE"] = raw["OBS_VALUE"] / 10 ** pd.to_numeric(raw["UNIT_MULT"], errors="coerce").fillna(0)

    rates = raw.pivot_table(index="TIME_PERIOD", columns="BASE_CUR", values="OBS_VALUE")
    rates.index.name = "date"
    rates.columns.name = None
    return rates.reindex(columns=currencies).sort_index()


# The daily rates averaged per week. Weeks end on Sunday ("W-SUN"), like NVE's date_id (every NVE date
# is a Sunday), so the weekly rates can be joined directly with the reservoir data
def weekly_rates(start, end, currencies=CURRENCIES):
    return fetch_rates(start, end, currencies).resample("W-SUN").mean()