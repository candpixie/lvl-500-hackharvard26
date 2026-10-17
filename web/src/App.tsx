import { useEffect, useRef, useState } from 'react'
import Globe from 'globe.gl'
import {
  AdditiveBlending,
  BufferGeometry,
  Float32BufferAttribute,
  Line,
  LineBasicMaterial,
  Points,
  PointsMaterial,
  ShaderMaterial,
  Vector3,
  type MeshPhongMaterial,
  type PerspectiveCamera,
  type SpriteMaterial,
} from 'three'
import '@fontsource-variable/jost'
import '@fontsource-variable/geist'
import '@fontsource-variable/geist-mono'
import AgentPanel from './AgentPanel.tsx'
import type { FocusOrbit, Neighborhood, UiEvent } from './events.ts'
import { imagineGrok, neighborhoodPrompt } from './events.ts'
import { createFleet, type Fleet } from './fleet.ts'
import NeighborhoodCard from './NeighborhoodCard.tsx'
import ObjectCard from './ObjectCard.tsx'
import { RING_DRAW_CAP, type ObjectFact, type OrbitCounts, type WorkerOut } from './orbit.ts'
import PlacePanel from './PlacePanel.tsx'
import {
  GLOBE_RADIUS,
  goldStarSprite,
  groundTrackPositions,
  orbitLine,
  ORBIT_COLOR,
  raanFor,
} from './place.ts'
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
  attribute float aMatch;
  uniform float uShellMin;
  uniform float uShellMax;
  uniform float uDim;
  uniform float uHideOutside;
  uniform float uDebrisOnly;
  uniform float uMatchOn;
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
    float match = uMatchOn * aMatch;
    if (uMatchOn > 0.5) {
      vAlpha = mix(0.06, 1.0, aMatch);
      if (aMatch > 0.5) vColor = vec3(0.2, 0.9, 1.0);
    }
    vec4 mv = modelViewMatrix * vec4(placed, 1.0);
    float base = mix(1.5, 2.5, debris);
    float depthScale = clamp(265.0 / max(-mv.z, 1.0), 0.6, 1.8);
    gl_PointSize = base * depthScale * mix(1.0, 2.1, max(inside * (1.0 - uMatchOn), match)) * uPixelRatio * uSize;
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

function formatAbsDegrees(value: number) {
  const abs = Math.abs(value)
  if (Math.abs(abs - Math.round(abs)) < 0.05) return String(Math.round(abs))
  return abs.toFixed(1)
}

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
    uMatchOn: { value: 0 },
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

const DEFAULT_INCLINATION = 53

export default function App() {
  const hostRef = useRef<HTMLDivElement>(null)
  const applyShellRef = useRef<(altitudeKm: number) => void>(() => {})
  const debrisRef = useRef<(on: boolean) => void>(() => {})
  const matchRef = useRef<(groups: string[] | null) => void>(() => {})
  const flyRef = useRef<(focus: FocusOrbit, opts?: { pin?: boolean; look?: boolean }) => void>(() => {})
  const selectByNoradRef = useRef<(norad: number) => boolean>(() => false)
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
  const [inclination, setInclination] = useState(DEFAULT_INCLINATION)
  const [selectedNorad, setSelectedNorad] = useState<number | null>(null)
  const [count, setCount] = useState(1000)
  const [size, setSize] = useState(4)
  const [shells, setShells] = useState<ShellRow[] | null>(null)
  const [shellError, setShellError] = useState<string | null>(null)
  const [debrisOnly, setDebrisOnly] = useState(false)
  const [askedPlace, setAskedPlace] = useState<string | null>(null)
  const [pickRegion, setPickRegion] = useState(false)
  const [pickedLat, setPickedLat] = useState<number | null>(null)
  const [clockRate, setClockRate] = useState<1 | 60 | 600>(1)
  const [simLabel, setSimLabel] = useState('')
  const workerRef = useRef<Worker | null>(null)
  const fastRef = useRef(false)
  const controlsRef = useRef<{ autoRotate: boolean } | null>(null)
  const releaseSpinRef = useRef<() => void>(() => {})
  fastRef.current = clockRate > 1
  const [seeGroups, setSeeGroups] = useState<string[] | null>(null)
  const [epoch, setEpoch] = useState('')
  const [close, setClose] = useState(false)
  const [fact, setFact] = useState<ObjectFact | null>(null)
  const [liveKm, setLiveKm] = useState<number | null>(null)
  const [graphics] = useState<'ok' | 'missing'>(() => (webglAvailable() ? 'ok' : 'missing'))
  const altitudeRef = useRef(altitude)
  const inclinationRef = useRef(inclination)
  const debrisOnlyRef = useRef(debrisOnly)
  const pickRegionRef = useRef(pickRegion)
  const pickSurfaceRef = useRef<(lat: number, lng: number) => void>(() => {})
  const ignoreSliderUntil = useRef(0)
  const applyAskFocusRef = useRef<(focus: FocusOrbit | null) => void>(() => {})
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
    setClockRate(1)
    setSim({ phase: 'live', hood: viz.hood, image: null })
    enterSimRef.current(viz.hood.pickedIndex)
  }

  function startLiveSim() {
    if (!sim) return
    simLiveRef.current = true
    setClockRate(1)
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
      .atmosphereColor('#d7e6f4')
      .atmosphereAltitude(0.15)
      .pointOfView({ lat: 18, lng: 12, altitude: 3.4 }, 0)

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
    controls.autoRotate = false
    controls.autoRotateSpeed = 1
    controlsRef.current = controls

    const HOME = { lat: 18, lng: 12, altitude: 2.6 }
    const INTRO_MS = 2500
    const FLY_MS = 1400
    const IDLE_MS = 4_000
    const globeCenter = new Vector3()
    let userPaused = false
    let inSimView = false
    let spinHeldUntil = 0
    let idleTimer = 0
    let releaseTimer = 0
    const canSpin = () =>
      !fastRef.current && !userPaused && !inSimView && !simLiveRef.current && performance.now() >= spinHeldUntil
    const releaseSpin = () => {
      if (canSpin()) controls.autoRotate = true
    }
    releaseSpinRef.current = releaseSpin
    const holdSpin = (ms: number) => {
      controls.autoRotate = false
      spinHeldUntil = performance.now() + ms
      window.clearTimeout(releaseTimer)
      releaseTimer = window.setTimeout(releaseSpin, ms)
    }
    const holdForPointer = () => {
      userPaused = true
      controls.autoRotate = false
      window.clearTimeout(idleTimer)
      idleTimer = 0
    }
    const armResume = () => {
      window.clearTimeout(idleTimer)
      idleTimer = window.setTimeout(() => {
        idleTimer = 0
        userPaused = false
        releaseSpin()
      }, IDLE_MS)
    }
    requestAnimationFrame(() => {
      globe.pointOfView(HOME, INTRO_MS)
    })
    holdSpin(INTRO_MS)

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
    }
    applyShellRef.current = syncShell
    matchRef.current = (groups) => {
      if (!cloud) return
      const attr = cloud.geometry.getAttribute('aMatch')
      const flags = attr.array as Float32Array
      const facts = factsRef.current
      for (let i = 0; i < flags.length; i++) flags[i] = groups && facts[i]?.groups.some((g) => groups.includes(g)) ? 1 : 0
      attr.needsUpdate = true
      for (const material of materials) material.uniforms.uMatchOn.value = groups ? 1 : 0
    }
    debrisRef.current = (on) => {
      const value = on ? 1 : 0
      for (const material of materials) material.uniforms.uDebrisOnly.value = value
    }

    let orbit: Line | null = null
    let track: Line | null = null
    const orbitMaterial = new LineBasicMaterial({ color: ORBIT_COLOR, transparent: true, opacity: 0.9 })
    const trackMaterial = new LineBasicMaterial({ color: '#9EE7D2', transparent: true, opacity: 0.8 })
    const paintTrack = (altitudeKm: number, inclinationDeg: number, raanDeg: number) => {
      if (track) {
        globe.scene().remove(track)
        track.geometry.dispose()
        track = null
      }
      const geometry = new BufferGeometry()
      geometry.setAttribute(
        'position',
        new Float32BufferAttribute(groundTrackPositions(altitudeKm, inclinationDeg, raanDeg), 3),
      )
      track = new Line(geometry, trackMaterial)
      track.visible = !simLiveRef.current
      globe.scene().add(track)
    }
    const star = goldStarSprite()
    globe.scene().add(star)
    globe
      .labelsData([])
      .labelLat('lat')
      .labelLng('lng')
      .labelText('text')
      .labelSize(0.7)
      .labelDotRadius(0.4)
      .labelColor(() => '#E7F27A')
      .labelAltitude(0.012)
      .labelIncludeDot(true)
    let pinOn = false
    let aim: { lat: number; lng: number; raan: number; inc: number; place?: string } | null = null
    flyRef.current = (focus, opts = {}) => {
      if (simLiveRef.current) return
      holdSpin(FLY_MS)
      const useAim = focus.raan_deg == null && aim != null && Math.abs(aim.inc - focus.inclination_deg) < 0.6
      const raan = focus.raan_deg ?? (useAim ? aim!.raan : 28)
      paintTrack(focus.altitude_km, focus.inclination_deg, raan)
      const markerLat = focus.latitude_deg ?? (useAim ? aim!.lat : undefined)
      const { positions, marker } = orbitLine(
        focus.altitude_km,
        focus.inclination_deg,
        raan,
        ALTITUDE_EXAGGERATION,
        markerLat,
      )
      if (orbit) {
        globe.scene().remove(orbit)
        orbit.geometry.dispose()
      }
      const geometry = new BufferGeometry()
      geometry.setAttribute('position', new Float32BufferAttribute(positions, 3))
      orbit = new Line(geometry, orbitMaterial)
      globe.scene().add(orbit)
      star.position.set(marker[0], marker[1], marker[2])
      pinOn = Boolean(opts.pin)
      star.visible = pinOn
      if (focus.latitude_deg != null && focus.longitude_deg != null && focus.raan_deg != null) {
        aim = {
          lat: focus.latitude_deg,
          lng: focus.longitude_deg,
          raan: focus.raan_deg,
          inc: focus.inclination_deg,
          place: focus.place,
        }
      }
      const lookLat = focus.latitude_deg ?? (useAim ? aim?.lat : undefined)
      const lookLng = focus.longitude_deg ?? (useAim ? aim?.lng : undefined)
      const lookPlace = focus.place ?? (useAim ? aim?.place : undefined)
      if (lookLat != null && lookLng != null) {
        globe.labelsData([{ lat: lookLat, lng: lookLng, text: lookPlace ?? '' }])
      } else if (!useAim) {
        globe.labelsData([])
      }
      if (!opts.look) return
      const pov = globe.pointOfView() as { lat?: number; lng?: number; altitude?: number }
      const lat = Math.max(-55, Math.min(55, lookLat ?? 90 - focus.inclination_deg))
      globe.pointOfView(
        {
          lat,
          lng: lookLng ?? pov.lng ?? 20,
          altitude: typeof pov.altitude === 'number' ? pov.altitude : 1.65,
        },
        700,
      )
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
      setSelectedNorad(null)
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

    const ringPositions = new Float32Array(RING_DRAW_CAP * 3)
    const ringGeometry = new BufferGeometry()
    ringGeometry.setAttribute('position', new Float32BufferAttribute(ringPositions, 3))
    ringGeometry.setDrawRange(0, 0)
    const ringMaterial = new PointsMaterial({
      color: '#67e8f9',
      size: 4,
      sizeAttenuation: false,
      transparent: true,
      opacity: 0.95,
      depthWrite: false,
    })
    const ringCloud = new Points(ringGeometry, ringMaterial)
    ringCloud.frustumCulled = false
    globe.scene().add(ringCloud)

    const showModels = (on: boolean) => {
      if (cloud) cloud.visible = !on
      ringCloud.visible = !on
      fleet?.setVisible(on)
      for (const material of materials) material.uniforms.uHideOutside.value = on ? 1 : 0
      if (on && positionsRef.current) fleet?.update(positionsRef.current)
    }

    const hideForSim = () => {
      if (cloud) cloud.visible = false
      ringCloud.visible = false
      fleet?.setVisible(false)
      if (orbit) orbit.visible = false
      if (track) track.visible = false
      star.visible = false
      for (const material of materials) material.uniforms.uHideOutside.value = 1
      clearPick()
    }

    const selectByNorad = (norad: number) => {
      const index = factsRef.current.findIndex((item) => item.norad === norad)
      if (index < 0) return false
      const next = factsRef.current[index]
      const mean = next.meanKm
      if (Number.isFinite(mean) && mean > 0) {
        const shellAlt = Math.min(1950, Math.max(200, Math.round(mean / 10) * 10))
        setAltitude(shellAlt)
        altitudeRef.current = shellAlt
        syncShell(shellAlt)
      }
      if (!zoomed) {
        const pov = globe.pointOfView()
        globe.pointOfView({ lat: pov.lat, lng: pov.lng, altitude: 0.95 }, 900)
        zoomed = true
        showModels(true)
        setClose(true)
      }
      picked = index
      models.uniforms.uPick.value = index
      setFact(next)
      setSelectedNorad(norad)
      const positions = positionsRef.current
      if (positions) {
        const length = Math.hypot(positions[index * 3], positions[index * 3 + 1], positions[index * 3 + 2])
        setLiveKm((length / 100 - 1) * 6371)
      } else {
        setLiveKm(Number.isFinite(mean) ? mean : null)
      }
      return true
    }
    selectByNoradRef.current = selectByNorad

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
    const pointerOverGlobe = (event: { clientX: number; clientY: number }) => {
      const cam = globe.camera() as PerspectiveCamera
      cam.updateMatrixWorld()
      const rect = canvas.getBoundingClientRect()
      globeCenter.set(0, 0, 0).project(cam)
      const cx = rect.left + (globeCenter.x * 0.5 + 0.5) * rect.width
      const cy = rect.top + (-globeCenter.y * 0.5 + 0.5) * rect.height
      const angular = Math.asin(Math.min(1, GLOBE_RADIUS / Math.max(cam.position.length(), 1)))
      const fov = (cam.fov * Math.PI) / 180
      const screenRadius = (Math.tan(angular) / Math.tan(fov / 2)) * (rect.height / 2)
      return Math.hypot(event.clientX - cx, event.clientY - cy) <= screenRadius
    }
    const notePointer = (event: PointerEvent) => {
      const dragging = event.buttons !== 0
      if (pointerOverGlobe(event) || dragging) {
        holdForPointer()
        return
      }
      if (userPaused && idleTimer === 0) armResume()
    }
    const onWheel = (event: WheelEvent) => {
      if (pointerOverGlobe(event)) {
        holdForPointer()
        return
      }
      userPaused = true
      controls.autoRotate = false
      armResume()
    }
    let pickFrame = 0
    const onPointerMove = (event: PointerEvent) => {
      notePointer(event)
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
        const nextFact = factsRef.current[index] ?? null
        setFact(nextFact)
        setSelectedNorad(nextFact?.norad ?? null)
      })
    }
    const onPointerLeave = (event: PointerEvent) => {
      cancelAnimationFrame(pickFrame)
      if (picked >= 0) clearPick()
      if (event.buttons !== 0) return
      if (userPaused && idleTimer === 0) armResume()
    }
    canvas.addEventListener('pointermove', onPointerMove)
    canvas.addEventListener('pointerleave', onPointerLeave)
    canvas.addEventListener('wheel', onWheel, { passive: true })

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
      inSimView = true
      controls.autoRotate = false
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
      if (orbit) orbit.visible = true
      if (track) track.visible = true
      star.visible = pinOn
      syncShell(altitudeRef.current)
      fit()
      inSimView = false
      globe.pointOfView(HOME, 900)
      holdSpin(900)
    }

    const worker = new Worker(new URL('./propagate.worker.ts', import.meta.url), { type: 'module' })
    workerRef.current = worker
    let clockLabel = ''

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
        geometry.setAttribute('aMatch', new Float32BufferAttribute(new Float32Array(message.kinds.length), 1))
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
      if (message.kind !== 'positions') return
      if (!cloud || !fleet || message.positions.length !== factsRef.current.length * 3) return
      if (message.ring) {
        const shown = Math.min(RING_DRAW_CAP, message.ring.length / 3)
        const attr = ringCloud.geometry.getAttribute('position')
        ;(attr.array as Float32Array).set(message.ring.subarray(0, shown * 3))
        attr.needsUpdate = true
        ringCloud.geometry.setDrawRange(0, shown)
      }
      const label = new Date(message.simMs).toISOString().slice(0, 16).replace('T', ' ')
      if (label !== clockLabel) {
        clockLabel = label
        setSimLabel(`${label} UTC`)
      }
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
    const locate = globe as unknown as {
      toGlobeCoords(x: number, y: number): { lat: number; lng: number } | null
    }
    const readSurface = (lat: number, lng: number) => {
      if (simLiveRef.current || !pickRegionRef.current) return
      if (!Number.isFinite(lat) || !Number.isFinite(lng)) return
      pickSurfaceRef.current(lat, lng)
    }
    globe.onGlobeClick((coords) => readSurface(coords.lat, coords.lng))
    globe.onPolygonClick((_polygon, _event, coords) => readSurface(coords.lat, coords.lng))
    const onDown = (event: PointerEvent) => {
      if (pointerOverGlobe(event)) holdForPointer()
      downX = event.clientX
      downY = event.clientY
    }
    const onUp = (event: PointerEvent) => {
      if (!pointerOverGlobe(event) && userPaused && idleTimer === 0) armResume()
      if (simLiveRef.current) return
      if (Math.hypot(event.clientX - downX, event.clientY - downY) > 5) return
      if (pickRegionRef.current) {
        const rect = canvas.getBoundingClientRect()
        try {
          const coords = locate.toGlobeCoords(event.clientX - rect.left, event.clientY - rect.top)
          if (coords) readSurface(coords.lat, coords.lng)
        } catch {
          // A miss outside the Earth is not a placement.
        }
        return
      }
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
    flyRef.current({ altitude_km: altitudeRef.current, inclination_deg: inclinationRef.current })

    return () => {
      applyShellRef.current = () => {}
      debrisRef.current = () => {}
      matchRef.current = () => {}
      clearPickRef.current = () => {}
      selectByNoradRef.current = () => false
      cancelAnimationFrame(pickFrame)
      window.clearTimeout(idleTimer)
      window.clearTimeout(releaseTimer)
      canvas.removeEventListener('pointermove', onPointerMove)
      canvas.removeEventListener('pointerleave', onPointerLeave)
      canvas.removeEventListener('wheel', onWheel)
      canvas.removeEventListener('pointerdown', onDown)
      canvas.removeEventListener('pointerup', onUp)
      cancelAnimationFrame(refit)
      resizeObserver.disconnect()
      flyRef.current = () => {}
      workerRef.current = null
      controlsRef.current = null
      enterSimRef.current = () => {}
      exitSimRef.current = () => {}
      controls.update = nativeUpdate
      simActors?.dispose()
      catalogRef.current = null
      window.removeEventListener('resize', fit)
      window.visualViewport?.removeEventListener('resize', fit)
      workerRef.current = null
      controlsRef.current = null
      releaseSpinRef.current = () => {}
      worker.terminate()
      ringGeometry.dispose()
      ringMaterial.dispose()
      ringCloud.removeFromParent()
      dots.dispose()
      models.dispose()
      orbitMaterial.dispose()
      trackMaterial.dispose()
      orbit?.geometry.dispose()
      track?.geometry.dispose()
      const starMaterial = star.material as SpriteMaterial
      starMaterial.map?.dispose()
      starMaterial.dispose()
      star.removeFromParent()
      cloud?.geometry.dispose()
      fleet?.dispose()
      globe._destructor()
    }
  }, [graphics])

  useEffect(() => {
    const worker = workerRef.current
    if (!worker) return
    worker.postMessage({ kind: 'rate', rate: clockRate })
    worker.postMessage({ kind: 'ring', altKm: altitude, incDeg: inclination, count })
    const controls = controlsRef.current
    if (clockRate > 1) {
      if (controls) controls.autoRotate = false
    } else {
      releaseSpinRef.current()
    }
  }, [clockRate, altitude, inclination, count])

  const applyUiEvent = (event: UiEvent) => {
    if (event.type === 'focusOrbit') {
      applyAskFocusRef.current({
        altitude_km: event.altitude_km,
        inclination_deg: event.inclination_deg,
        count: event.count,
        dims_m: event.dims_m,
        latitude_deg: event.latitude_deg,
        longitude_deg: event.longitude_deg,
        raan_deg: event.raan_deg,
        place: event.place,
      })
      return
    }
    if (event.type === 'selectObject') {
      selectByNoradRef.current(event.norad)
      return
    }
    if (event.type === 'showApproach') {
      selectByNoradRef.current(event.norad_1)
    }
  }

  useEffect(() => {
    altitudeRef.current = altitude
    applyShellRef.current(altitude)
  }, [altitude])

  useEffect(() => {
    inclinationRef.current = inclination
  }, [inclination])

  useEffect(() => {
    pickRegionRef.current = pickRegion
    const canvas = hostRef.current?.querySelector('canvas')
    if (canvas) canvas.style.cursor = pickRegion ? 'crosshair' : ''
  }, [pickRegion])

  pickSurfaceRef.current = (lat, lng) => {
    const need = Math.abs(lat)
    const nextInc = Math.max(inclinationRef.current, Math.ceil(need - 1e-9))
    setPickedLat(lat)
    setInclination(nextInc)
    const hemi = lat >= 0 ? 'N' : 'S'
    flyRef.current(
      {
        altitude_km: altitudeRef.current,
        inclination_deg: nextInc,
        latitude_deg: lat,
        longitude_deg: lng,
        raan_deg: raanFor(nextInc, lat, lng),
        place: `${formatAbsDegrees(need)}°${hemi}`,
      },
      { pin: true, look: true },
    )
  }

  useEffect(() => {
    debrisOnlyRef.current = debrisOnly
    debrisRef.current(debrisOnly)
  }, [debrisOnly])

  useEffect(() => {
    matchRef.current(seeGroups)
  }, [seeGroups])

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

  useEffect(() => {
    applyAskFocusRef.current = (focus) => {
      if (!focus) {
        flyRef.current({ altitude_km: altitudeRef.current, inclination_deg: inclinationRef.current })
        return
      }
      const next = Math.min(1950, Math.max(200, Math.round(focus.altitude_km)))
      ignoreSliderUntil.current = Date.now() + 500
      setAltitude(next)
      setAltitudeChosen(true)
      setInclination(focus.inclination_deg)
      if (typeof focus.count === 'number' && Number.isFinite(focus.count) && focus.count > 0) {
        setCount(Math.round(focus.count))
      }
      const length = focus.dims_m?.[0]
      if (typeof length === 'number' && Number.isFinite(length)) {
        setSize(Math.min(20, Math.max(1, length)))
      }
      if (focus.place) setAskedPlace(focus.place)
      flyRef.current({ ...focus, altitude_km: next }, { pin: true, look: true })
    }
  })

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
          {pickRegion
            ? 'Click a point on Earth.'
            : close
              ? 'Point at a satellite. Not to scale.'
              : 'Set a shell, or click a dot.'}
        </p>
        <p className="asof">
          {epoch ? (
            <>
              CelesTrak GP · <span className="num">{formatEpoch(epoch)}</span>
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
          size={size}
          shells={shells}
          shellError={shellError}
          debrisOnly={debrisOnly}
          onSeeGroups={setSeeGroups}
          onAltitude={(value) => {
            if (Date.now() < ignoreSliderUntil.current) return
            setAltitude(value)
            setAltitudeChosen(true)
            flyRef.current({ altitude_km: value, inclination_deg: inclination })
          }}
          onInclination={(value) => {
            setInclination(value)
            flyRef.current({ altitude_km: altitude, inclination_deg: value })
          }}
          onCount={setCount}
          onSize={setSize}
          onDebrisOnly={setDebrisOnly}
          pickRegion={pickRegion}
          pickedLat={pickedLat}
          onPickRegion={setPickRegion}
          onScene={(scene) => {
            setAltitude(scene.altitude)
            setAltitudeChosen(true)
            if (scene.inclination != null) setInclination(scene.inclination)
            if (scene.count != null) setCount(scene.count)
            if (scene.debrisOnly != null) setDebrisOnly(scene.debrisOnly)
            const look = scene.look || scene.latitude != null || scene.focus
            flyRef.current(
              {
                altitude_km: scene.altitude,
                inclination_deg: scene.inclination ?? inclination,
                latitude_deg: scene.latitude,
                longitude_deg: scene.longitude,
                raan_deg: scene.raan,
                place: scene.place,
              },
              look ? { pin: scene.latitude != null || Boolean(scene.focus), look: true } : undefined,
            )
          }}
          askedPlace={askedPlace}
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
        <div className="legend-block">
          <ul className="legend">
            {LEGEND.map((item) => (
              <li key={item.key}>
                <span className="swatch" style={{ background: item.color }} />
                <span>{item.label}</span>
              </li>
            ))}
            <li>
              <span className="swatch swatch-constellation" />
              <span>
                your constellation
                {count > RING_DRAW_CAP ? (
                  <span className="legend-count num">
                    {' '}
                    showing {RING_DRAW_CAP.toLocaleString('en-US')} of {count.toLocaleString('en-US')}
                  </span>
                ) : null}
              </span>
            </li>
          </ul>
          <div className="clock" role="group" aria-label="Time lapse">
            {(
              [
                [1, '1×'],
                [60, '60×'],
                [600, '600×'],
              ] as const
            ).map(([rate, label]) => (
              <button
                key={rate}
                type="button"
                aria-pressed={clockRate === rate}
                onClick={() => setClockRate(rate)}
              >
                <span className="num">{label}</span>
              </button>
            ))}
            {simLabel ? <p className="clock-time num">{simLabel}</p> : null}
          </div>
        </div>
        <p className="source">Tracked objects only, lower bound</p>
      </aside>
      {close && fact && !sim && <ObjectCard fact={fact} liveKm={liveKm} />}
      <AgentPanel
        altitude={altitude}
        count={count}
        context={{
          altitude_km: altitude,
          inclination_deg: inclination,
          selected_norad: selectedNorad,
        }}
        onFocus={(focus) => applyAskFocusRef.current(focus)}
        onUiEvent={applyUiEvent}
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
