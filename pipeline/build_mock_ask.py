"""Build docs/mock_ask.json: canned /api/ask responses made from the REAL tool outputs (local core.py).

The numbers in every mock answer come from the snapshot in data/out/tools, so the UI team builds against true
shapes and values. Run:  uv run python pipeline/build_mock_ask.py
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from chalk_tools import core  # noqa: E402


def ev(alt, inc):
    return {"type": "focusOrbit", "altitude_km": alt, "inclination_deg": inc}


def resp(snap, text, spoken, tools, events, caveats, status="ok"):
    return {"status": status, "source": "mock", "speak_text": spoken, "display_text": spoken, "ui_events": events,
            "evidence": [{"tool": n, "args": a, "summary": s} for n, a, s in tools],
            "caveats": caveats, "trace_id": "mock-trace", "snapshot_id": snap.snapshot_id}


def main():
    snap = core.Snapshot.load_compact(ROOT / "data/out/tools")
    out = {}

    out["geo"] = {"match": ["geostationary", "geo", "36000", "moon"], "response": resp(
        snap, "", "This view covers low Earth orbit only, 200 to 2,000 kilometers, so I can't answer for that altitude.",
        [], [], ["Out of scope: tools reject altitudes outside 200 to 2,000 km."], status="out_of_scope")}

    r = core.shell_crowding(snap, 550)
    d = r["data"]
    out["crowding_550"] = {"match": ["how crowded", "550"], "response": resp(
        snap, "", f"The {d['shell_km'][0]} to {d['shell_km'][1]} km shell holds {d['total']:,} tracked objects, "
        f"{d['counts']['PAY']:,} payloads, {d['counts']['DEB']} debris pieces and "
        f"{d['counts']['R/B']} rocket bodies.",
        [("shell_crowding", {"altitude_km": 550, "inclination_deg": None},
          f"{d['total']} objects in {d['shell_km'][0]}-{d['shell_km'][1]} km")],
        [ev(550, 53.0)], r["caveats"])}

    r = core.recommend_orbit(snap, 98.0, 400, 1200, top_n=3)
    c = r["data"]["candidates"]
    out["polar_climate"] = {"match": ["polar", "climate", "sun-synchronous", "98"], "response": resp(
        snap, "", f"For a polar orbit near 98 degrees, the quietest shells I can see are {c[0]['shell_km'][0]} to "
        f"{c[0]['shell_km'][1]} km, then {c[1]['shell_km'][0]} and {c[2]['shell_km'][0]} km. Quiet here means few tracked "
        f"objects, and {round(c[0]['debris_share'] * 100)} percent of the objects in the top pick are debris, so debris that "
        f"stays up a long time is part of that picture.",
        [("recommend_orbit", {"inclination_deg": 98.0, "min_altitude_km": 400, "max_altitude_km": 1200, "top_n": 3},
          "quietest shells " + ", ".join(str(x["shell_km"][0]) for x in c))],
        [ev(c[0]["shell_km"][0] + 25, 98.0)], r["caveats"])}

    r = core.close_approaches(snap, 450, 550, limit=3)
    a = r["data"]["approaches"][0]
    out["near_misses_500"] = {"match": ["near miss", "close approach", "500"], "response": resp(
        snap, "", f"SOCRATES predicts {r['data']['rows_available']:,} close approaches around 450 to 550 km this week. "
        f"The closest is {a['name_1'].split(' [')[0]} and {a['name_2'].split(' [')[0]} at {a['miss_distance_m']:g} meters"
        f"{', though SOCRATES shows a probability near 1.0 that we cannot verify' if a['probability_flag'] else ''}.",
        [("close_approaches", {"min_altitude_km": 450, "max_altitude_km": 550, "limit": 3},
          f"closest {a['miss_distance_m']:g} m, {a['name_1']} vs {a['name_2']}")],
        [ev(round(a["pair_altitude_km"]), 53.0), {"type": "showApproach", "norad_1": a["norad_1"], "norad_2": a["norad_2"]}],
        r["caveats"])}

    r = core.objects_near(snap, 420, 51.6, limit=3)
    o = r["data"]["objects"]
    out["near_iss"] = {"match": [" iss", "space station", "51.6"], "response": resp(
        snap, "", f"{r['data']['total_matches']} tracked objects share the space station's altitude and orbital plane. "
        f"The nearest match is {o[0]['name']}, then {o[1]['name']}.",
        [("objects_near", {"altitude_km": 420, "inclination_deg": 51.6, "limit": 3},
          f"{r['data']['total_matches']} matches; nearest {o[0]['name']}")],
        [ev(420, 51.6), {"type": "selectObject", "norad": o[0]["norad"]}], r["caveats"])}

    out["higher"] = {"match": ["higher", "a bit up"], "response": resp(
        snap, "", "Moving up one shell, 50 kilometers.", [], [{"type": "focusOrbit", "altitude_km": "+50", "inclination_deg": None}],
        ["Mock: the real agent sends an absolute altitude, never '+50'. The UI should treat relative values as +50 of current."])}

    out["_default"] = {"match": [], "response": resp(
        snap, "", "Mock server: I only know a few canned questions. Try: how crowded is 550 km, a polar climate satellite, "
        "near misses around 500 km, what is near the ISS, or a bit higher.", [], [], ["Mock response."], status="ok")}

    (ROOT / "docs/mock_ask.json").write_text(json.dumps(out, indent=1))
    print("docs/mock_ask.json:", [k for k in out if not k.startswith("_")])


if __name__ == "__main__":
    main()
