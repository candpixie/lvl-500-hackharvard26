"""eGRID2023 (rev2, metric) subregion CO2e output emission rates -> data/out/egrid_subregions.json.

Source: EPA eGRID2023, https://www.epa.gov/egrid/download-data
Field SRC2ERTA in the metric file = annual CO2e output emission rate, kg/MWh (= g/kWh).
"""
import json
import pathlib
import urllib.request

import pandas as pd

URL = "https://www.epa.gov/system/files/documents/2025-06/egrid2023_data_metric_rev2.xlsx"
ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = ROOT / "data/raw/egrid2023_data_metric_rev2.xlsx"
OUT = ROOT / "data/out/egrid_subregions.json"


def main():
    if not RAW.exists():
        RAW.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(URL, RAW)
    df = pd.read_excel(RAW, "SRL23", header=1)
    rows = [
        {
            "subregion": r.SUBRGN,
            "name": r.SRNAME,
            "co2e_g_per_kwh": round(float(r.SRC2ERTA), 1),
        }
        for r in df.itertuples()
    ]
    rows.sort(key=lambda r: r["co2e_g_per_kwh"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"source": "EPA eGRID2023 rev2, SRC2ERTA", "unit": "gCO2e/kWh", "subregions": rows}, indent=2))
    print(f"wrote {len(rows)} subregions to {OUT}")


if __name__ == "__main__":
    main()
