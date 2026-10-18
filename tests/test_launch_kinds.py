"""Checks on web/public/launch_kinds.json, the data behind the "What are you launching?" picker."""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DATA = json.loads((ROOT / "web/public/launch_kinds.json").read_text())
GRID = json.loads((ROOT / "data/out/crowding_grid.json").read_text())["rows"]
BAND = DATA["band_grid"]


def test_grid_shape_matches_its_axes():
    assert len(BAND["total"]) == len(BAND["debris"]) == len(BAND["shell_total"]) == len(BAND["alt_lo"])
    assert all(len(row) == len(BAND["inc_lo"]) for row in BAND["total"] + BAND["debris"])
    assert BAND["alt_step_km"] == 50 and BAND["inc_step_deg"] == 10
    assert BAND["alt_lo"][0] == 300 and BAND["alt_lo"][-1] + 50 == 2000 and BAND["inc_lo"] == list(range(0, 180, 10))


def test_grid_matches_the_teams_crowding_table():
    """Each cell is the crowding_grid.json cell rounded; each shell total is the unrounded sum, rounded once."""
    index = {(r["alt_lo"], r["inc_lo"]): r for r in GRID}
    for a, alt in enumerate(BAND["alt_lo"]):
        assert BAND["shell_total"][a] == round(sum(index[alt, i]["total"] for i in BAND["inc_lo"]))
        for b, inc in enumerate(BAND["inc_lo"]):
            assert BAND["total"][a][b] == round(index[alt, inc]["total"])
            assert BAND["debris"][a][b] == round(index[alt, inc]["DEB"])


def test_a_band_never_holds_more_than_its_shell_and_debris_never_more_than_the_band():
    for a in range(len(BAND["alt_lo"])):
        assert all(0 <= BAND["debris"][a][b] <= BAND["total"][a][b] + 1 for b in range(len(BAND["inc_lo"])))
        assert max(BAND["total"][a]) <= BAND["shell_total"][a] + 1


def test_every_kinds_preset_orbit_fits_the_sliders():
    """The picker moves the altitude slider (200 to 1,950 km) and the inclination slider (0 to 180)."""
    for row in DATA["kinds"]:
        alt = round(row["altitude_km"]["median"] / 5) * 5
        assert 200 <= alt <= 1950, row["kind"]
        assert 0 <= round(row["inclination_deg_median"]) <= 180, row["kind"]


def test_kinds_carry_honest_caveats_and_no_globe_highlight_field():
    for row in DATA["kinds"]:
        assert row["caveats"] and any("prediction" in c.lower() or "predict" in c.lower() for c in row["caveats"])
        assert "map_groups" not in row  # the "See" dropdown was removed
    station = next(r for r in DATA["kinds"] if r["kind"] == "station")
    assert station["objects"] == 1 and any("ISS alone" in c for c in station["caveats"])


def test_the_example_the_pr_quotes_is_true():
    """Weather satellites' neighbors: about 2,070 of the 10,374 tracked objects in 450 to 500 km are in the 90 to 100 degree band."""
    a, b = BAND["alt_lo"].index(450), BAND["inc_lo"].index(90)
    assert (BAND["total"][a][b], BAND["shell_total"][a], BAND["debris"][a][b]) == (2070, 10374, 37)


def test_custom_default_matches_the_apps_own_defaults():
    """Picking "Custom" resets to DEFAULT_ORBIT in launchKinds.ts. It must equal what the page loads with."""
    import re
    app = (ROOT / "web/src/App.tsx").read_text()
    kinds_ts = (ROOT / "web/src/launchKinds.ts").read_text()
    start = int(re.search(r"const START_ALTITUDE = (\d+)", app).group(1))
    inc = int(re.search(r"const DEFAULT_INCLINATION = (\d+)", app).group(1))
    default = re.search(r"DEFAULT_ORBIT: OrbitState = \{ altitude: (\d+), inclination: (\d+), chosen: false \}", kinds_ts)
    assert default, "DEFAULT_ORBIT line not found in launchKinds.ts"
    assert (int(default.group(1)), int(default.group(2))) == (start, inc)
    assert "useState(false)" in re.search(r"const \[altitudeChosen, setAltitudeChosen\] = [^\n]+", app).group(0)  # chosen: false is the start
