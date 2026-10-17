// Pure helpers for the "What are you launching?" picker. No React here so they can be tested on their own.

export const ALTITUDE_MIN_KM = 200
export const ALTITUDE_MAX_KM = 1950
export const ALTITUDE_STEP_KM = 5

/** Tracked objects per 50 km shell and 10 degree inclination band (a lower bound), from launch_kinds.json. */
export interface BandGrid {
  alt_lo: number[]
  alt_step_km: number
  inc_lo: number[]
  inc_step_deg: number
  total: number[][]
  shell_total: number[]
  debris: number[][]
  note: string
}

export interface BandNeighbors {
  shellLo: number
  shellHi: number
  incLo: number
  incHi: number
  inBand: number
  wholeShell: number
  debrisInBand: number
}

/** The slider positions for a kind's typical orbit: the median altitude on the slider's 5 km steps, the median
 *  inclination to the nearest degree, both kept inside the slider's range. */
export function presetOrbit(medianAltitudeKm: number, medianInclinationDeg: number) {
  const altitude = Math.round(medianAltitudeKm / ALTITUDE_STEP_KM) * ALTITUDE_STEP_KM
  return {
    altitude: Math.min(ALTITUDE_MAX_KM, Math.max(ALTITUDE_MIN_KM, altitude)),
    inclination: Math.min(180, Math.max(0, Math.round(medianInclinationDeg))),
  }
}

/** How many of the tracked objects in this altitude's shell are in this orbit's inclination band. Null when the
 *  altitude is outside the grid. */
export function bandNeighbors(grid: BandGrid, altitudeKm: number, inclinationDeg: number): BandNeighbors | null {
  const first = grid.alt_lo[0]
  const shell = Math.floor((altitudeKm - first) / grid.alt_step_km)
  if (!Number.isFinite(shell) || shell < 0 || shell >= grid.alt_lo.length) return null
  const band = Math.min(grid.inc_lo.length - 1, Math.max(0, Math.floor(inclinationDeg / grid.inc_step_deg)))
  const row = grid.total[shell]
  return {
    shellLo: grid.alt_lo[shell],
    shellHi: grid.alt_lo[shell] + grid.alt_step_km,
    incLo: grid.inc_lo[band],
    incHi: grid.inc_lo[band] + grid.inc_step_deg,
    inBand: row[band],
    wholeShell: grid.shell_total[shell],
    debrisInBand: grid.debris[shell][band],
  }
}
