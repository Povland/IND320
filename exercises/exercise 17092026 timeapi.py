import json
import urllib.request

req = urllib.request.Request(
    "https://timeapi.io/api/v1/time/current/utc",
    headers={"accept": "*/*"},
)
with urllib.request.urlopen(req, timeout=10) as resp:
    data = json.load(resp)

print(data["utc_time"])