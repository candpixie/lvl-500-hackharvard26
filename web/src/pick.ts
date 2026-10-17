import { Vector3, type Camera } from 'three'
import { shellBounds } from './shells.ts'

const EXAGGERATION = 5.5
const scratch = new Vector3()

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
    if (altitude < bounds.min || altitude > bounds.max) continue
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
