# orbit-payback

HackHarvard 2026. Every orbital data center starts in carbon debt from being built and launched.
We show whether it pays that debt back before the hardware dies, for real data centers, using real
satellite orbits and the peer-reviewed ESpaS model.

## Run the pipeline
Needs [uv](https://docs.astral.sh/uv/).

```sh
uv run python pipeline/egrid.py          # grid carbon by US subregion -> data/out/egrid_subregions.json
(cd data/raw && uv run python ../../pipeline/shadow.py)   # one year of real orbits -> data/out/shadow.json
uv run python pipeline/payback_rough.py  # ROUGH payback numbers -> data/out/payback_rough.json
```

`data/raw/` (eGRID workbook, DE421 ephemeris) is downloaded on first run and not committed.

## Layout
- `pipeline/` Python, offline. Writes static JSON to `data/out/`.
- `data/espas/` ESpaS CSVs and configs, copied unchanged (see NOTICE.md).
- `docs/findings.md` what we've learned so far. Read this first.
- `docs/espas-columns.md` what every ESpaS column means, plus gotchas.
- `web/` frontend, built in Cursor (SpaceX AI challenge requirement). Reads only `data/out/`.

## Tasks
- [x] ESpaS CSVs read and documented
- [x] Shadow fraction from real orbits (Starcloud-1, Starlink, dawn-dusk, ISS check)
- [x] Grid carbon for every US subregion
- [ ] Pick 5 real data centers: name, location, announced MW with a source link, eGRID subregion. At least one with documented dedicated clean power (hydro or nuclear contract) so the verdict can flip
- [ ] Real payback model: battery mass from simulated shadow, fix the simplifications in `payback_rough.py`, reproduce ESpaS CSV rows within 1%
- [ ] Grok API key working (Imagine + Voice), Cursor installed for everyone, log Cursor and Grok Bot use for the Devpost
- [ ] Frontend: site picker, payback clock, orbit view

## Sources
- ESpaS, MIT/Apache-2.0: https://gitlab.com/sustainable-computing-systems/espas
- Ohs et al., Dirty Bits in Low-Earth Orbit, arXiv 2508.06250
- EPA eGRID2023 rev2: https://www.epa.gov/egrid/download-data
- CelesTrak GP data: https://celestrak.org
- skyfield + JPL DE421 ephemeris
