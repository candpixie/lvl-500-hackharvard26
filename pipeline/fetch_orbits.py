"""Download every free orbit dataset we use into data/raw/ (not committed).

CelesTrak throttles repeat downloads of the same group (about every 2 hours), so files newer
than 2 hours are kept and not fetched again. Run from the repo root:
    uv run python pipeline/fetch_orbits.py
Space-Track (all debris with orbits) needs each person's own free account and is not fetched here.
"""
import json
import pathlib
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = ROOT / "data/raw/celestrak"
MAX_AGE_S = 2 * 3600
GP = "https://celestrak.org/NORAD/elements/gp.php?GROUP={}&FORMAT=json"

# active = every working satellite. analyst = tracked but unidentified objects.
# The debris groups are the big breakups. The rest are labels (which constellation an object belongs to).
GROUPS = [
    "active", "analyst", "last-30-days",
    "fengyun-1c-debris", "cosmos-2251-debris", "iridium-33-debris", "cosmos-1408-debris",
    "stations", "starlink", "oneweb", "kuiper", "qianfan", "hulianwang", "planet",
    "cubesat", "education", "geo", "gnss", "weather", "science", "military",
]
FILES = {
    "satcat.csv": "https://celestrak.org/pub/satcat.csv",
    "socrates-minrange.csv": "https://celestrak.org/SOCRATES/sort-minRange.csv",
}


def fresh(path):
    return path.exists() and time.time() - path.stat().st_mtime < MAX_AGE_S and path.stat().st_size > 100


def get(url, path):
    if fresh(path):
        return "cached"
    data = urllib.request.urlopen(url, timeout=120).read()
    if path.suffix == ".json":
        json.loads(data)  # throttle notices come back as plain text, don't overwrite good data with them
    path.write_bytes(data)
    time.sleep(1)
    return "downloaded"


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    for g in GROUPS:
        p = RAW / f"{g}.json"
        try:
            status = get(GP.format(g), p)
            print(f"{g:22s} {status:10s} {len(json.loads(p.read_text())):6d} objects")
        except Exception as e:
            print(f"{g:22s} FAILED     {str(e)[:60]}")
    for name, url in FILES.items():
        p = RAW / name
        try:
            print(f"{name:22s} {get(url, p):10s} {p.stat().st_size / 1e6:.1f} MB")
        except Exception as e:
            print(f"{name:22s} FAILED     {str(e)[:60]}")


if __name__ == "__main__":
    main()
