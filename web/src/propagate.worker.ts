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
import { RING_DRAW_CAP, type ObjectFact, type OrbitCounts, type WorkerIn, type WorkerOut } from './orbit.ts'

const EARTH_RADIUS_KM = 6371
const GLOBE_RADIUS = 100
const MU_KM3_S2 = 398600.4418
/** Matches `ALTITUDE_EXAGGERATION` in App.tsx. Catalog dots get this in the point shader. */
const ALTITUDE_EXAGGERATION = 5.5

const COLOR: Record<keyof OrbitCounts, readonly [number, number, number]> = {
  satellite: [0.97, 0.98, 1],
  debris: [0xf2 / 255, 0xa5 / 255, 0x41 / 255],
  'rocket body': [0x8c / 255, 0x7a / 255, 0xe6 / 255],
  unknown: [0x8b / 255, 0x97 / 255, 0xa6 / 255],
}

interface CatalogObject {
  norad: number
  name: string
  type: string
  owner: string | null
  launch_date: string | null
  radar_size_m2: number | null
  apogee_km: number | null
  perigee_km: number | null
  constellation: string | null
  groups: string[]
  source_group: string
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

function writeXyz(latDeg: number, lngDeg: number, radius: number, out: Float32Array, offset: number) {
  const phi = ((90 - latDeg) * Math.PI) / 180
  const theta = ((90 - lngDeg) * Math.PI) / 180
  const phiSin = Math.sin(phi)
  out[offset] = radius * phiSin * Math.cos(theta)
  out[offset + 1] = radius * Math.cos(phi)
  out[offset + 2] = radius * phiSin * Math.sin(theta)
}

function trueRadius(altKm: number) {
  return GLOBE_RADIUS * (1 + altKm / EARTH_RADIUS_KM)
}

/** Same radius the catalog point shader draws: capped relative altitude times 5.5. */
function shellRadius(altKm: number) {
  const realRel = Math.max(altKm, 0) / EARTH_RADIUS_KM
  return GLOBE_RADIUS * (1 + Math.min(realRel, 0.5) * ALTITUDE_EXAGGERATION)
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
  writeXyz(degreesLat(gd.latitude), degreesLong(gd.longitude), trueRadius(gd.height), out, offset)
  return true
}

function ringShown(count: number) {
  if (!Number.isFinite(count) || count < 1) return 0
  return Math.min(RING_DRAW_CAP, Math.round(count))
}

function meanMotion(altKm: number) {
  const radius = EARTH_RADIUS_KM + Math.max(altKm, 0)
  return Math.sqrt(MU_KM3_S2 / (radius * radius * radius))
}

function writeRing(
  altKm: number,
  incDeg: number,
  count: number,
  seconds: number,
  gmst: number,
  out: Float32Array,
) {
  const shown = ringShown(count)
  if (shown < 1) return 0
  const motion = meanMotion(altKm)
  const radius = shellRadius(altKm)
  const inc = (incDeg * Math.PI) / 180
  const sinI = Math.sin(inc)
  const cosI = Math.cos(inc)
  const planes = Math.max(1, Math.round(Math.sqrt(shown)))
  const perPlane = Math.ceil(shown / planes)
  let n = 0
  for (let k = 0; k < planes && n < shown; k++) {
    const raan = (k * Math.PI * 2) / planes
    for (let j = 0; j < perPlane && n < shown; j++) {
      const u = (j * Math.PI * 2) / perPlane + (k * Math.PI * 2) / shown + motion * seconds
      const lat = Math.asin(sinI * Math.sin(u))
      const lng = raan + Math.atan2(cosI * Math.sin(u), Math.cos(u)) - gmst
      writeXyz((lat * 180) / Math.PI, (lng * 180) / Math.PI, radius, out, n * 3)
      n += 1
    }
  }
  return n
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
  const facts: ObjectFact[] = []
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
    const inclination = obj.omm.INCLINATION
    facts.push({
      name: obj.name,
      norad: obj.norad,
      type,
      owner: obj.owner,
      launch: obj.launch_date,
      apogee: obj.apogee_km,
      perigee: obj.perigee_km,
      meanKm: meanAltitude(obj),
      inclination: typeof inclination === 'number' && Number.isFinite(inclination) ? inclination : null,
      radar: typeof obj.radar_size_m2 === 'number' && obj.radar_size_m2 > 0 ? obj.radar_size_m2 : null,
      constellation: obj.constellation,
      groups: obj.groups ?? [],
      sourceGroup: obj.source_group,
    })
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
      epoch: latestEpoch.slice(0, 10),
      facts,
    },
    [colors.buffer, firstFrame.buffer, altitudes.buffer, kinds.buffer],
  )

  let rate = 1
  let simMs = Date.now()
  let lastReal = performance.now()
  let ringAlt = 480
  let ringInc = 53
  let ringCount = 1000
  self.onmessage = (event: MessageEvent<WorkerIn>) => {
    const data = event.data
    if (!data || data.kind === 'rate') {
      const next = data && data.kind === 'rate' ? data.rate : 1
      if (next !== 1 && next !== 60 && next !== 600) return
      if (next === 1) simMs = Date.now()
      rate = next
      return
    }
    if (!Number.isFinite(data.altKm) || !Number.isFinite(data.incDeg) || !Number.isFinite(data.count)) return
    ringAlt = data.altKm
    ringInc = data.incDeg
    ringCount = data.count
  }

  const tick = () => {
    const started = performance.now()
    const elapsed = Math.min(250, started - lastReal)
    lastReal = started
    if (rate === 1) simMs = Date.now()
    else simMs += elapsed * rate
    const tickNow = new Date(simMs)
    const tickGmst = gstime(tickNow)
    const frame = new Float32Array(livePositions.length)
    for (let i = 0; i < kept.length; i++) {
      const offset = i * 3
      if (!place(kept[i].satrec, tickNow, tickGmst, frame, offset)) hold(livePositions, frame, offset)
    }
    livePositions.set(frame)
    const copy = new Float32Array(livePositions)
    const shown = ringShown(ringCount)
    const ring = new Float32Array(shown * 3)
    writeRing(ringAlt, ringInc, ringCount, simMs / 1000, tickGmst, ring)
    post({ kind: 'positions', positions: copy, ring, simMs, rate }, [copy.buffer, ring.buffer])
    const wait = rate > 1 ? 33 : 1000
    setTimeout(tick, Math.max(0, wait - (performance.now() - started)))
  }
  lastReal = performance.now()
  setTimeout(tick, 1000)
}

void main()
