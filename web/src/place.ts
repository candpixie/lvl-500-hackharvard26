import { CanvasTexture, Sprite, SpriteMaterial } from 'three'

export const EARTH_RADIUS_KM = 6371
export const GLOBE_RADIUS = 100
export const ORBIT_COLOR = '#E7F27A'
export const PLACE_STAR_COLOR = '#F5C542'

const STEPS = 240
const MU_KM3_S2 = 398600.4418
const EARTH_RATE_RAD_S = 7.292115e-5
const TRACK_RADIUS = GLOBE_RADIUS * 1.006

function wrap360(deg: number) {
  const turned = deg % 360
  return turned < 0 ? turned + 360 : turned
}

export function raanFor(inclinationDeg: number, latDeg: number, lonDeg: number) {
  const inc = (inclinationDeg * Math.PI) / 180
  const lat = (Math.max(-90, Math.min(90, latDeg)) * Math.PI) / 180
  const lon = (lonDeg * Math.PI) / 180
  const sinI = Math.sin(inc)
  if (Math.abs(sinI) < 1e-8) return wrap360(lonDeg)
  const u = Math.asin(Math.max(-1, Math.min(1, Math.sin(lat) / sinI)))
  const cosU = Math.cos(u)
  const sinU = Math.sin(u)
  const k = sinU * Math.cos(inc)
  const xOrb = Math.cos(lat) * Math.cos(lon)
  const yOrb = Math.cos(lat) * Math.sin(lon)
  const det = cosU * cosU + k * k
  if (det < 1e-12) return wrap360(lonDeg)
  const cosO = (cosU * xOrb + k * yOrb) / det
  const sinO = (cosU * yOrb - k * xOrb) / det
  return wrap360((Math.atan2(sinO, cosO) * 180) / Math.PI)
}

function writeGlobe(xOrb: number, yOrb: number, zOrb: number, radius: number, out: Float32Array, offset: number) {
  out[offset] = radius * yOrb
  out[offset + 1] = radius * zOrb
  out[offset + 2] = radius * xOrb
}

function ecefUnit(inclinationDeg: number, raanDeg: number, argument: number, elapsedSec: number) {
  const inc = (inclinationDeg * Math.PI) / 180
  const raan = (raanDeg * Math.PI) / 180
  const cosU = Math.cos(argument)
  const sinU = Math.sin(argument)
  const cosI = Math.cos(inc)
  const x = cosU * Math.cos(raan) - sinU * cosI * Math.sin(raan)
  const y = cosU * Math.sin(raan) + sinU * cosI * Math.cos(raan)
  const z = sinU * Math.sin(inc)
  const rot = EARTH_RATE_RAD_S * elapsedSec
  const cosR = Math.cos(rot)
  const sinR = Math.sin(rot)
  return {
    x: x * cosR + y * sinR,
    y: -x * sinR + y * cosR,
    z,
  }
}

export function meanMotionRadPerSec(altitudeKm: number) {
  const radius = EARTH_RADIUS_KM + Math.max(0, altitudeKm)
  return Math.sqrt(MU_KM3_S2 / (radius * radius * radius))
}

export function groundTrackPositions(altitudeKm: number, inclinationDeg: number, raanDeg: number, orbits = 3) {
  const motion = meanMotionRadPerSec(altitudeKm)
  const period = (Math.PI * 2) / motion
  const steps = Math.round(orbits * 180)
  const out = new Float32Array((steps + 1) * 3)
  for (let i = 0; i <= steps; i++) {
    const elapsed = (i / steps) * orbits * period
    const unit = ecefUnit(inclinationDeg, raanDeg, motion * elapsed, elapsed)
    writeGlobe(unit.x, unit.y, unit.z, TRACK_RADIUS, out, i * 3)
  }
  return out
}

export const CONSTELLATION_DRAW_CAP = 2000

export function writeConstellation(
  altitudeKm: number,
  inclinationDeg: number,
  raanDeg: number,
  count: number,
  elapsedSec: number,
  out: Float32Array,
) {
  const drawn = Math.min(CONSTELLATION_DRAW_CAP, Math.max(0, Math.floor(count)))
  const motion = meanMotionRadPerSec(altitudeKm)
  const radius = GLOBE_RADIUS * (1 + Math.max(0, altitudeKm) / EARTH_RADIUS_KM)
  for (let i = 0; i < drawn; i++) {
    const argument = (i / drawn) * Math.PI * 2 + motion * elapsedSec
    const unit = ecefUnit(inclinationDeg, raanDeg, argument, elapsedSec)
    writeGlobe(unit.x, unit.y, unit.z, radius, out, i * 3)
  }
  return drawn
}

export function orbitLine(
  altitudeKm: number,
  inclinationDeg: number,
  raanDeg = 28,
  exaggerate = 1,
  markerLatDeg?: number,
) {
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

  let markerStep = Math.round(STEPS * 0.18)
  if (markerLatDeg != null && Math.abs(sinI) > 1e-4) {
    const sinU = Math.sin((markerLatDeg * Math.PI) / 180) / sinI
    const clamped = Math.max(-1, Math.min(1, sinU))
    const ascending = Math.asin(clamped)
    if (Number.isFinite(ascending)) markerStep = Math.round((ascending / (Math.PI * 2)) * STEPS)
  }
  const marker = markerStep * 3
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
