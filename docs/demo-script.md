# Demo script (~90 seconds, video)

Servers: `uv run uvicorn api.main:app --reload --port 8000` and `cd web && npm run dev`.
Open **http://127.0.0.1:5173**. Record the globe; left panel is the story, right panel is Grok.

Say **“tracked objects only, lower bound”** once. Never say “collision probability” unless you are quoting SOCRATES.

## Shot 1 — The hook (15s)

Leave the globe spinning at ~480 km (Starlink shell, ~10,000 objects).

> Low Earth orbit holds about 29,000 tracked objects. In January, SpaceX filed for up to a million orbital data-center satellites. If we put something up there, where does it do the least harm?

## Shot 2 — 1 million at 900 km (20s)

Left panel: click **1M at 900 km**. Wait for the yellow orbit and the score.

> A million four-meter satellites at 900 km. Score about 42. Expected collisions per year, first-order model, is huge — and a dead satellite stays up about 500 years. Self-crowding dominates. They would have to maneuver.

## Shot 3 — Safest shell (15s)

Click **Safest 500 km**. The list should already show 500–550 on top.

> Same constellation at 500 to 550 km. Score about 80. Wreckage falls out in about a decade. Low shells win because air drag cleans them.

## Shot 4 — Why 800 km is bad (15s)

Click **Debris 800 km**. Amber debris-only view.

> Debris piles up at 800 to 850 km — leftover from the 2007 Chinese ASAT test and the 2009 Iridium-Cosmos collision. Drag is too weak. Junk lives where nature can’t clean it up.

## Shot 5 — Grok Imagine (15s)

At 480 km click **Visualize this shell**, or click a bright dot. Wait for the labeled illustration. Click the image, then **scroll out** (or **Enter neighborhood**). Drag to look around.

> Hubble sits in this shell, next to WorldView-1. The still is an illustration. Scroll out and you are in the catalog neighborhood — pale satellites, amber debris, tracked objects only.

## Shot 6 — This week’s near miss (15s)

Click the **NuSat-47 vs Fengyun 1C** card (or **Near miss** on the right, then wait ~20s if you want Grok to speak).

> This week: a working satellite is predicted to pass 12 meters from a piece of Fengyun-1C debris at 14.5 km/s. That is a SOCRATES close approach, not a probability we computed.

## Shot 7 — Grok voice (optional, 20–40s)

Right panel: **1,000 sats** → **Ask + speak**. Globe flies to 500–550 km.

Skip this take if time is tight; shots 2–6 already tell the story without waiting on the model.

## Cutaways you can add later

- Chalk eval slide: “N/M recommendations stayed out of the 800 km junk band.”
- Imagine still: keep the caption “illustration, not data.”
