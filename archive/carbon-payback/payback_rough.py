"""ROUGH first pass at carbon payback, straight from the ESpaS CSVs. Not for slides yet.

debt   = launch carbon + production carbon - GPU embodied carbon (a ground site needs the GPU too)
yearly = ground IT power x PUE x 8760 h x grid intensity (what the orbit avoids each year)
payback_years = debt / yearly

Known simplifications (fix in the real model):
- Only the GPU is subtracted from debt. CPU, memory, storage and network are left in, so debt is slightly high.
- Ground load = GPU power x 1.1 PUE. Real ground PUE is 1.1 to 1.5, which would shorten payback.
- Battery size uses ESpaS's fixed sun angle, not our simulated shadow fraction.
- Ignores ground building construction, cooling water, and orbit downtime.
"""
import json
import pathlib

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCENARIOS = {
    # name: (csv, GPU embodied kgCO2e from the config, ground GPU power kW)
    "starcloud-1 (1 H100, Falcon 9)": ("starcloud1_ds.csv", 1312.0, 0.70),
    "100 kW GPU cluster (100 H100, Starship)": ("gpu_dc_100kw_ds.csv", 131200.0, 70.0),
}
PUE = 1.1


def main():
    eg = json.loads((ROOT / "data/out/egrid_subregions.json").read_text())["subregions"]
    rate = {r["subregion"]: r["co2e_g_per_kwh"] for r in eg}
    grids = {"NYUP": rate["NYUP"], "SRMV": rate["SRMV"], "MROE": rate["MROE"], "dedicated hydro (assumed 20)": 20.0}
    out = []
    for name, (csv, gpu_kg, kw) in SCENARIOS.items():
        d = pd.read_csv(ROOT / "data/espas" / csv)
        r = d[(d.redundancy == 1) & (d.mission_time_yr == 5.0)].iloc[0]
        debt = r.launch_carbon_kgco2e + r.production_carbon_kgco2e - gpu_kg
        print(f"{name}: debt {debt:,.0f} kgCO2e (launch {r.launch_carbon_kgco2e:,.0f})")
        for g, gi in grids.items():
            yearly = kw * PUE * 8760 * gi / 1000
            yrs = debt / yearly
            print(f"   vs {g:30s} {gi:6.1f} g/kWh -> payback {yrs:5.2f} years")
            out.append({"scenario": name, "grid": g, "grid_g_per_kwh": gi, "debt_kg": round(debt), "payback_years": round(yrs, 2)})
    (ROOT / "data/out/payback_rough.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
