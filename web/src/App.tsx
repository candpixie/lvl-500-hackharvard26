import { useEffect, useRef, useState } from 'react'
import Globe from 'globe.gl'
import {
  BufferGeometry,
  Float32BufferAttribute,
  Line,
  LineBasicMaterial,
  Points,
  ShaderMaterial,
  Vector3,
  type MeshPhongMaterial,
} from 'three'
import '@fontsource/ibm-plex-mono/400.css'
import '@fontsource/ibm-plex-mono/500.css'
import AgentPanel from './AgentPanel.tsx'
import type { FocusOrbit, Neighborhood } from './events.ts'
import { imagineGrok, neighborhoodPrompt } from './events.ts'
import NeighborhoodCard from './NeighborhoodCard.tsx'
import type { OrbitCounts, WorkerOut } from './orbit.ts'
import PlacePanel from './PlacePanel.tsx'
import { orbitLine, ORBIT_COLOR } from './place.ts'
import { exaggeratePoint, neighborhoodAround, neighborhoodInShell, pickNearest } from './pick.ts'
import { shellBounds, type ShellRow } from './shells.ts'
import { createSimActors, simCameraRig } from './simCraft.ts'
import SimOverlay from './SimOverlay.tsx'

interface CatalogPick {
  positions: Float32Array
  names: string[]
  types: string[]
  altitudes: Float32Array
}

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
  const flyRef = useRef<(focus: FocusOrbit) => void>(() => {})
  const catalogRef = useRef<CatalogPick | null>(null)
  const vizGen = useRef(0)
  const startVizRef = useRef<(hood: Neighborhood) => void>(() => {})
  const enterSimRef = useRef<(index: number) => void>(() => {})
  const exitSimRef = useRef<() => void>(() => {})
  const simLiveRef = useRef(false)
  const [status, setStatus] = useState<Status>({ state: 'loading' })
  const [viz, setViz] = useState<{
    hood: Neighborhood
    status: 'loading' | 'ready' | 'error'
    image: { src: string; label: string } | null
  } | null>(null)
  const [sim, setSim] = useState<{
    phase: 'still' | 'live'
    hood: Neighborhood
    image: { src: string; label: string } | null
  } | null>(null)
  const [altitude, setAltitude] = useState(START_ALTITUDE)
  const [inclination, setInclination] = useState(53)
  const [count, setCount] = useState(1000)
  const [shells, setShells] = useState<ShellRow[] | null>(null)
  const [shellError, setShellError] = useState<string | null>(null)
  const [debrisOnly, setDebrisOnly] = useState(false)
  const [epoch, setEpoch] = useState('')
  const [graphics] = useState<'ok' | 'missing'>(() => (webglAvailable() ? 'ok' : 'missing'))

  function startViz(hood: Neighborhood) {
    const id = ++vizGen.current
    setViz({ hood, status: 'loading', image: null })
    void imagineGrok(neighborhoodPrompt(hood))
      .then((art) => {
        if (id !== vizGen.current) return
        const src = art.url ?? (art.b64_json ? `data:image/png;base64,${art.b64_json}` : '')
        setViz({ hood, status: src ? 'ready' : 'error', image: src ? { src, label: art.label } : null })
      })
      .catch(() => {
        if (id !== vizGen.current) return
        setViz({ hood, status: 'error', image: null })
      })
  }

  function openSim() {
    if (!viz) return
    if (viz.image) {
      setSim({ phase: 'still', hood: viz.hood, image: viz.image })
      return
    }
    simLiveRef.current = true
    setSim({ phase: 'live', hood: viz.hood, image: null })
    enterSimRef.current(viz.hood.pickedIndex)
  }

  function startLiveSim() {
    if (!sim) return
    simLiveRef.current = true
    setSim({ ...sim, phase: 'live' })
    setAltitude(Math.round(sim.hood.picked.alt_km / 10) * 10)
    enterSimRef.current(sim.hood.pickedIndex)
  }

  function leaveSim() {
    simLiveRef.current = false
    exitSimRef.current()
    setSim(null)
  }

  useEffect(() => {
    startVizRef.current = startViz
  })

  useEffect(() => {
    document.body.classList.toggle('is-sim', Boolean(sim))
    return () => document.body.classList.remove('is-sim')
  }, [sim])

  useEffect(() => {
    if (sim?.phase !== 'live') return
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      simLiveRef.current = false
      exitSimRef.current()
      setSim(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [sim?.phase])

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
      if (!simLiveRef.current) globe.globeOffset([Math.round(column * 0.42), 0])
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

    let orbit: Line | null = null
    const orbitMaterial = new LineBasicMaterial({ color: ORBIT_COLOR, transparent: true, opacity: 0.9 })
    flyRef.current = (focus) => {
      if (simLiveRef.current) return
      const { positions } = orbitLine(focus.altitude_km, focus.inclination_deg, 28, ALTITUDE_EXAGGERATION)
      if (orbit) {
        globe.scene().remove(orbit)
        orbit.geometry.dispose()
      }
      const geometry = new BufferGeometry()
      geometry.setAttribute('position', new Float32BufferAttribute(positions, 3))
      orbit = new Line(geometry, orbitMaterial)
      globe.scene().add(orbit)
      const lat = Math.max(-55, Math.min(55, 90 - focus.inclination_deg))
      globe.pointOfView({ lat, lng: 20, altitude: 1.45 }, 1400)
    }

    globe.renderer().domElement.addEventListener('webglcontextlost', (event: Event) => {
      event.preventDefault()
      setStatus({ state: 'error', message: 'WebGL stopped. The orbit map cannot draw without it.' })
    })

    globe.onZoom((pov: { altitude: number }) => {
      if (simLiveRef.current) return
      material.uniforms.uHideOutside.value = pov.altitude < ZOOM_HIDE_ALTITUDE ? 1 : 0
    })

    let cloud: Points | null = null
    let simActors: ReturnType<typeof createSimActors> | null = null
    let simIndex = -1
    const simTarget = new Vector3()
    const nativeUpdate = controls.update.bind(controls)
    controls.update = () => {
      if (simLiveRef.current) controls.target.copy(simTarget)
      return nativeUpdate()
    }
    const home = { minDistance: 120, maxDistance: 2200, rotateSpeed: 0.45 }
    const worker = new Worker(new URL('./propagate.worker.ts', import.meta.url), { type: 'module' })

    const lockSimTarget = (positions: Float32Array, index: number) => {
      const [x, y, z] = exaggeratePoint(positions[index * 3], positions[index * 3 + 1], positions[index * 3 + 2], ALTITUDE_EXAGGERATION)
      simTarget.set(x, y, z)
    }

    enterSimRef.current = (index: number) => {
      const catalog = catalogRef.current
      if (!catalog || index < 0) return
      simActors?.dispose()
      const spatial = neighborhoodAround(
        index,
        catalog.positions,
        catalog.names,
        catalog.types,
        catalog.altitudes,
        16,
      )
      simActors = createSimActors(
        [index, ...spatial.nearbyIndices],
        catalog.names,
        catalog.types,
        catalog.positions,
        ALTITUDE_EXAGGERATION,
      )
      globe.scene().add(simActors.root)
      simIndex = index
      lockSimTarget(catalog.positions, index)
      const { eye } = simCameraRig(simTarget.x, simTarget.y, simTarget.z)
      globe.globeOffset([0, 0])
      controls.minDistance = 12
      controls.maxDistance = 80
      controls.rotateSpeed = 0.85
      controls.enablePan = true
      material.uniforms.uSize.value = 5
      material.uniforms.uHideOutside.value = 1
      if (cloud) cloud.visible = false
      const cam = globe.camera()
      const start = cam.position.clone()
      const startTarget = controls.target.clone()
      const began = performance.now()
      const step = () => {
        const u = Math.min(1, (performance.now() - began) / 1200)
        const ease = 1 - (1 - u) ** 3
        cam.position.lerpVectors(start, eye, ease)
        controls.target.lerpVectors(startTarget, simTarget, ease)
        cam.lookAt(controls.target)
        controls.update()
        if (u < 1) requestAnimationFrame(step)
      }
      requestAnimationFrame(step)
    }

    exitSimRef.current = () => {
      simActors?.dispose()
      simActors = null
      simIndex = -1
      if (cloud) cloud.visible = true
      controls.minDistance = home.minDistance
      controls.maxDistance = home.maxDistance
      controls.rotateSpeed = home.rotateSpeed
      controls.target.set(0, 0, 0)
      material.uniforms.uSize.value = 2.2
      material.uniforms.uHideOutside.value = 0
      fit()
      globe.pointOfView({ lat: 18, lng: 12, altitude: 1.65 }, 900)
    }

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
        catalogRef.current = {
          positions: geometry.getAttribute('position').array as Float32Array,
          names: message.names,
          types: message.types,
          altitudes: message.altitudes,
        }
        setStatus({ state: 'ready' })
        return
      }
      if (!cloud) return
      const attribute = cloud.geometry.getAttribute('position')
      const array = attribute.array as Float32Array
      if (message.positions.length !== array.length) return
      array.set(message.positions)
      attribute.needsUpdate = true
      simActors?.update(array)
      if (simLiveRef.current && simIndex >= 0) lockSimTarget(array, simIndex)
    }

    const canvas = globe.renderer().domElement
    let downX = 0
    let downY = 0
    const origin = new Vector3()
    const dir = new Vector3()
    const onDown = (event: PointerEvent) => {
      downX = event.clientX
      downY = event.clientY
    }
    const onUp = (event: PointerEvent) => {
      if (simLiveRef.current) return
      if (Math.hypot(event.clientX - downX, event.clientY - downY) > 5) return
      const catalog = catalogRef.current
      if (!catalog) return
      const cam = globe.camera()
      cam.updateMatrixWorld()
      const rect = canvas.getBoundingClientRect()
      const ndcX = ((event.clientX - rect.left) / rect.width) * 2 - 1
      const ndcY = -((event.clientY - rect.top) / rect.height) * 2 + 1
      origin.setFromMatrixPosition(cam.matrixWorld)
      dir.set(ndcX, ndcY, 0.5).unproject(cam).sub(origin).normalize()
      const index = pickNearest(catalog.positions, origin, dir, catalog.names.length, ALTITUDE_EXAGGERATION)
      if (index < 0) return
      startVizRef.current(neighborhoodAround(index, catalog.positions, catalog.names, catalog.types, catalog.altitudes))
    }
    canvas.addEventListener('pointerdown', onDown)
    canvas.addEventListener('pointerup', onUp)

    return () => {
      applyShellRef.current = () => {}
      debrisRef.current = () => {}
      flyRef.current = () => {}
      enterSimRef.current = () => {}
      exitSimRef.current = () => {}
      controls.update = nativeUpdate
      simActors?.dispose()
      catalogRef.current = null
      canvas.removeEventListener('pointerdown', onDown)
      canvas.removeEventListener('pointerup', onUp)
      window.removeEventListener('resize', fit)
      worker.terminate()
      material.dispose()
      orbitMaterial.dispose()
      orbit?.geometry.dispose()
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
        <p className="kicker">Orbit Payback</p>
        <h1>How crowded is this altitude?</h1>
        <p className="dek">Place a constellation. Click a dot to visualize its neighborhood.</p>
        <p className="asof">{epoch ? `Data as of ${formatEpoch(epoch)}` : 'CelesTrak GP'}</p>
        <PlacePanel
          altitude={altitude}
          inclination={inclination}
          count={count}
          shells={shells}
          shellError={shellError}
          debrisOnly={debrisOnly}
          onAltitude={(value) => {
            setAltitude(value)
            flyRef.current({ altitude_km: value, inclination_deg: inclination })
          }}
          onInclination={(value) => {
            setInclination(value)
            flyRef.current({ altitude_km: altitude, inclination_deg: value })
          }}
          onCount={setCount}
          onDebrisOnly={setDebrisOnly}
          onScene={(scene) => {
            setAltitude(scene.altitude)
            if (scene.count != null) setCount(scene.count)
            if (scene.debrisOnly != null) setDebrisOnly(scene.debrisOnly)
            flyRef.current({ altitude_km: scene.altitude, inclination_deg: inclination })
          }}
          onVisualizeShell={() => {
            const catalog = catalogRef.current
            if (!catalog) return
            const bounds = shellBounds(altitude)
            const hood = neighborhoodInShell(
              bounds.min,
              bounds.max,
              catalog.names,
              catalog.types,
              catalog.altitudes,
              debrisOnly,
            )
            if (hood) startViz(hood)
          }}
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
      <AgentPanel
        onFocus={(focus) => {
          const next = Math.min(1950, Math.max(200, Math.round(focus.altitude_km / 10) * 10))
          setAltitude(next)
          setInclination(focus.inclination_deg)
          flyRef.current({ ...focus, altitude_km: next })
        }}
      />
      {viz && !sim && (
        <NeighborhoodCard
          hood={viz.hood}
          status={viz.status}
          image={viz.image}
          onClose={() => {
            vizGen.current += 1
            setViz(null)
          }}
          onEnterSim={openSim}
        />
      )}
      {sim && (
        <SimOverlay
          hood={sim.hood}
          image={sim.image}
          phase={sim.phase}
          onEnterLive={startLiveSim}
          onExit={leaveSim}
        />
      )}
      {overlay}
    </>
  )
}
