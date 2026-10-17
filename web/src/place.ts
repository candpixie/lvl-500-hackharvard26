export const EARTH_RADIUS_KM = 6371
export const GLOBE_RADIUS = 100
export const ORBIT_COLOR = '#E7F27A'

const STEPS = 240

export function orbitLine(altitudeKm: number, inclinationDeg: number, raanDeg = 28) {
  const positions = new Float32Array((STEPS + 1) * 3)
  const inc = (inclinationDeg * Math.PI) / 180
  const raan = (raanDeg * Math.PI) / 180
  const radius = GLOBE_RADIUS * (1 + altitudeKm / EARTH_RADIUS_KM)
  const cosI = Math.cos(inc)
  const sinI = Math.sin(inc)
  const cosO = Math.cos(raan)
  const sinO = Math.sin(raan)

  for (let i = 0; i <= STEPS; i++) {
    const u = (i / STEPS) * Math.PI * 2
    const cosU = Math.cos(u)
    const sinU = Math.sin(u)
    const x = cosU * cosO - sinU * cosI * sinO
    const y = cosU * sinO + sinU * cosI * cosO
    const z = sinU * sinI
    const offset = i * 3
    positions[offset] = radius * y
    positions[offset + 1] = radius * z
    positions[offset + 2] = radius * x
  }

  const marker = Math.round(STEPS * 0.18) * 3
  return {
    positions,
    marker: [positions[marker], positions[marker + 1], positions[marker + 2]] as const,
  }
}
