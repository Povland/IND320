from pathlib import Path

# src/ind320/config.py -> parents[2] is the project root
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Folder with credentials and tokens. Listed in .gitignore, never pushed to GitHub
SECRETS_DIR = PROJECT_ROOT / "No_sync"


# Reads KEY=value lines from a .env file in No_sync/ and returns them as a dict.
# Handles quotes around values and the invisible BOM character Windows sometimes adds.
def load_env(filename):
    path = SECRETS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Can't find {path}")

    values = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values