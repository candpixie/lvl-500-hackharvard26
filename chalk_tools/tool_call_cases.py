"""Tool-calling eval rows: what a correct agent should call for each question. Written by Person A.

Each case: id, group, question, context (what the globe shows), history (earlier turns), and expected:
  calls: [{tool, args, tol}]   expected arguments with an optional per-argument tolerance (default by name, see agent_scorers)
  no_call: True when the right behavior is to answer without calling any tool
  out_of_scope: True when the question is outside what the tools cover (also no_call)
Arguments the agent adds beyond the expected ones (for example a default limit) are not penalized.
Mission phrases: ISS-like = 51.6, sun-synchronous = about 98, polar = about 90, equatorial = 0, Starlink-like = 53.
Altitude phrases: 1 mile = 1.609 km. Relative phrases ("a bit higher") = +50 km from context.
"""
from __future__ import annotations


def call(tool: str, tol: dict | None = None, **args) -> dict:
    return {"tool": tool, "args": args, "tol": tol or {}}


def case(id: str, group: str, question: str, calls: list[dict] | None = None, *, context: dict | None = None,
         history: list[dict] | None = None, no_call: bool = False, out_of_scope: bool = False) -> dict:
    return {"id": id, "group": group, "question": question, "context": context or {}, "history": history or [],
            "expected": {"calls": calls or [], "no_call": no_call or out_of_scope, "out_of_scope": out_of_scope}}


PREV_550 = [{"role": "user", "content": "How crowded is 550 km?"},
            {"role": "assistant", "content": "The 550 to 600 km shell holds 1,309 tracked objects.",
             "tool_calls": [{"name": "shell_crowding", "args": {"altitude_km": 550, "inclination_deg": None}}]}]
PREV_RECOMMEND = [{"role": "user", "content": "Where should a sun-synchronous satellite go?"},
                  {"role": "assistant", "content": "The quietest shells near 98 degrees are 1150 to 1200 km, then 1100 and 1000 km.",
                   "tool_calls": [{"name": "recommend_orbit", "args": {"inclination_deg": 98.0}}]}]

CASES = [
    # shell_crowding
    case("sc1", "shell_crowding", "How crowded is 550 km?", [call("shell_crowding", altitude_km=550)]),
    case("sc2", "shell_crowding", "How many objects are at 800 km?", [call("shell_crowding", altitude_km=800)]),
    case("sc3", "shell_crowding", "Is 480 km busy?", [call("shell_crowding", altitude_km=480)]),
    case("sc4", "shell_crowding", "How crowded is it 300 miles up?", [call("shell_crowding", altitude_km=483)]),  # unit conversion
    case("sc5", "shell_crowding", "What is in the 750 to 800 km shell?", [call("shell_crowding", tol={"altitude_km": 30}, altitude_km=775)]),
    case("sc6", "shell_crowding", "How crowded is 550 km for a polar orbit?",
         [call("shell_crowding", tol={"inclination_deg": 10}, altitude_km=550, inclination_deg=90)]),
    case("sc7", "shell_crowding", "hows crowded is 650 km", [call("shell_crowding", altitude_km=650)]),  # typo, paraphrase
    case("sc8", "shell_crowding", "How much debris is up at 850 km?", [call("shell_crowding", altitude_km=850)]),
    # objects_near
    case("on1", "objects_near", "What is near the space station's orbit?",
         [call("objects_near", tol={"altitude_km": 30}, altitude_km=420, inclination_deg=51.6)]),
    case("on2", "objects_near", "What objects share a sun-synchronous orbit at 700 km?",
         [call("objects_near", tol={"inclination_deg": 1.5}, altitude_km=700, inclination_deg=98)]),
    case("on3", "objects_near", "What is near a polar orbit at 700 km?",
         [call("objects_near", tol={"inclination_deg": 10}, altitude_km=700, inclination_deg=90)]),
    case("on4", "objects_near", "Who else is flying at 550 km and 53 degrees?", [call("objects_near", altitude_km=550, inclination_deg=53)]),
    case("on5", "objects_near", "List the 5 objects closest to a 600 km, 97.5 degree orbit.",
         [call("objects_near", altitude_km=600, inclination_deg=97.5, limit=5)]),
    case("on6", "objects_near", "whats around 500km 45 deg", [call("objects_near", altitude_km=500, inclination_deg=45)]),
    case("on7", "objects_near", "Which objects are near an equatorial orbit at 800 km?",
         [call("objects_near", tol={"inclination_deg": 5}, altitude_km=800, inclination_deg=0)]),
    # close_approaches
    case("ca1", "close_approaches", "Any near misses around 800 km this week?",
         [call("close_approaches", tol={"min_altitude_km": 50, "max_altitude_km": 50}, min_altitude_km=750, max_altitude_km=850)]),
    case("ca2", "close_approaches", "What are the closest predicted approaches between 400 and 600 km?",
         [call("close_approaches", min_altitude_km=400, max_altitude_km=600)]),
    case("ca3", "close_approaches", "Show me near misses at the space station's altitude.",
         [call("close_approaches", tol={"min_altitude_km": 30, "max_altitude_km": 40}, min_altitude_km=400, max_altitude_km=450)]),
    case("ca4", "close_approaches", "Any close approaches between 500 and 550 km?",
         [call("close_approaches", min_altitude_km=500, max_altitude_km=550)]),
    case("ca5", "close_approaches", "Are there close calls around 1000 km?",
         [call("close_approaches", tol={"min_altitude_km": 50, "max_altitude_km": 50}, min_altitude_km=950, max_altitude_km=1050)]),
    case("ca6", "close_approaches", "Give me the 3 closest near misses between 450 and 550 km.",
         [call("close_approaches", min_altitude_km=450, max_altitude_km=550, limit=3)]),
    # recommend_orbit (mission_fit: the inclination must suit the mission)
    case("ro1", "recommend_orbit", "Where should I put a polar climate satellite?",
         [call("recommend_orbit", tol={"inclination_deg": 8}, inclination_deg=92)]),
    case("ro2", "recommend_orbit", "Where should I put a sun-synchronous imaging satellite?",
         [call("recommend_orbit", tol={"inclination_deg": 1.5}, inclination_deg=98)]),
    case("ro3", "recommend_orbit", "What is the best orbit for an ISS-like cubesat?", [call("recommend_orbit", inclination_deg=51.6)]),
    case("ro4", "recommend_orbit", "Quietest altitude for an equatorial satellite?",
         [call("recommend_orbit", tol={"inclination_deg": 5}, inclination_deg=0)]),
    case("ro5", "recommend_orbit", "Where could I place a satellite at 53 degrees between 500 and 700 km?",
         [call("recommend_orbit", inclination_deg=53, min_altitude_km=500, max_altitude_km=700)]),
    case("ro6", "recommend_orbit", "Where should a 97.5 degree Earth-observation satellite go?",
         [call("recommend_orbit", tol={"inclination_deg": 1.5}, inclination_deg=97.5)]),
    case("ro7", "recommend_orbit", "I want a Starlink-like orbit. Where is it quiet?", [call("recommend_orbit", inclination_deg=53)]),
    case("ro8", "recommend_orbit", "Where should a 70 degree inclination satellite go?", [call("recommend_orbit", inclination_deg=70)]),
    # no tool call needed
    case("nc1", "no_call", "What is SGP4?", no_call=True),
    case("nc2", "no_call", "Thanks!", no_call=True),
    case("nc3", "no_call", "What does shell mean here?", no_call=True),
    # out of scope: no call, say so
    case("os1", "out_of_scope", "How crowded is geostationary orbit at 35,786 km?", out_of_scope=True),
    case("os2", "out_of_scope", "Can you track the Moon for me?", out_of_scope=True),
    # multi-step
    case("ms1", "multi_step", "Compare how crowded 550 km and 800 km are.",
         [call("shell_crowding", altitude_km=550), call("shell_crowding", altitude_km=800)]),
    case("ms2", "multi_step", "How crowded is 550 km, and are there any near misses there?",
         [call("shell_crowding", altitude_km=550),
          call("close_approaches", tol={"min_altitude_km": 50, "max_altitude_km": 50}, min_altitude_km=500, max_altitude_km=600)]),
    # multi-turn follow-ups (relative phrases resolve against context)
    case("mt1", "multi_turn", "What about a bit higher?", [call("shell_crowding", tol={"altitude_km": 10}, altitude_km=600)],
         context={"altitude_km": 550, "inclination_deg": None}, history=PREV_550),
    case("mt2", "multi_turn", "What is near here?", [call("objects_near", tol={"altitude_km": 10, "inclination_deg": 1}, altitude_km=420, inclination_deg=51.6)],
         context={"altitude_km": 420, "inclination_deg": 51.6}),
    case("mt3", "multi_turn", "Why that one?", no_call=True, history=PREV_RECOMMEND),  # answer from stored evidence
]
