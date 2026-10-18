import { Vector3, type Camera } from 'three'
import type { Neighborhood, NearbyObject } from './events.ts'
import { shellBounds } from './shells.ts'

const GLOBE_RADIUS = 100
const EXAGGERATION = 5.5
const scratch = new Vector3()

export function exaggeratePoint(x: number, y: number, z: number, factor: number) {
  const r = Math.hypot(x, y, z) || 1
  const realRel = Math.max(r / GLOBE_RADIUS - 1, 0)
  const visualR = GLOBE_RADIUS * (1 + Math.min(realRel, 0.5) * factor)
  const scale = visualR / r
  return [x * scale, y * scale, z * scale] as const
}

export function pickNearest(
  positions: Float32Array,
  origin: { x: number; y: number; z: number },
  dir: { x: number; y: number; z: number },
  count: number,
  exaggerate: number,
  maxDist = 8,
) {
  let best = -1
  let bestDist = maxDist
  for (let i = 0; i < count; i++) {
    const [vx, vy, vz] = exaggeratePoint(positions[i * 3], positions[i * 3 + 1], positions[i * 3 + 2], exaggerate)
    const px = vx - origin.x
    const py = vy - origin.y
    const pz = vz - origin.z
    const t = px * dir.x + py * dir.y + pz * dir.z
    if (t < 0) continue
    const dx = vx - (origin.x + t * dir.x)
    const dy = vy - (origin.y + t * dir.y)
    const dz = vz - (origin.z + t * dir.z)
    const dist = Math.hypot(dx, dy, dz)
    if (dist < bestDist) {
      bestDist = dist
      best = i
    }
  }
  return best
}

export function screenNearest(options: {
  positions: Float32Array
  altitudes: Float32Array
  kinds: Float32Array
  camera: Camera
  width: number
  height: number
  x: number
  y: number
  altitudeKm: number
  debrisOnly: boolean
  radiusPx: number
  /** When false, a click can land on a dim dot outside the altitude on the slider. */
  shellOnly?: boolean
}): number | null {
  const { positions, camera, width, height, x, y } = options
  const cam = camera.position
  const camLen = Math.hypot(cam.x, cam.y, cam.z) || 1
  const bounds = shellBounds(options.altitudeKm)
  let best = -1
  let bestDistance = options.radiusPx * options.radiusPx
  const count = positions.length / 3

  for (let index = 0; index < count; index++) {
    const altitude = options.altitudes[index]
    if (options.shellOnly !== false && (altitude < bounds.min || altitude > bounds.max)) continue
    if (options.debrisOnly && options.kinds[index] < 0.5) continue
    const px = positions[index * 3]
    const py = positions[index * 3 + 1]
    const pz = positions[index * 3 + 2]
    const length = Math.hypot(px, py, pz)
    if (length < 1) continue
    if ((px * cam.x + py * cam.y + pz * cam.z) / (length * camLen) < 0.12) continue
    const realRel = Math.max(length / 100 - 1, 0)
    const radius = 100 * (1 + Math.min(realRel, 0.5) * EXAGGERATION)
    scratch.set((px * radius) / length, (py * radius) / length, (pz * radius) / length)
    scratch.project(camera)
    if (scratch.z < -1 || scratch.z > 1) continue
    const sx = (scratch.x * 0.5 + 0.5) * width
    const sy = (-scratch.y * 0.5 + 0.5) * height
    const dx = sx - x
    const dy = sy - y
    const distance = dx * dx + dy * dy
    if (distance < bestDistance) {
      bestDistance = distance
      best = index
    }
  }

  return best < 0 ? null : best
}

export function neighborhoodAround(
  index: number,
  positions: Float32Array,
  names: string[],
  types: string[],
  altitudes: Float32Array,
  nearbyCount = 8,
): Neighborhood {
  const picked: NearbyObject = {
    name: names[index] ?? 'unknown',
    type: types[index] ?? 'unknown',
    alt_km: altitudes[index] ?? 0,
  }
  const px = positions[index * 3]
  const py = positions[index * 3 + 1]
  const pz = positions[index * 3 + 2]
  const scored: { i: number; d: number }[] = []
  for (let i = 0; i < names.length; i++) {
    if (i === index) continue
    const dx = positions[i * 3] - px
    const dy = positions[i * 3 + 1] - py
    const dz = positions[i * 3 + 2] - pz
    scored.push({ i, d: dx * dx + dy * dy + dz * dz })
  }
  scored.sort((a, b) => a.d - b.d)
  const mix = { satellite: 0, debris: 0, 'rocket body': 0, unknown: 0 }
  const nearby: NearbyObject[] = []
  const nearbyIndices: number[] = []
  for (let n = 0; n < Math.min(40, scored.length); n++) {
    const i = scored[n].i
    const kind = (types[i] ?? 'unknown') as keyof typeof mix
    if (kind in mix) mix[kind] += 1
    else mix.unknown += 1
    if (nearby.length < nearbyCount) {
      nearby.push({ name: names[i] ?? 'unknown', type: types[i] ?? 'unknown', alt_km: altitudes[i] ?? 0 })
      nearbyIndices.push(i)
    }
  }
  return { picked, nearby, mix, pickedIndex: index, nearbyIndices }
}

export function neighborhoodInShell(
  altMin: number,
  altMax: number,
  names: string[],
  types: string[],
  altitudes: Float32Array,
  preferDebris = false,
): Neighborhood | null {
  const inShell: number[] = []
  const mix = { satellite: 0, debris: 0, 'rocket body': 0, unknown: 0 }
  for (let i = 0; i < names.length; i++) {
    const alt = altitudes[i]
    if (alt < altMin || alt > altMax) continue
    inShell.push(i)
    const kind = (types[i] ?? 'unknown') as keyof typeof mix
    if (kind in mix) mix[kind] += 1
    else mix.unknown += 1
  }
  if (!inShell.length) return null
  let pickedIdx = inShell[0]
  if (preferDebris) {
    const debris = inShell.find((i) => types[i] === 'debris')
    if (debris != null) pickedIdx = debris
  }
  const nearbyIdx = inShell.filter((i) => i !== pickedIdx).slice(0, 8)
  const nearby = nearbyIdx.map((i) => ({
    name: names[i] ?? 'unknown',
    type: types[i] ?? 'unknown',
    alt_km: altitudes[i] ?? 0,
  }))
  return {
    picked: {
      name: names[pickedIdx] ?? 'unknown',
      type: types[pickedIdx] ?? 'unknown',
      alt_km: altitudes[pickedIdx] ?? 0,
    },
    nearby,
    mix,
    pickedIndex: pickedIdx,
    nearbyIndices: nearbyIdx,
  }
}
