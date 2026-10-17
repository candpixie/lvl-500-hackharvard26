"""Fraction of time each satellite spends in Earth's shadow over one year, from real orbits.

Orbits: CelesTrak GP data (TLE), propagated with SGP4 via skyfield.
Shadow: skyfield is_sunlit() against the JPL DE421 ephemeris.
A year-long SGP4 propagation drifts along-track, but the orbit plane's slow rotation
(what sets the shadow fraction) is modeled, so the yearly fraction is meaningful.
Output: data/out/shadow.json
"""
import json
import pathlib
import urllib.request

import numpy as np
from skyfield.api import EarthSatellite, load

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data/out/shadow.json"

# NORAD catalog numbers. Starlink and Starcloud-1 are the scenario satellites, the ISS is
# the known-answer check (about a third of each orbit in shadow on average), and
# Sentinel-1A is a real dawn-dusk sun-synchronous orbit (near zero shadow most of the year).
SATELLITES = {
    "starcloud-1": 66303,
    "starlink-3240": 49728,
    "sentinel-1a-dawn-dusk": 39634,
    "iss": 25544,
}
STEP_MIN = 2
DAYS = 365


def fetch_tle(catnr):
    url = f"https://celestrak.org/NORAD/elements/gp.php?CATNR={catnr}&FORMAT=tle"
    lines = urllib.request.urlopen(url, timeout=30).read().decode().strip().splitlines()
    return [l.strip() for l in lines[:3]]


def main():
    ts = load.timescale()
    eph = load("de421.bsp")
    results = {}
    for key, catnr in SATELLITES.items():
        name, l1, l2 = fetch_tle(catnr)
        sat = EarthSatellite(l1, l2, name, ts)
        t0 = sat.epoch.tt
        minutes = np.arange(0, DAYS * 24 * 60, STEP_MIN)
        t = ts.tt_jd(t0 + minutes / 1440.0)
        sunlit = sat.at(t).is_sunlit(eph)
        daily = sunlit.reshape(DAYS, -1).mean(axis=1)
        alt_km = float(np.mean(sat.at(t[:720]).distance().km) - 6371.0)
        results[key] = {
            "name": name,
            "norad": catnr,
            "tle_epoch": sat.epoch.utc_iso(),
            "mean_altitude_km": round(alt_km, 1),
            "inclination_deg": round(float(np.degrees(sat.model.inclo)), 2),
            "shadow_fraction_year": round(1 - float(sunlit.mean()), 4),
            "shadow_fraction_daily_min": round(1 - float(daily.max()), 4),
            "shadow_fraction_daily_max": round(1 - float(daily.min()), 4),
            "days_with_no_shadow": int((daily > 0.999).sum()),
            "shadow_fraction_by_day": [round(1 - float(d), 4) for d in daily],
        }
        r = results[key]
        print(f"{key:24s} alt {r['mean_altitude_km']:6.1f} km  shadow {r['shadow_fraction_year']:.3f} "
              f"(daily {r['shadow_fraction_daily_min']:.3f} to {r['shadow_fraction_daily_max']:.3f}), "
              f"no-shadow days {r['days_with_no_shadow']}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"source": "CelesTrak GP + skyfield SGP4 + DE421", "step_min": STEP_MIN, "days": DAYS, "satellites": results}, indent=1))


if __name__ == "__main__":
    main()
