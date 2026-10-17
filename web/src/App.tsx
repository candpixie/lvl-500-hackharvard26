import { useEffect, useRef, useState } from 'react'
import Globe from 'globe.gl'
import { ShaderMaterial, type MeshPhongMaterial } from 'three'
import '@fontsource/ibm-plex-mono/400.css'
import '@fontsource/ibm-plex-mono/500.css'
import { createFleet, type Fleet } from './fleet.ts'
import ObjectCard from './ObjectCard.tsx'
import type { ObjectFact, OrbitCounts, WorkerOut } from './orbit.ts'
import { screenNearest } from './pick.ts'
import PlacePanel from './PlacePanel.tsx'
import { shellBounds, type ShellRow } from './shells.ts'

const LEGEND: { key: keyof OrbitCounts; label: string; color: string }[] = [
  { key: 'satellite', label: 'satellite', color: '#C9D6E3' },
  { key: 'debris', label: 'debris', color: '#F2A541' },
  { key: 'rocket body', label: 'rocket body', color: '#8C7AE6' },
  { key: 'unknown', label: 'unidentified', color: '#8B97A6' },
]

const ZOOM_HIDE_ALTITUDE = 1.15
const START_ALTITUDE = 480
const ALTITUDE_EXAGGERATION = 5.5

type Status = { state: 'loading' } | { state: 'error'; message: string } | { state: 'ready' }

const craftVertex = `
  attribute float aAlt;
  attribute float aKind;
  attribute float aId;
  uniform float uShellMin;
  uniform float uShellMax;
  uniform float uDim;
  uniform float uHideOutside;
  uniform float uDebrisOnly;
  uniform float uPick;
  varying vec3 vColor;
  varying float vAlpha;
  void main() {
    float inside = step(uShellMin, aAlt) * step(aAlt, uShellMax);
    float debris = step(0.5, aKind);
    float picked = step(abs(aId - uPick), 0.5);
    vec3 shaped = position * mix(1.0, 1.65, picked);
    vec4 placed = instanceMatrix * vec4(shaped, 1.0);
    vec3 lit = normalize(mat3(instanceMatrix) * normal);
    float shade = 0.62 + 0.38 * max(dot(lit, normalize(vec3(0.35, 0.82, 0.28))), 0.0);
    if (debris > 0.5) vAlpha = mix(uDebrisOnly > 0.5 ? 0.1 : 0.78, 1.0, inside);
    else vAlpha = mix(uDim, 1.0, inside);
    if (uHideOutside > 0.5) vAlpha *= inside;
    if (uDebrisOnly > 0.5) vAlpha *= debris;
    vAlpha = max(vAlpha, picked);
    vColor = color * instanceColor * shade * mix(1.0, 1.25, picked);
    gl_Position = projectionMatrix * modelViewMatrix * placed;
  }
`

const craftFragment = `
  varying vec3 vColor;
  varying float vAlpha;
  void main() {
    if (vAlpha < 0.03) discard;
    gl_FragColor = vec4(vColor * vAlpha, 1.0);
  }
`

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function formatEpoch(day: string) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(day)
  if (!match) return day
  const month = MONTHS[Number(match[2]) - 1]
  if (!month) return day
  return `${Number(match[3])} ${month} ${match[1]}`
}

function webglAvailable() {
  try {
    const canvas = document.createElement('canvas')
    return Boolean(canvas.getContext('webgl2') || canvas.getContext('webgl'))
  } catch {
    return false
  }
}

function fleetMaterial(altitudeKm: number) {
  const bounds = shellBounds(altitudeKm)
  return new ShaderMaterial({
    uniforms: {
      uShellMin: { value: bounds.min },
      uShellMax: { value: bounds.max },
      uDim: { value: 0.04 },
      uHideOutside: { value: 0 },
      uDebrisOnly: { value: 0 },
      uPick: { value: -1 },
    },
    vertexShader: craftVertex,
    fragmentShader: craftFragment,
    vertexColors: true,
  })
}

export default function App() {
  const hostRef = useRef<HTMLDivElement>(null)
  const applyShellRef = useRef<(altitudeKm: number) => void>(() => {})
  const debrisRef = useRef<(on: boolean) => void>(() => {})
  const [status, setStatus] = useState<Status>({ state: 'loading' })
  const [altitude, setAltitude] = useState(START_ALTITUDE)
  const [shells, setShells] = useState<ShellRow[] | null>(null)
  const [shellError, setShellError] = useState<string | null>(null)
  const [debrisOnly, setDebrisOnly] = useState(false)
  const [epoch, setEpoch] = useState('')
  const [close, setClose] = useState(false)
  const [fact, setFact] = useState<ObjectFact | null>(null)
  const [liveKm, setLiveKm] = useState<number | null>(null)
  const [graphics] = useState<'ok' | 'missing'>(() => (webglAvailable() ? 'ok' : 'missing'))
  const altitudeRef = useRef(altitude)
  const debrisOnlyRef = useRef(debrisOnly)
  const clearPickRef = useRef<() => void>(() => {})

  useEffect(() => {
    const host = hostRef.current
    if (!host || graphics !== 'ok') return

    const globe = (() => {
      try {
        return new Globe(host, {
          rendererConfig: { antialias: true, alpha: false, failIfMajorPerformanceCaveat: false },
        })
      } catch {
        return null
      }
    })()
    if (!globe) {
      setStatus({ state: 'error', message: 'This view needs WebGL. The orbit map cannot draw without it.' })
      return
    }

    globe
      .backgroundColor('#05070B')
      .showAtmosphere(true)
      .atmosphereColor('#9bb8d4')
      .atmosphereAltitude(0.11)
      .pointOfView({ lat: 18, lng: 12, altitude: 1.65 }, 0)

    const surface = globe.globeMaterial() as MeshPhongMaterial
    surface.color.set('#243444')
    surface.emissive.set('#15202c')
    surface.emissiveIntensity = 0.55
    surface.shininess = 12

    void fetch('/land-110m.geojson')
      .then((response) => (response.ok ? response.json() : null))
      .then((land: { features?: object[] } | null) => {
        if (!land?.features) return
        globe
          .polygonsData(land.features)
          .polygonCapColor(() => 'rgba(46, 66, 84, 0.55)')
          .polygonSideColor(() => 'rgba(0, 0, 0, 0)')
          .polygonStrokeColor(() => 'rgba(168, 196, 216, 0.45)')
          .polygonAltitude(0.001)
          .polygonsTransitionDuration(0)
      })
      .catch(() => {})

    const controls = globe.controls()
    controls.enableDamping = true
    controls.dampingFactor = 0.08
    controls.rotateSpeed = 0.45
    controls.zoomSpeed = 0.7
    controls.minDistance = 160
    controls.maxDistance = 2200

    const material = fleetMaterial(START_ALTITUDE)
    const fit = () => {
      const width = window.innerWidth
      const column = Math.min(320, width * 0.42)
      globe.width(width)
      globe.height(window.innerHeight)
      globe.globeOffset([Math.round(column * 0.42), 0])
    }
    fit()
    window.addEventListener('resize', fit)

    applyShellRef.current = (altitudeKm) => {
      const bounds = shellBounds(altitudeKm)
      material.uniforms.uShellMin.value = bounds.min
      material.uniforms.uShellMax.value = bounds.max
      const realRel = Math.min(Math.max(altitudeKm, 0) / 6371, 0.5)
      controls.minDistance = 100 * (1 + realRel * ALTITUDE_EXAGGERATION) + 22
    }
    debrisRef.current = (on) => {
      material.uniforms.uDebrisOnly.value = on ? 1 : 0
    }

    globe.renderer().domElement.addEventListener('webglcontextlost', (event: Event) => {
      event.preventDefault()
      setStatus({ state: 'error', message: 'WebGL stopped. The orbit map cannot draw without it.' })
    })

    const positionsRef = { current: null as Float32Array | null }
    const altitudesRef = { current: null as Float32Array | null }
    const kindsRef = { current: null as Float32Array | null }
    const factsRef = { current: [] as ObjectFact[] }
    let picked = -1
    let zoomed = false

    const clearPick = () => {
      picked = -1
      material.uniforms.uPick.value = -1
      setFact(null)
      setLiveKm(null)
    }
    clearPickRef.current = clearPick

    globe.onZoom((pov: { altitude: number }) => {
      const next = pov.altitude < ZOOM_HIDE_ALTITUDE
      material.uniforms.uHideOutside.value = next ? 1 : 0
      if (next === zoomed) return
      zoomed = next
      setClose(next)
      if (!next) clearPick()
    })

    let fleet: Fleet | null = null
    const canvas = globe.renderer().domElement
    let pickFrame = 0
    const onPointerMove = (event: PointerEvent) => {
      if (!zoomed) return
      const rect = canvas.getBoundingClientRect()
      const x = event.clientX - rect.left
      const y = event.clientY - rect.top
      cancelAnimationFrame(pickFrame)
      pickFrame = requestAnimationFrame(() => {
        const positions = positionsRef.current
        const pointAltitudes = altitudesRef.current
        const kinds = kindsRef.current
        if (!positions || !pointAltitudes || !kinds) return
        const index = screenNearest({
          positions,
          altitudes: pointAltitudes,
          kinds,
          camera: globe.camera(),
          width: rect.width,
          height: rect.height,
          x,
          y,
          altitudeKm: altitudeRef.current,
          debrisOnly: debrisOnlyRef.current,
          radiusPx: 28,
        })
        const next = index ?? -1
        if (next === picked) return
        picked = next
        material.uniforms.uPick.value = picked
        if (index == null) {
          setFact(null)
          setLiveKm(null)
          return
        }
        const length = Math.hypot(positions[index * 3], positions[index * 3 + 1], positions[index * 3 + 2])
        setLiveKm((length / 100 - 1) * 6371)
        setFact(factsRef.current[index] ?? null)
      })
    }
    const onPointerLeave = () => {
      cancelAnimationFrame(pickFrame)
      if (picked >= 0) clearPick()
    }
    canvas.addEventListener('pointermove', onPointerMove)
    canvas.addEventListener('pointerleave', onPointerLeave)
    const worker = new Worker(new URL('./propagate.worker.ts', import.meta.url), { type: 'module' })

    worker.onerror = () => {
      setStatus({ state: 'error', message: 'Orbit worker failed' })
    }

    worker.onmessage = (event: MessageEvent<WorkerOut>) => {
      const message = event.data
      if (message.kind === 'error') {
        setStatus({ state: 'error', message: message.message })
        return
      }
      if (message.kind === 'ready') {
        positionsRef.current = message.positions
        altitudesRef.current = message.altitudes
        kindsRef.current = message.kinds
        factsRef.current = message.facts
        fleet = createFleet(message.facts, message.altitudes, message.kinds, material, (mesh) => {
          globe.scene().add(mesh)
        })
        fleet.update(message.positions)
        setEpoch(message.epoch)
        setStatus({ state: 'ready' })
        return
      }
      if (!fleet || message.positions.length !== factsRef.current.length * 3) return
      positionsRef.current = message.positions
      fleet.update(message.positions)
      if (picked >= 0) {
        const length = Math.hypot(
          message.positions[picked * 3],
          message.positions[picked * 3 + 1],
          message.positions[picked * 3 + 2],
        )
        setLiveKm((length / 100 - 1) * 6371)
      }
    }

    return () => {
      applyShellRef.current = () => {}
      debrisRef.current = () => {}
      clearPickRef.current = () => {}
      cancelAnimationFrame(pickFrame)
      canvas.removeEventListener('pointermove', onPointerMove)
      canvas.removeEventListener('pointerleave', onPointerLeave)
      window.removeEventListener('resize', fit)
      worker.terminate()
      material.dispose()
      fleet?.dispose()
      globe._destructor()
    }
  }, [graphics])

  useEffect(() => {
    altitudeRef.current = altitude
    applyShellRef.current(altitude)
  }, [altitude])

  useEffect(() => {
    debrisOnlyRef.current = debrisOnly
    debrisRef.current(debrisOnly)
  }, [debrisOnly])

  useEffect(() => {
    if (!fact || !close) return
    const bounds = shellBounds(altitude)
    const hiddenByShell = fact.meanKm < bounds.min || fact.meanKm > bounds.max
    const hiddenByDebris = debrisOnly && fact.type !== 'debris'
    if (hiddenByShell || hiddenByDebris) clearPickRef.current()
  }, [altitude, debrisOnly, close, fact])

  useEffect(() => {
    const load = async () => {
      try {
        const response = await fetch('/leo_shells.json')
        if (!response.ok) throw new Error(`Shell counts unavailable (${response.status})`)
        const payload = (await response.json()) as { shells?: ShellRow[] }
        setShells(payload.shells ?? [])
      } catch (error) {
        setShellError(error instanceof Error ? error.message : 'Shell counts unavailable')
      }
    }
    void load()
  }, [])

  const overlay =
    graphics === 'missing' ? (
      <div className="status status-error">This view needs WebGL. The orbit map cannot draw without it.</div>
    ) : status.state === 'loading' ? (
      <div className="status">Loading orbits</div>
    ) : status.state === 'error' ? (
      <div className="status status-error">{status.message}</div>
    ) : null

  return (
    <>
      <div ref={hostRef} className="viewport" />
      <aside className="hud">
        <p className="kicker">Orbit crowding</p>
        <h1>How crowded is this altitude?</h1>
        <p className="dek">{close ? 'Point at a satellite.' : 'That shell stays bright.'}</p>
        <p className="asof">{epoch ? `Data as of ${formatEpoch(epoch)}` : 'CelesTrak GP'}</p>
        <PlacePanel
          altitude={altitude}
          shells={shells}
          shellError={shellError}
          debrisOnly={debrisOnly}
          onAltitude={setAltitude}
          onDebrisOnly={setDebrisOnly}
        />
        <ul className="legend">
          {LEGEND.map((item) => (
            <li key={item.key}>
              <span className="swatch" style={{ background: item.color }} />
              <span>{item.label}</span>
            </li>
          ))}
        </ul>
        <p className="source">CelesTrak GP</p>
      </aside>
      {close && fact && <ObjectCard fact={fact} liveKm={liveKm} />}
      {overlay}
    </>
  )
}
