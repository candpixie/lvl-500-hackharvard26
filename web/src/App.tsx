import { useEffect, useRef, useState } from 'react'
import Globe from 'globe.gl'
import {
  BufferGeometry,
  Float32BufferAttribute,
  Points,
  ShaderMaterial,
  type MeshPhongMaterial,
} from 'three'
import '@fontsource/ibm-plex-mono/400.css'
import '@fontsource/ibm-plex-mono/500.css'
import type { OrbitCounts, WorkerOut } from './orbit.ts'
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

const pointVertex = `
  attribute float aAlt;
  attribute float aKind;
  uniform float uShellMin;
  uniform float uShellMax;
  uniform float uDim;
  uniform float uHideOutside;
  uniform float uDebrisOnly;
  uniform float uExaggerate;
  uniform float uSize;
  uniform float uScale;
  varying vec3 vColor;
  varying float vAlpha;
  void main() {
    float realRel = max(length(position) / 100.0 - 1.0, 0.0);
    float capped = min(realRel, 0.5);
    vec3 placed = normalize(position) * 100.0 * (1.0 + capped * uExaggerate);
    float inside = step(uShellMin, aAlt) * step(aAlt, uShellMax);
    float debris = step(0.5, aKind);
    vColor = color;
    if (debris > 0.5) vAlpha = mix(uDebrisOnly > 0.5 ? 0.1 : 0.78, 1.0, inside);
    else vAlpha = mix(uDim, 1.0, inside);
    if (uHideOutside > 0.5) vAlpha *= inside;
    if (uDebrisOnly > 0.5) vAlpha *= debris;
    vec4 mv = modelViewMatrix * vec4(placed, 1.0);
    float outsideScale = uDebrisOnly > 0.5 ? 0.35 : 0.72;
    float boost = mix(1.0, 2.7, debris) * mix(outsideScale, 2.0, inside);
    gl_PointSize = uSize * boost * (uScale / -mv.z);
    gl_Position = projectionMatrix * mv;
  }
`

const pointFragment = `
  varying vec3 vColor;
  varying float vAlpha;
  void main() {
    if (vAlpha < 0.01) discard;
    vec2 centered = gl_PointCoord - vec2(0.5);
    float dist = dot(centered, centered);
    if (dist > 0.25) discard;
    float edge = smoothstep(0.25, 0.02, dist);
    gl_FragColor = vec4(vColor, vAlpha * edge);
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

function shellMaterial(altitudeKm: number) {
  const bounds = shellBounds(altitudeKm)
  return new ShaderMaterial({
    uniforms: {
      uShellMin: { value: bounds.min },
      uShellMax: { value: bounds.max },
      uDim: { value: 0.04 },
      uHideOutside: { value: 0 },
      uDebrisOnly: { value: 0 },
      uExaggerate: { value: ALTITUDE_EXAGGERATION },
      uSize: { value: 2.2 },
      uScale: { value: 400 },
    },
    vertexShader: pointVertex,
    fragmentShader: pointFragment,
    transparent: true,
    depthWrite: false,
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
  const [graphics] = useState<'ok' | 'missing'>(() => (webglAvailable() ? 'ok' : 'missing'))

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
    controls.minDistance = 120
    controls.maxDistance = 2200

    const material = shellMaterial(START_ALTITUDE)
    const fit = () => {
      const width = window.innerWidth
      const column = Math.min(320, width * 0.42)
      globe.width(width)
      globe.height(window.innerHeight)
      globe.globeOffset([Math.round(column * 0.42), 0])
      material.uniforms.uScale.value = globe.renderer().domElement.height * 0.5
    }
    fit()
    window.addEventListener('resize', fit)

    applyShellRef.current = (altitudeKm) => {
      const bounds = shellBounds(altitudeKm)
      material.uniforms.uShellMin.value = bounds.min
      material.uniforms.uShellMax.value = bounds.max
    }
    debrisRef.current = (on) => {
      material.uniforms.uDebrisOnly.value = on ? 1 : 0
    }

    globe.renderer().domElement.addEventListener('webglcontextlost', (event: Event) => {
      event.preventDefault()
      setStatus({ state: 'error', message: 'WebGL stopped. The orbit map cannot draw without it.' })
    })

    globe.onZoom((pov: { altitude: number }) => {
      material.uniforms.uHideOutside.value = pov.altitude < ZOOM_HIDE_ALTITUDE ? 1 : 0
    })

    let cloud: Points | null = null
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
        const geometry = new BufferGeometry()
        geometry.setAttribute('position', new Float32BufferAttribute(message.positions, 3))
        geometry.setAttribute('color', new Float32BufferAttribute(message.colors, 3))
        geometry.setAttribute('aAlt', new Float32BufferAttribute(message.altitudes, 1))
        geometry.setAttribute('aKind', new Float32BufferAttribute(message.kinds, 1))
        setEpoch(message.epoch)
        const points = new Points(geometry, material)
        points.frustumCulled = false
        globe.scene().add(points)
        cloud = points
        setStatus({ state: 'ready' })
        return
      }
      if (!cloud) return
      const attribute = cloud.geometry.getAttribute('position')
      const array = attribute.array as Float32Array
      if (message.positions.length !== array.length) return
      array.set(message.positions)
      attribute.needsUpdate = true
    }

    return () => {
      applyShellRef.current = () => {}
      debrisRef.current = () => {}
      window.removeEventListener('resize', fit)
      worker.terminate()
      material.dispose()
      cloud?.geometry.dispose()
      globe._destructor()
    }
  }, [graphics])

  useEffect(() => {
    applyShellRef.current(altitude)
  }, [altitude])

  useEffect(() => {
    debrisRef.current(debrisOnly)
  }, [debrisOnly])

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
        <p className="dek">That shell stays bright.</p>
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
      {overlay}
    </>
  )
}
