import subprocess
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

from utils.major_version import MAJOR_VERSION

GITHUB_REPO = "Povland/IND320"
GITHUB_API = f"https://api.github.com/repos/{GITHUB_REPO}"

# The file with the major version. Every commit that changes it counts as the start of a new major version,
# so the file should only ever hold the one line MAJOR_VERSION = n
MAJOR_FILE = "app/utils/major_version.py"


# The branch the app is running from, read from the local git repo. Falls back to main if git isn't available
def _local_branch():
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=Path(__file__).resolve().parent,
            capture_output=True, text=True, check=True, timeout=5,
        )
        branch = result.stdout.strip()
        return branch if branch and branch != "HEAD" else "main"
    except Exception:
        return "main"


# One request to GitHub's API. Raises an error if it fails (no internet, branch not pushed, rate limit...)
def _github(path, **params):
    response = requests.get(
        f"{GITHUB_API}/{path}",
        params=params,
        headers={"Accept": "application/vnd.github+json"},
        timeout=5,
    )
    response.raise_for_status()
    return response.json()


# The minor version and the newest commit, based on what is pushed to GitHub:
# 1. the newest commit on the branch
# 2. the last commit that changed MAJOR_FILE, i.e. where the current major version started
# 3. the number of commits between the two = the minor version
# Cached for 10 minutes, since GitHub allows 60 requests per hour without logging in (this uses 3)
@st.cache_data(ttl=600, show_spinner=False)
def _fetch_from_github(branch):
    newest = _github(f"commits/{branch}")
    major_changes = _github("commits", sha=branch, path=MAJOR_FILE, per_page=1)

    if major_changes:
        minor = _github(f"compare/{major_changes[0]['sha']}...{newest['sha']}")["ahead_by"]
    else:
        minor = 0   # the file isn't pushed yet

    return {
        "minor": minor,
        "branch": branch,
        "sha": newest["sha"][:7],
        "date": newest["commit"]["committer"]["date"],
        "url": newest["html_url"],
    }


# The app version as major.minor, e.g. 3.14. The major number comes from the code, so it is known even without internet
def get_version():
    try:
        info = _fetch_from_github(_local_branch())
        return {**info, "version": f"{MAJOR_VERSION}.{info['minor']}"}
    except Exception as error:
        return {"version": f"{MAJOR_VERSION}.?", "error": str(error)}


# One line with the version, the time of the last update and a link to the commit on GitHub. Used on the About page
def show_version():
    info = get_version()
    if "error" in info:
        st.caption(f"Version {info['version']} (could not reach GitHub: {info['error']})")
        return
    updated = pd.Timestamp(info["date"]).tz_convert("Europe/Oslo")
    st.markdown(
        f"**Version {info['version']}** · last update {updated:%d.%m.%Y %H:%M} · "
        f"[`{info['sha']}`]({info['url']}) on `{info['branch']}`"
    )