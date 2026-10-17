# Findings so far (Fri Oct 16, night)

Everything here is reproducible from `pipeline/`. Numbers marked ROUGH are not for slides yet.

## 1. Shadow fraction from real orbits (`pipeline/shadow.py`, one year, 2-minute steps)
| Satellite | Altitude | Inclination | Time in shadow (year) | Days with no shadow |
|---|---|---|---|---|
| Starcloud-1 (NORAD 66303) | 505 km | 45.4 deg | 34.0% | 1 |
| Starlink-3240 (NORAD 49728) | 470 km | 53.2 deg | 32.8% | 12 |
| Sentinel-1A, dawn-dusk (NORAD 39634) | 702 km | 98.2 deg | 3.6% | 279 |
| ISS (known-answer check) | 427 km | 51.6 deg | 34.1% | 7 |

- Known-answer test passes: the ISS spends about a third of its time in shadow.
- Dawn-dusk orbits spend about 10x less time in shadow than Starlink-style orbits. Less shadow
  means smaller batteries, a lighter satellite and less launch carbon. That's the orbit toggle.
- ESpaS assumes one fixed sun angle. Starcloud-1's config uses the worst case (beta 0), which
  happens to be close to what we simulated (34%). The 100 kW design assumes almost no shadow,
  which only holds for a dawn-dusk orbit.

## 2. Grid carbon (`pipeline/egrid.py`, EPA eGRID2023 rev2)
US subregion averages run from **110 gCO2e/kWh (NYUP, upstate NY)** to **637 (MROE)** on the
mainland. Full list in `data/out/egrid_subregions.json`.

**This changes the pitch.** The paper's orbit number (52 to 66 gCO2e/kWh) is below **every**
US subregion average. So "Earth wins on a clean grid" is only true for a data center with its
own dedicated clean supply (hydro, nuclear, solar contracts), not for any US grid average.
The verdict still flips, but the clean side has to be a real site with dedicated clean power.

## 3. ROUGH payback (`pipeline/payback_rough.py`, 5-year mission rows)
| Scenario | Debt | vs NYUP 110 | vs SRMV 337 | vs MROE 637 | vs dedicated hydro (assumed 20) |
|---|---|---|---|---|---|
| Starcloud-1 (1 H100, Falcon 9) | 3,429 kg | 4.6 yr | 1.5 yr | 0.8 yr | 25 yr |
| 100 kW cluster (100 H100, Starship) | 179,200 kg | 2.4 yr | 0.8 yr | 0.4 yr | 13 yr |

- **Starcloud-1 flew an 11-month mission (0.92 yr).** At that length it only pays back against
  the dirtiest grids. Against upstate NY it would need about 4.6 years. Big if it holds,
  so check it before anyone says it out loud.
- A large Starship-launched cluster pays back fast against average US grids, and never within
  5 years against dedicated hydro. That's the flip for the demo.
- Simplifications are listed at the top of `payback_rough.py`. The real model has to fix them.

## Open
- Battery mass should come from our simulated shadow, not ESpaS's fixed angle.
- Pick the 5 real sites (see README tasks). The clean one needs documented dedicated clean power.
