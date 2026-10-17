# What the ESpaS CSV columns mean

Read from `src/commands/design_space.rs` in ESpaS. One row = one satellite design at a given
mission length and redundancy. Use `redundancy == 1` unless you mean spare hardware.

| Column | Meaning | Unit |
|---|---|---|
| mission_time_yr | How long the satellite runs | years |
| redundancy | Copies of the compute payload (spares). Platform is not multiplied | x |
| total_mass_kg | Platform (solar + battery + radiator) + payload (compute, storage, network) x redundancy | kg |
| solar_mass_kg, battery_mass_kg, radiator_mass_kg | Platform parts | kg |
| cpu/gpu/dram/ssd/transceiver_mass_kg | Payload parts | kg |
| launch_carbon_kgco2e | total_mass x launch-and-re-entry intensity of the rocket | kgCO2e |
| production_carbon_kgco2e | Manufacturing: platform + data center hardware x redundancy. **Includes the GPU's own embodied carbon** | kgCO2e |
| total_carbon_kgco2e | launch + production | kgCO2e |
| carbon_per_gpu_hr_launch_gco2e | launch carbon / (mission_time x 8760) | gCO2e per **system**-hour |
| carbon_per_gpu_hr_total_gco2e | total carbon / (mission_time x 8760) | gCO2e per **system**-hour |
| solar_degradation_eol_pct | Solar power left at end of life vs start | % |

## Gotchas
- "per GPU hour" is really **per satellite hour**. ESpaS divides by mission hours, not GPU count.
  For the 100 kW config (100 GPUs) that's per 100 GPUs.
- ESpaS models shadow with one fixed sun angle (`sunlight_beta` in the config): 0 for Starcloud-1
  (worst case), 67.8 for the 100 kW design (almost no shadow). Real orbits change through the
  year. That's what our `pipeline/shadow.py` adds.
- Production carbon includes the GPU, which a ground data center would also need. For a
  payback comparison, subtract the compute hardware from the orbit's debt (see findings).
- The Starcloud-1 config comment says "325 km" but uses `altitude = 510`. The real satellite
  (NORAD 66303) currently sits at about 505 km, 45.4 deg inclination, so 510 is right.
