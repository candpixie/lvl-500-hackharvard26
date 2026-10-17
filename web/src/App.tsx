import { useEffect, useRef, useState } from 'react'
import Globe from 'globe.gl'
import {
  AdditiveBlending,
  BufferGeometry,
  Float32BufferAttribute,
  Line,
  LineBasicMaterial,
  Points,
  ShaderMaterial,
  Vector3,
  type MeshPhongMaterial,
} from 'three'
import '@fontsource-variable/jost'
import '@fontsource-variable/geist'
import '@fontsource-variable/geist-mono'
import AgentPanel from './AgentPanel.tsx'
import type { FocusOrbit, Neighborhood } from './events.ts'
import { imagineGrok, neighborhoodPrompt } from './events.ts'
import { createFleet, type Fleet } from './fleet.ts'
import NeighborhoodCard from './NeighborhoodCard.tsx'
import ObjectCard from './ObjectCard.tsx'
import type { ObjectFact, OrbitCounts, WorkerOut } from './orbit.ts'
import PlacePanel from './PlacePanel.tsx'
import { orbitLine, ORBIT_COLOR } from './place.ts'
import {
  exaggeratePoint,
  neighborhoodAround,
  neighborhoodInShell,
  pickNearest,
  screenNearest,
} from './pick.ts'
import { shellBounds, type ShellRow } from './shells.ts'
import { createSimActors, simCameraRig } from './simCraft.ts'
import SimOverlay from './SimOverlay.tsx'

interface CatalogPick {
  positions: Float32Array
  names: string[]
  types: string[]
  altitudes: Float32Array
}

function catalogFrom(positions: Float32Array, facts: ObjectFact[], altitudes: Float32Array): CatalogPick {
  return {
    positions,
    names: facts.map((fact) => fact.name),
    types: facts.map((fact) => fact.type),
    altitudes,
  }
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
const POINT_SIZE = 2.1

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
    vec3 key = normalize(vec3(0.32, 0.78, 0.42));
    vec3 fill = normalize(vec3(-0.55, 0.15, -0.35));
    float shade = 0.78 + 0.22 * max(dot(lit, key), 0.0) + 0.16 * max(dot(lit, fill), 0.0);
    if (debris > 0.5) vAlpha = mix(uDebrisOnly > 0.5 ? 0.1 : 0.78, 1.0, inside);
    else vAlpha = mix(uDim, 1.0, inside);
    if (uHideOutside > 0.5) vAlpha *= inside;
    if (uDebrisOnly > 0.5) vAlpha *= debris;
    vAlpha = max(vAlpha, picked);
    vec3 base = color * instanceColor;
    if (debris > 0.5) base = vec3(0.949, 0.647, 0.255);
    else base *= shade;
    vColor = base * mix(1.0, 1.25, picked);
    gl_Position = projectionMatrix * modelViewMatrix * placed;
  }
`

const pointVertex = `
  attribute float aAlt;
  attribute float aKind;
  uniform float uShellMin;
  uniform float uShellMax;
  uniform float uDim;
  uniform float uHideOutside;
  uniform float uDebrisOnly;
  uniform float uExaggerate;
  uniform float uPixelRatio;
  uniform float uSize;
  varying vec3 vColor;
  varying float vAlpha;
  void main() {
    float realRel = max(length(position) / 100.0 - 1.0, 0.0);
    float capped = min(realRel, 0.5);
    vec3 placed = normalize(position) * 100.0 * (1.0 + capped * uExaggerate);
    float inside = step(uShellMin, aAlt) * step(aAlt, uShellMax);
    float debris = step(0.5, aKind);
    vColor = mix(color, vec3(1.0, 0.62, 0.1), debris);
    if (inside > 0.5 && debris < 0.5) vColor = vec3(0.97, 0.98, 1.0);
    if (debris > 0.5) vAlpha = mix(0.85, 1.0, inside);
    else vAlpha = mix(uDim, 1.0, inside);
    if (uHideOutside > 0.5) vAlpha *= inside;
    if (uDebrisOnly > 0.5) vAlpha *= debris;
    vec4 mv = modelViewMatrix * vec4(placed, 1.0);
    float base = mix(1.5, 2.5, debris);
    gl_PointSize = base * mix(1.0, 2.1, inside) * uPixelRatio * uSize;
    gl_Position = projectionMatrix * mv;
  }
`

const pointFragment = `
  varying vec3 vColor;
  varying float vAlpha;
  void main() {
    if (vAlpha < 0.03) discard;
    float dist = length(gl_PointCoord - vec2(0.5));
    float soft = smoothstep(0.5, 0.15, dist);
    if (soft < 0.02) discard;
    gl_FragColor = vec4(vColor, vAlpha * soft);
  }
`

const craftFragment = `
  varying vec3 vColor;
  varying float vAlpha;
  void main() {
    if (vAlpha < 0.25) discard;
    gl_FragColor = vec4(vColor, 1.0);
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

function shellUniforms(altitudeKm: number) {
  const bounds = shellBounds(altitudeKm)
  return {
    uShellMin: { value: bounds.min },
    uShellMax: { value: bounds.max },
    uDim: { value: 0.07 },
    uHideOutside: { value: 0 },
    uDebrisOnly: { value: 0 },
  }
}

function pointMaterial(altitudeKm: number) {
  return new ShaderMaterial({
    uniforms: {
      ...shellUniforms(altitudeKm),
      uExaggerate: { value: ALTITUDE_EXAGGERATION },
      uPixelRatio: { value: 1 },
      uSize: { value: 1 },
    },
    vertexShader: pointVertex,
    fragmentShader: pointFragment,
    transparent: true,
    depthWrite: false,
    blending: AdditiveBlending,
    vertexColors: true,
  })
}

function fleetMaterial(altitudeKm: number) {
  return new ShaderMaterial({
    uniforms: {
      ...shellUniforms(altitudeKm),
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
  const [altitudeChosen, setAltitudeChosen] = useState(false)
  const [inclination, setInclination] = useState(53)
  const [count, setCount] = useState(1000)
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
          rendererConfig: { antialias: true, alpha: false, preserveDrawingBuffer: true, failIfMajorPerformanceCaveat: false },
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

    const dots = pointMaterial(START_ALTITUDE)
    const models = fleetMaterial(START_ALTITUDE)
    const materials = [dots, models]
    const fit = () => {
      const width = Math.max(1, Math.round(host.clientWidth || document.documentElement.clientWidth || window.innerWidth))
      const height = Math.max(
        1,
        Math.round(host.clientHeight || document.documentElement.clientHeight || window.innerHeight),
      )
      const column = Math.min(320, width * 0.42)
      globe.width(width)
      globe.height(height)
      if (!simLiveRef.current) globe.globeOffset([Math.round(column * 0.42), 0])
      dots.uniforms.uPixelRatio.value = globe.renderer().getPixelRatio()
    }
    fit()
    const refit = requestAnimationFrame(fit)
    const resizeObserver = new ResizeObserver(fit)
    resizeObserver.observe(host)
    window.addEventListener('resize', fit)
    window.visualViewport?.addEventListener('resize', fit)

    const syncShell = (altitudeKm: number) => {
      const bounds = shellBounds(altitudeKm)
      for (const material of materials) {
        material.uniforms.uShellMin.value = bounds.min
        material.uniforms.uShellMax.value = bounds.max
      }
      if (simLiveRef.current) return
      const realRel = Math.min(Math.max(altitudeKm, 0) / 6371, 0.5)
      controls.minDistance = 100 * (1 + realRel * ALTITUDE_EXAGGERATION) + 22
    }
    applyShellRef.current = syncShell
    debrisRef.current = (on) => {
      const value = on ? 1 : 0
      for (const material of materials) material.uniforms.uDebrisOnly.value = value
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

    const positionsRef = { current: null as Float32Array | null }
    const altitudesRef = { current: null as Float32Array | null }
    const kindsRef = { current: null as Float32Array | null }
    const factsRef = { current: [] as ObjectFact[] }
    let picked = -1
    let zoomed = false

    const clearPick = () => {
      picked = -1
      models.uniforms.uPick.value = -1
      setFact(null)
      setLiveKm(null)
    }
    clearPickRef.current = clearPick

    let fleet: Fleet | null = null
    let cloud: Points | null = null
    let simActors: ReturnType<typeof createSimActors> | null = null
    let simIndex = -1
    const simTarget = new Vector3()
    const nativeUpdate = controls.update.bind(controls)
    controls.update = () => {
      if (simLiveRef.current) controls.target.copy(simTarget)
      return nativeUpdate()
    }

    const showModels = (on: boolean) => {
      if (cloud) cloud.visible = !on
      fleet?.setVisible(on)
      for (const material of materials) material.uniforms.uHideOutside.value = on ? 1 : 0
      if (on && positionsRef.current) fleet?.update(positionsRef.current)
    }

    const hideForSim = () => {
      if (cloud) cloud.visible = false
      fleet?.setVisible(false)
      for (const material of materials) material.uniforms.uHideOutside.value = 1
      clearPick()
    }

    globe.onZoom((pov: { altitude: number }) => {
      if (simLiveRef.current) return
      const next = pov.altitude < ZOOM_HIDE_ALTITUDE
      if (next === zoomed) return
      zoomed = next
      showModels(next)
      setClose(next)
      if (!next) clearPick()
    })

    const canvas = globe.renderer().domElement
    let pickFrame = 0
    const onPointerMove = (event: PointerEvent) => {
      if (simLiveRef.current || !zoomed) return
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
        models.uniforms.uPick.value = picked
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

    const lockSimTarget = (positions: Float32Array, index: number) => {
      const [x, y, z] = exaggeratePoint(
        positions[index * 3],
        positions[index * 3 + 1],
        positions[index * 3 + 2],
        ALTITUDE_EXAGGERATION,
      )
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
      dots.uniforms.uSize.value = 2.4
      hideForSim()
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
      dots.uniforms.uSize.value = 1
      simActors?.dispose()
      simActors = null
      simIndex = -1
      controls.maxDistance = 2200
      controls.rotateSpeed = 0.45
      controls.target.set(0, 0, 0)
      dots.uniforms.uSize.value = POINT_SIZE
      showModels(zoomed)
      setClose(zoomed)
      syncShell(altitudeRef.current)
      fit()
      globe.pointOfView({ lat: 18, lng: 12, altitude: 1.65 }, 900)
    }

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
        const geometry = new BufferGeometry()
        geometry.setAttribute('position', new Float32BufferAttribute(message.positions, 3))
        geometry.setAttribute('color', new Float32BufferAttribute(message.colors, 3))
        geometry.setAttribute('aAlt', new Float32BufferAttribute(message.altitudes, 1))
        geometry.setAttribute('aKind', new Float32BufferAttribute(message.kinds, 1))
        const points = new Points(geometry, dots)
        points.frustumCulled = false
        globe.scene().add(points)
        cloud = points
        fleet = createFleet(message.facts, message.altitudes, message.kinds, models, (mesh) => {
          globe.scene().add(mesh)
        })
        const live = geometry.getAttribute('position').array as Float32Array
        positionsRef.current = live
        catalogRef.current = catalogFrom(live, message.facts, message.altitudes)
        setEpoch(message.epoch)
        setStatus({ state: 'ready' })
        return
      }
      if (!cloud || !fleet || message.positions.length !== factsRef.current.length * 3) return
      const positions = cloud.geometry.getAttribute('position')
      const array = positions.array as Float32Array
      array.set(message.positions)
      positions.needsUpdate = true
      positionsRef.current = array
      if (zoomed && !simLiveRef.current) fleet.update(array)
      simActors?.update(array)
      if (simLiveRef.current && simIndex >= 0) lockSimTarget(array, simIndex)
      if (picked >= 0) {
        const length = Math.hypot(
          message.positions[picked * 3],
          message.positions[picked * 3 + 1],
          message.positions[picked * 3 + 2],
        )
        setLiveKm((length / 100 - 1) * 6371)
      }
    }

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
      clearPickRef.current = () => {}
      cancelAnimationFrame(pickFrame)
      canvas.removeEventListener('pointermove', onPointerMove)
      canvas.removeEventListener('pointerleave', onPointerLeave)
      canvas.removeEventListener('pointerdown', onDown)
      canvas.removeEventListener('pointerup', onUp)
      cancelAnimationFrame(refit)
      resizeObserver.disconnect()
      flyRef.current = () => {}
      enterSimRef.current = () => {}
      exitSimRef.current = () => {}
      controls.update = nativeUpdate
      simActors?.dispose()
      catalogRef.current = null
      window.removeEventListener('resize', fit)
      window.visualViewport?.removeEventListener('resize', fit)
      worker.terminate()
      dots.dispose()
      models.dispose()
      orbitMaterial.dispose()
      orbit?.geometry.dispose()
      cloud?.geometry.dispose()
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
        <p className="kicker">Orbit Payback</p>
        <h1>How crowded is this altitude?</h1>
        <p className="dek">
          {close
            ? 'Point at a satellite. Click to visualize its neighborhood.'
            : 'Place a constellation. Click a dot to visualize its neighborhood.'}
        </p>
        <p className="asof">
          {epoch ? (
            <>
              Data as of <span className="num">{formatEpoch(epoch)}</span>
            </>
          ) : (
            'CelesTrak GP'
          )}
        </p>
        <PlacePanel
          altitude={altitude}
          altitudeChosen={altitudeChosen}
          inclination={inclination}
          count={count}
          shells={shells}
          shellError={shellError}
          debrisOnly={debrisOnly}
          onAltitude={(value) => {
            setAltitude(value)
            setAltitudeChosen(true)
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
            setAltitudeChosen(true)
            if (scene.inclination != null) setInclination(scene.inclination)
            if (scene.count != null) setCount(scene.count)
            if (scene.debrisOnly != null) setDebrisOnly(scene.debrisOnly)
            flyRef.current({
              altitude_km: scene.altitude,
              inclination_deg: scene.inclination ?? inclination,
            })
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
      {close && fact && !sim && <ObjectCard fact={fact} liveKm={liveKm} />}
      <AgentPanel
        onFocus={(focus) => {
          const next = Math.min(1950, Math.max(200, Math.round(focus.altitude_km / 10) * 10))
          setAltitude(next)
          setAltitudeChosen(true)
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
