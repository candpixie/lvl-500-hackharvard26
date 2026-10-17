import {
  degreesLat,
  degreesLong,
  eciToGeodetic,
  gstime,
  json2satrec,
  propagate,
  type OMMJsonObject,
  type SatRec,
} from 'satellite.js'
import type { OrbitCounts, WorkerOut } from './orbit.ts'

const EARTH_RADIUS_KM = 6371
const GLOBE_RADIUS = 100

const COLOR: Record<keyof OrbitCounts, readonly [number, number, number]> = {
  satellite: [0xc9 / 255, 0xd6 / 255, 0xe3 / 255],
  debris: [0xf2 / 255, 0xa5 / 255, 0x41 / 255],
  'rocket body': [0x8c / 255, 0x7a / 255, 0xe6 / 255],
  unknown: [0x8b / 255, 0x97 / 255, 0xa6 / 255],
}

interface CatalogObject {
  name?: string
  type: string
  apogee_km: number | null
  perigee_km: number | null
  omm: OMMJsonObject
}

interface LiveObject {
  satrec: SatRec
  type: keyof OrbitCounts
}

function post(message: WorkerOut, transfer: Transferable[] = []) {
  ;(self as unknown as { postMessage(message: WorkerOut, transfer: Transferable[]): void }).postMessage(
    message,
    transfer,
  )
}

function meanAltitude(obj: CatalogObject) {
  const high = obj.apogee_km
  const low = obj.perigee_km
  if (typeof high !== 'number' || typeof low !== 'number' || !Number.isFinite(high) || !Number.isFinite(low)) return -1
  return (high + low) / 2
}

function objectType(type: string): keyof OrbitCounts {
  if (type === 'satellite' || type === 'debris' || type === 'rocket body' || type === 'unknown') return type
  return 'unknown'
}

function writeXyz(latDeg: number, lngDeg: number, altKm: number, out: Float32Array, offset: number) {
  const phi = ((90 - latDeg) * Math.PI) / 180
  const theta = ((90 - lngDeg) * Math.PI) / 180
  const radius = GLOBE_RADIUS * (1 + altKm / EARTH_RADIUS_KM)
  const phiSin = Math.sin(phi)
  out[offset] = radius * phiSin * Math.cos(theta)
  out[offset + 1] = radius * Math.cos(phi)
  out[offset + 2] = radius * phiSin * Math.sin(theta)
}

function place(satrec: SatRec, now: Date, gmst: number, out: Float32Array, offset: number) {
  const pv = propagate(satrec, now)
  const position = pv?.position
  if (!position || !Number.isFinite(position.x) || !Number.isFinite(position.y) || !Number.isFinite(position.z)) {
    return false
  }
  const gd = eciToGeodetic(position, gmst)
  if (!Number.isFinite(gd.latitude) || !Number.isFinite(gd.longitude) || !Number.isFinite(gd.height)) {
    return false
  }
  if (gd.height < -50) return false
  writeXyz(degreesLat(gd.latitude), degreesLong(gd.longitude), gd.height, out, offset)
  return true
}

function hold(from: Float32Array, to: Float32Array, offset: number) {
  to[offset] = from[offset]
  to[offset + 1] = from[offset + 1]
  to[offset + 2] = from[offset + 2]
}

async function main() {
  let objects: CatalogObject[] = []
  try {
    const response = await fetch('/objects.json')
    if (!response.ok) {
      post({ kind: 'error', message: `Could not load orbits (${response.status})` })
      return
    }
    const payload = (await response.json()) as { objects?: CatalogObject[] }
    objects = payload.objects ?? []
  } catch (error) {
    post({ kind: 'error', message: error instanceof Error ? error.message : 'Could not load orbits' })
    return
  }

  const now = new Date()
  const gmst = gstime(now)
  const kept: LiveObject[] = []
  const positions = new Float32Array(objects.length * 3)
  const colorList: number[] = []
  const altitudeList: number[] = []
  const kindList: number[] = []
  const nameList: string[] = []
  const typeList: string[] = []
  let latestEpoch = ''
  const counts: OrbitCounts = { satellite: 0, debris: 0, 'rocket body': 0, unknown: 0 }

  for (const obj of objects) {
    const type = objectType(obj.type)
    let satrec: SatRec
    try {
      satrec = json2satrec(obj.omm)
    } catch {
      continue
    }
    const offset = kept.length * 3
    if (!place(satrec, now, gmst, positions, offset)) continue
    kept.push({ satrec, type })
    counts[type] += 1
    const [r, g, b] = COLOR[type]
    colorList.push(r, g, b)
    altitudeList.push(meanAltitude(obj))
    kindList.push(type === 'debris' ? 1 : 0)
    const ommName = (obj.omm as { OBJECT_NAME?: string }).OBJECT_NAME
    nameList.push((typeof obj.name === 'string' && obj.name) || ommName || 'UNKNOWN')
    typeList.push(type)
    const epoch = obj.omm.EPOCH
    if (typeof epoch === 'string' && epoch > latestEpoch) latestEpoch = epoch
  }

  const livePositions = positions.slice(0, kept.length * 3)
  const colors = new Float32Array(colorList)
  const altitudes = new Float32Array(altitudeList)
  const kinds = new Float32Array(kindList)
  const firstFrame = new Float32Array(livePositions)
  post(
    {
      kind: 'ready',
      count: kept.length,
      catalog: objects.length,
      counts,
      colors,
      positions: firstFrame,
      altitudes,
      kinds,
      names: nameList,
      types: typeList,
      epoch: latestEpoch.slice(0, 10),
    },
    [colors.buffer, firstFrame.buffer, altitudes.buffer, kinds.buffer],
  )

  const tick = () => {
    const started = performance.now()
    const tickNow = new Date()
    const tickGmst = gstime(tickNow)
    const frame = new Float32Array(livePositions.length)
    for (let i = 0; i < kept.length; i++) {
      const offset = i * 3
      if (!place(kept[i].satrec, tickNow, tickGmst, frame, offset)) hold(livePositions, frame, offset)
    }
    livePositions.set(frame)
    const copy = new Float32Array(livePositions)
    post({ kind: 'positions', positions: copy }, [copy.buffer])
    setTimeout(tick, Math.max(0, 1000 - (performance.now() - started)))
  }
  setTimeout(tick, 1000)
}

void main()
