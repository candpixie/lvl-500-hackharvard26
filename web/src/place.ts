import { CanvasTexture, Sprite, SpriteMaterial } from 'three'

export const EARTH_RADIUS_KM = 6371
export const GLOBE_RADIUS = 100
export const ORBIT_COLOR = '#E7F27A'
export const PLACE_STAR_COLOR = '#F5C542'

const STEPS = 240

export function orbitLine(altitudeKm: number, inclinationDeg: number, raanDeg = 28, exaggerate = 1) {
  const positions = new Float32Array((STEPS + 1) * 3)
  const inc = (inclinationDeg * Math.PI) / 180
  const raan = (raanDeg * Math.PI) / 180
  const realRel = Math.max(altitudeKm / EARTH_RADIUS_KM, 0)
  const radius = GLOBE_RADIUS * (1 + Math.min(realRel, 0.5) * exaggerate)
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

export function goldStarSprite() {
  const canvas = document.createElement('canvas')
  canvas.width = 128
  canvas.height = 128
  const ctx = canvas.getContext('2d')
  if (!ctx) return new Sprite()
  const cx = 64
  const cy = 64
  const spikes = 5
  const outer = 58
  const inner = 24
  ctx.beginPath()
  for (let i = 0; i < spikes * 2; i++) {
    const radius = i % 2 === 0 ? outer : inner
    const angle = -Math.PI / 2 + (i * Math.PI) / spikes
    const x = cx + Math.cos(angle) * radius
    const y = cy + Math.sin(angle) * radius
    if (i === 0) ctx.moveTo(x, y)
    else ctx.lineTo(x, y)
  }
  ctx.closePath()
  ctx.shadowColor = '#FFE38A'
  ctx.shadowBlur = 20
  ctx.fillStyle = PLACE_STAR_COLOR
  ctx.fill()
  const material = new SpriteMaterial({
    map: new CanvasTexture(canvas),
    transparent: true,
    depthWrite: false,
  })
  const sprite = new Sprite(material)
  sprite.scale.set(16, 16, 1)
  sprite.visible = false
  return sprite
}
