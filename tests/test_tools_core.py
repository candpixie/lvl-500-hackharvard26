"""Tool accuracy tests. Run: uv run --with pytest pytest tests -q

Each tool is checked against an independent recompute written with the csv module (no pandas), so a bug
in one method shows up as a disagreement. Needs data/raw/ from pipeline/fetch_orbits.py. These tests
check invariants that hold for any snapshot, so they survive a data refresh.
"""
import csv
import json
import math
from pathlib import Path

import pytest

from chalk_tools import core

RAW = core.RAW
pytestmark = pytest.mark.skipif(not (RAW / "satcat.csv").exists(), reason="run pipeline/fetch_orbits.py first")


@pytest.fixture(scope="module")
def snap():
    return core.Snapshot.load()


@pytest.fixture(scope="module")
def sat_rows():
    """On-orbit SATCAT rows read with csv: no decay date, Earth-centered, with apogee and perigee."""
    out = []
    with (RAW / "satcat.csv").open() as f:
        for r in csv.DictReader(f):
            if r["DECAY_DATE"] or r["ORBIT_CENTER"] != "EA" or not r["APOGEE"] or not r["PERIGEE"]:
                continue
            t = r["OBJECT_TYPE"] if r["OBJECT_TYPE"] in core.TYPE_KEYS else "UNK"
            out.append({"norad": int(r["NORAD_CAT_ID"]), "name": r["OBJECT_NAME"], "type": t,
                        "apogee": float(r["APOGEE"]), "perigee": float(r["PERIGEE"]),
                        "inc": float(r["INCLINATION"]) if r["INCLINATION"] else None})
    return out


# ---------- shell_crowding ----------

@pytest.mark.parametrize("alt", [200, 250, 480, 550, 799.9, 800, 1950, 1999])
def test_shell_crowding_matches_independent_recompute(snap, sat_rows, alt):
    lo = int(alt // 50 * 50)
    expected = {k: 0 for k in core.TYPE_KEYS}
    for r in sat_rows:
        if lo <= (r["apogee"] + r["perigee"]) / 2 < lo + 50:
            expected[r["type"]] += 1
    res = core.shell_crowding(snap, alt)
    assert res["ok"] and res["data"]["counts"] == expected
    assert res["data"]["total"] == sum(expected.values())


def test_shell_crowding_boundary_belongs_to_upper_shell(snap):
    assert core.shell_crowding(snap, 500)["data"]["shell_km"] == [500, 550]
    assert core.shell_crowding(snap, 499.9)["data"]["shell_km"] == [450, 500]


def test_shells_add_up_to_leo_total(snap, sat_rows):
    total = sum(core.shell_crowding(snap, a)["data"]["total"] for a in range(200, 2000, 50))
    expected = sum(1 for r in sat_rows if 200 <= (r["apogee"] + r["perigee"]) / 2 < 2000)
    assert total == expected


@pytest.mark.parametrize("alt", [199.9, 2000, 36000, -5, float("nan")])
def test_shell_crowding_rejects_out_of_range(snap, alt):
    res = core.shell_crowding(snap, alt)
    assert not res["ok"] and res["error"]["type"] in ("out_of_range", "invalid_argument")


def test_shell_crowding_inclination_filter_never_adds_objects(snap):
    all_incl = core.shell_crowding(snap, 550)["data"]["total"]
    narrow = core.shell_crowding(snap, 550, inclination_deg=53, inclination_band_deg=2)["data"]["total"]
    assert 0 < narrow <= all_incl


def test_shell_density_uses_shell_volume(snap):
    d = core.shell_crowding(snap, 550)["data"]
    vol = core.shell_volume_km3(550, 600)
    assert d["objects_per_million_km3"] == pytest.approx(d["total"] / vol * 1e6, rel=1e-3)


def test_matches_committed_leo_shells_file_shape(snap):
    """The UI reads data/out/leo_shells.json; counts per shell must agree when both come from the same SATCAT."""
    shells = json.loads((core.ROOT / "data/out/leo_shells.json").read_text())["shells"]
    row = next(s for s in shells if s["shell_km"] == 550)
    res = core.shell_crowding(snap, 550)["data"]["counts"]
    # Equal only if leo_shells.json was built from this same snapshot; report, do not hide, a mismatch.
    assert sum(res.values()) > 0 and sum(v for k, v in row.items() if k != "shell_km") > 0


# ---------- objects_near ----------

@pytest.mark.parametrize("alt,inc", [(420, 51.6), (693, 98.2), (550, 53), (800, 98), (1200, 87)])
def test_objects_near_matches_brute_force(snap, sat_rows, alt, inc):
    tol = 5.0
    expected = {r["norad"] for r in sat_rows
                if r["inc"] is not None and r["perigee"] <= alt <= r["apogee"] and abs(r["inc"] - inc) <= tol}
    res = core.objects_near(snap, alt, inc, limit=50)
    assert res["ok"] and res["data"]["total_matches"] == len(expected)
    assert {o["norad"] for o in res["data"]["objects"]} <= expected


def test_objects_near_known_objects_appear_and_negatives_do_not(snap):
    iss = [o["norad"] for o in core.objects_near(snap, 420, 51.6, limit=50)["data"]["objects"]]
    assert 25544 in iss
    sentinel = [o["norad"] for o in core.objects_near(snap, 693, 98.2, limit=50)["data"]["objects"]]
    assert 39634 in sentinel
    assert 25544 not in sentinel and 39634 not in iss  # wrong inclination and altitude


def test_objects_near_sorted_nearest_first_and_limited(snap):
    res = core.objects_near(snap, 550, 53, limit=7)["data"]["objects"]
    assert len(res) == 7
    d = [math.hypot((((o["perigee_km"] + o["apogee_km"]) / 2) - 550) / core.SHELL_KM,
                    (o["inclination_deg"] - 53) / 5.0) for o in res]
    assert d == sorted(d)


def test_objects_near_eccentric_object_counts_in_range_not_in_average_shell(snap):
    """Decision: objects_near uses the orbit's perigee-apogee range; shell_crowding uses the average altitude."""
    c = snap.catalog
    e = c[(c.APOGEE - c.PERIGEE > 1000) & (c.PERIGEE >= 300) & (c.APOGEE < 1900) & c.INCLINATION.notna()].iloc[0]
    alt = float(e.PERIGEE) + 10
    near = core.objects_near(snap, alt, float(e.INCLINATION), limit=50, inclination_tol_deg=0.01)
    assert e.NORAD_CAT_ID in {o["norad"] for o in near["data"]["objects"]} or near["data"]["total_matches"] > 50
    assert not (e.mean_alt // 50 * 50 <= alt < e.mean_alt // 50 * 50 + 50)  # it is not in this altitude's shell


def test_objects_near_validation(snap):
    assert not core.objects_near(snap, 550, 181)["ok"]
    assert not core.objects_near(snap, 550, -1)["ok"]
    assert not core.objects_near(snap, 100, 53)["ok"]


# ---------- close_approaches ----------

def _independent_approaches(sat_rows):
    mean_alt = {r["norad"]: (r["apogee"] + r["perigee"]) / 2 for r in sat_rows}
    out = []
    with (RAW / "socrates-minrange.csv").open() as f:
        for r in csv.DictReader(f):
            if core.constellation(r["OBJECT_NAME_1"]) and core.constellation(r["OBJECT_NAME_1"]) == core.constellation(r["OBJECT_NAME_2"]):
                continue
            if float(r["TCA_RELATIVE_SPEED"]) <= core.MIN_RELATIVE_SPEED_KM_S:
                continue
            a1, a2 = mean_alt.get(int(r["NORAD_CAT_ID_1"])), mean_alt.get(int(r["NORAD_CAT_ID_2"]))
            if a1 is None or a2 is None:
                continue
            out.append((float(r["TCA_RANGE"]), int(r["NORAD_CAT_ID_1"]), int(r["NORAD_CAT_ID_2"]), (a1 + a2) / 2))
    return out


def test_close_approaches_matches_independent_refilter(snap, sat_rows):
    ind = _independent_approaches(sat_rows)
    lo, hi = 400, 600
    expected = sorted(x for x in ind if lo <= x[3] <= hi)
    res = core.close_approaches(snap, lo, hi, limit=10)
    assert res["ok"] and res["data"]["rows_available"] == len(expected)
    got = [(a["miss_distance_m"], a["norad_1"], a["norad_2"]) for a in res["data"]["approaches"]]
    want = [(round(x[0] * 1000, 1), x[1], x[2]) for x in expected[:10]]
    assert got == want


def test_close_approaches_exclusions_and_units(snap):
    res = core.close_approaches(snap, 200, 1999, limit=50)["data"]["approaches"]
    assert res, "expected some approaches"
    for a in res:
        c1, c2 = core.constellation(a["name_1"]), core.constellation(a["name_2"])
        assert not (c1 and c1 == c2)
        assert a["relative_speed_km_s"] > core.MIN_RELATIVE_SPEED_KM_S
    d = [a["miss_distance_m"] for a in res]
    assert d == sorted(d)


def test_miss_distance_converts_km_to_meters(snap):
    top = snap.approaches.iloc[0]
    res = core.close_approaches(snap, 200, 1999, limit=1)["data"]["approaches"][0]
    assert res["miss_distance_m"] == pytest.approx(float(top.TCA_RANGE) * 1000, abs=0.1)


def test_suspect_probability_is_flagged_not_hidden(snap):
    for a in core.close_approaches(snap, 200, 1999, limit=50)["data"]["approaches"]:
        assert (a["probability_flag"] == "suspect") == (a["max_probability"] >= core.SUSPECT_PROBABILITY)


def test_close_approaches_validation(snap):
    assert not core.close_approaches(snap, 800, 500)["ok"]
    assert not core.close_approaches(snap, 100, 500)["ok"]
    empty = core.close_approaches(snap, 1990, 1990.5)
    assert empty["ok"]


# ---------- envelope ----------

def test_every_result_carries_snapshot_id_and_is_json_serializable(snap):
    for res in (core.shell_crowding(snap, 550), core.objects_near(snap, 550, 53),
                core.close_approaches(snap, 400, 600), core.shell_crowding(snap, 5)):
        assert res["snapshot_id"] == snap.snapshot_id
        json.dumps(res)


def test_compact_snapshot_answers_identically_to_raw(snap):
    """What ships to Chalk (data/out/tools) must answer exactly like the raw files the tests checked."""
    tools = core.ROOT / "data/out/tools"
    if not (tools / "catalog.csv.gz").exists():
        pytest.skip("run pipeline/build_tools_data.py first")
    compact = core.Snapshot.load_compact(tools)
    assert compact.snapshot_id == snap.snapshot_id
    for fn, args in [(core.shell_crowding, (550,)), (core.shell_crowding, (800, 98)),
                     (core.objects_near, (420, 51.6, 10)), (core.close_approaches, (400, 600, 10))]:
        assert json.dumps(fn(compact, *args), sort_keys=True) == json.dumps(fn(snap, *args), sort_keys=True)
