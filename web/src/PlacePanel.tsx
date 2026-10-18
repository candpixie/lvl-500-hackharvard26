import { useEffect, useRef, useState, type FormEvent } from 'react'
import {
  closestMiss,
  placeAt,
  rankLocations,
  type LocationRank,
  type LocationSlot,
  type NearMiss,
  type PlaceResult,
} from './events.ts'
import { bandNeighbors, sceneForKind, type BandGrid } from './launchKinds.ts'
import { majorityLabel, shellForAltitude, shellRange, shellTotal, type ShellRow } from './shells.ts'

const PLACE_CHIPS = ['Africa', 'China', 'Europe']

function formatCount(value: number) {
  return value.toLocaleString('en-US')
}

function formatCollisionCount(value: number) {
  return value < 1 ? value.toFixed(2) : Math.round(value).toLocaleString('en-US')
}

function yearsLabel(years: number) {
  if (years < 2) return 'about a year'
  return `~${Math.round(years).toLocaleString('en-US')} yr`
}

function dimsFor(size: number) {
  return [size, size / 2, size / 4]
}

function formatLength(value: number) {
  return Number.isInteger(value) ? String(value) : value.toFixed(1)
}

function scoreTone(score: number) {
  if (score >= 70) return 'quieter'
  if (score >= 45) return 'mixed'
  return 'crowded'
}

function formatBand(value: number) {
  if (Math.abs(value - Math.round(value)) < 0.05) return Math.round(value).toLocaleString('en-US')
  return value.toFixed(1)
}

function bandReason(row: LocationSlot, place: string) {
  const band = `${formatBand(row.inc_lo)}–${formatBand(row.inc_hi)}° band`
  const slice = row.band_covers
    ? band
    : `${band} · reaches ${place} from ${formatBand(row.covering_lo)}–${formatBand(row.covering_hi)}°`
  return `${slice} · ${formatBand(row.debris)} debris · ${formatBand(row.total)} tracked · reaches ${formatBand(row.reaches_deg)}°`
}

function formatScore(score: number) {
  return Number.isInteger(score) ? String(Math.round(score)) : score.toFixed(1)
}

interface LaunchKind {
  kind: string
  label: string
  objects: number
  altitude_km: { p10: number; median: number; p90: number }
  inclination_deg_median: number
  close_approaches_per_object: number
  all_leo_close_approaches_per_object: number
  caveats: string[]
}

interface SavedPlacement {
  id: number
  name: string
  altitude: number
  inclination: number
  count: number
  score: number
}

interface PlacePanelProps {
  altitude: number
  altitudeChosen: boolean
  inclination: number
  count: number
  size: number
  shells: ShellRow[] | null
  shellError: string | null
  debrisOnly: boolean
  onAltitude: (value: number) => void
  onInclination: (value: number) => void
  onSize: (value: number) => void
  onDebrisOnly: (value: boolean) => void
  onScene: (scene: {
    altitude: number
    inclination?: number
    count?: number
    debrisOnly?: boolean
    latitude?: number
    longitude?: number
    raan?: number
    place?: string
    look?: boolean
    focus?: boolean
    chosen?: boolean
  }) => void
  onVisualizeShell: () => void
  askedPlace?: string | null
  pickRegion: boolean
  pickedLat: number | null
  onPickRegion: (on: boolean) => void
}

export default function PlacePanel({
  altitude,
  altitudeChosen,
  inclination,
  count,
  size,
  shells,
  shellError,
  debrisOnly,
  onAltitude,
  onInclination,
  onSize,
  onDebrisOnly,
  onScene,
  onVisualizeShell,
  askedPlace,
  pickRegion,
  pickedLat,
  onPickRegion,
}: PlacePanelProps) {
  const current = shells ? shellForAltitude(shells, altitude) : null
  const [place, setPlace] = useState<PlaceResult | null>(null)
  const [miss, setMiss] = useState<NearMiss | null>(null)
  const [saved, setSaved] = useState<SavedPlacement[]>([])
  const [placeName, setPlaceName] = useState<string | null>(null)
  const [placeNonce, setPlaceNonce] = useState(0)
  const [placeText, setPlaceText] = useState('')
  const [slots, setSlots] = useState<LocationSlot[]>([])
  const [busiest, setBusiest] = useState<LocationSlot | null>(null)
  const [placeMeta, setPlaceMeta] = useState<LocationRank['region'] | null>(null)
  const [placeError, setPlaceError] = useState<string | null>(null)
  const appliedPlace = useRef<string | null>(null)
  const onSceneRef = useRef(onScene)
  onSceneRef.current = onScene
  const nextSaveId = useRef(1)
  const [saveName, setSaveName] = useState('')
  const [openSaveId, setOpenSaveId] = useState<number | null>(null)
  const [touched, setTouched] = useState(false)
  const [kinds, setKinds] = useState<LaunchKind[]>([])
  const [grid, setGrid] = useState<BandGrid | null>(null)
  const [kindKey, setKindKey] = useState('')
  const kind = kinds.find((row) => row.kind === kindKey) ?? null
  const neighbors = kind && grid ? bandNeighbors(grid, altitude, inclination) : null
  const dims = dimsFor(size)
  const ready = altitudeChosen || touched
  const tone = ready && place ? scoreTone(place.score) : null
  const shellLabel = current
    ? `${current.shell_km.toLocaleString('en-US')}–${(current.shell_km + 50).toLocaleString('en-US')} km`
    : null
  const rankAltitude = Math.min(2000, Math.max(300, altitude))
  const listedLo = Math.floor(rankAltitude / 50) * 50

  function commit() {
    setTouched(true)
  }

  useEffect(() => {
    const nextDims = dimsFor(size)
    const timer = window.setTimeout(() => {
      void placeAt(altitude, inclination, count, nextDims)
        .then((result) => {
          setPlace(result)
        })
        .catch(() => {
          setPlace(null)
        })
    }, 220)
    return () => window.clearTimeout(timer)
  }, [altitude, inclination, count, size])

  useEffect(() => {
    void closestMiss()
      .then(setMiss)
      .catch(() => setMiss(null))
  }, [])

  useEffect(() => {
    fetch('/launch_kinds.json')
      .then((response) => (response.ok ? response.json() : Promise.reject(new Error(String(response.status)))))
      .then((payload: { kinds?: LaunchKind[]; band_grid?: BandGrid }) => {
        setKinds(payload.kinds ?? [])
        setGrid(payload.band_grid ?? null)
      })
      .catch(() => {
        setKinds([])
        setGrid(null)
      })
  }, [])

  function chooseKind(key: string) {
    setKindKey(key)
    // a kind moves the sliders to its typical orbit; "Custom" puts the page back to its original default
    onScene({ ...sceneForKind(kinds.find((item) => item.kind === key) ?? null) })
  }

  useEffect(() => {
    const name = placeName?.trim()
    if (!name) return
    let cancel = false
    const timer = window.setTimeout(() => {
      void rankLocations(name, rankAltitude, 5)
        .then((result) => {
          if (cancel) return
          setSlots(result.rows)
          setBusiest(result.busiest ?? null)
          setPlaceMeta(result.region)
          setPlaceError(null)
          const top = result.rows[0]
          if (top && appliedPlace.current !== result.region.id) {
            appliedPlace.current = result.region.id
            onSceneRef.current({
              altitude,
              inclination: top.inclination_deg,
              latitude: top.latitude_deg,
              longitude: top.longitude_deg,
              raan: top.raan_deg,
              place: result.region.label,
            })
          }
        })
        .catch((err: unknown) => {
          if (cancel) return
          setSlots([])
          setBusiest(null)
          setPlaceMeta(null)
          setPlaceError(err instanceof Error ? err.message : 'Could not rank that place')
        })
    }, 220)
    return () => {
      cancel = true
      window.clearTimeout(timer)
    }
  }, [placeName, placeNonce, altitude])

  useEffect(() => {
    if (!askedPlace || askedPlace === placeName) return
    askPlace(askedPlace)
    // askPlace is stable enough for a place name arriving from Ask.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [askedPlace])

  function askPlace(name: string) {
    const next = name.trim()
    if (!next) return
    appliedPlace.current = null
    setPlaceText(next)
    setPlaceName(next)
    setPlaceNonce((value) => value + 1)
    commit()
  }

  function submitPlace(event: FormEvent) {
    event.preventDefault()
    askPlace(placeText)
  }

  function applySlot(row: LocationSlot) {
    commit()
    onScene({
      altitude,
      inclination: row.inclination_deg,
      latitude: row.latitude_deg,
      longitude: row.longitude_deg,
      raan: row.raan_deg,
      place: placeMeta?.label,
    })
  }

  function chooseSize(value: string) {
    const next = Number(value)
    if (!Number.isFinite(next)) return
    onSize(Math.min(20, Math.max(1, next)))
    commit()
  }

  function savePlacement() {
    if (!place) return
    const id = nextSaveId.current++
    setSaved((rows) => [
      ...rows,
      {
        id,
        name: saveName.trim() || `Placement ${id}`,
        altitude: Math.round(altitude),
        inclination: Math.round(inclination),
        count,
        score: Math.round(place.score),
      },
    ])
    setSaveName('')
    setOpenSaveId(id)
  }

  return (
    <div className="panel">
      <section className="step">
        <h2 className="step-title">
          <span className="step-num num">1</span>
          Your mission
        </h2>
        {kinds.length > 0 && (
          <label className="field">
            <span className="field-label">What are you launching?</span>
            <select
              className="step-number kind-select"
              value={kindKey}
              aria-label="Type of object"
              onChange={(event) => chooseKind(event.target.value)}
            >
              <option value="">Custom</option>
              {kinds.map((row) => (
                <option key={row.kind} value={row.kind}>
                  {row.label}
                </option>
              ))}
            </select>
          </label>
        )}
        {kind && (
          <p className="shell-line kind-line" title={kind.caveats.join(' ')}>
            Existing {kind.label}s ({kind.objects.toLocaleString('en-US')}): typically{' '}
            <span className="num">
              {kind.altitude_km.p10}–{kind.altitude_km.p90} km
            </span>{' '}
            at <span className="num">{Math.round(kind.inclination_deg_median)}°</span>. About{' '}
            <span className="num">{kind.close_approaches_per_object}</span> predicted close approaches each this
            week, against <span className="num">{kind.all_leo_close_approaches_per_object}</span> for the average
            object in low orbit. Observed for existing objects, not a forecast for yours. SOCRATES, one week.
          </p>
        )}
        {kind && neighbors && (
          <p className="shell-line kind-line" title={grid?.note}>
            In this orbit's band ({neighbors.incLo}–{neighbors.incHi}°): about{' '}
            <span className="num">{formatCount(neighbors.inBand)}</span> of the{' '}
            <span className="num">{formatCount(neighbors.wholeShell)}</span> tracked objects in the{' '}
            {neighbors.shellLo.toLocaleString('en-US')}–{neighbors.shellHi.toLocaleString('en-US')} km shell
            {neighbors.inBand > 0 ? (
              <>
                , <span className="num">{formatCount(neighbors.debrisInBand)}</span> of them debris
              </>
            ) : (
              <>. None are tracked there, which is not the same as empty: small debris is not tracked</>
            )}
            . Tracked objects only, a lower bound.
          </p>
        )}
        <label className="field">
          <span className="field-label">
            Size
            <span className="num">
              {formatLength(dims[0])}×{formatLength(dims[1])}×{formatLength(dims[2])} m
            </span>
          </span>
          <input
            className="step-number"
            type="number"
            min={1}
            max={20}
            step={1}
            value={size}
            aria-label="Satellite size in meters"
            onChange={(event) => chooseSize(event.target.value)}
          />
        </label>
      </section>

      <section className="step">
        <h2 className="step-title">
          <span className="step-num num">2</span>
          Where
        </h2>
        <label className="field">
          <span className="field-label">
            <span className="mark">Altitude</span>
            <span className="num">{Math.round(altitude).toLocaleString('en-US')} km</span>
          </span>
          <input
            type="range"
            min={200}
            max={1950}
            step={5}
            value={altitude}
            onChange={(event) => {
              commit()
              onAltitude(Number(event.target.value))
            }}
          />
        </label>

        <form className="place-query" onSubmit={submitPlace}>
          <span className="field-label">
            Over a place
            <span>at this altitude</span>
          </span>
          <div className="presets place-presets" role="group" aria-label="Place over">
            {PLACE_CHIPS.map((name) => (
              <button
                key={name}
                type="button"
                aria-pressed={placeMeta?.label === name}
                onClick={() => askPlace(name)}
              >
                {name}
              </button>
            ))}
          </div>
          <label className="field">
            <span className="field-label">Or another place</span>
            <input
              className="step-number place-input"
              type="text"
              value={placeText}
              placeholder="India, Japan, Brazil…"
              aria-label="Place to fly over"
              onChange={(event) => setPlaceText(event.target.value)}
            />
          </label>
          <button type="submit" className="suggest">
            Rank orbits that cross it
          </button>
        </form>
        {placeError && <p className="shell-note">{placeError}</p>}
        {placeMeta && (
          <p className="shell-line">
            Needs <span className="num">{formatBand(placeMeta.min_reach_deg)}°</span> of latitude to cross{' '}
            {placeMeta.name}. Quietest debris first.
          </p>
        )}
        {slots.length > 0 && (
          <ol className="rank-list">
            {slots.map((row) => {
              const active = Math.abs(inclination - row.inclination_deg) < 0.6
              return (
                <li key={`${row.alt_lo}-${row.inc_lo}`}>
                  <button
                    type="button"
                    className="rank-row"
                    aria-pressed={active}
                    onClick={() => applySlot(row)}
                  >
                    <span className="rank-score num">{formatBand(row.debris)}</span>
                    <span>
                      <strong>{formatBand(row.inclination_deg)}°</strong>
                      <span className="rank-reason">{bandReason(row, placeMeta?.name ?? 'this place')}</span>
                    </span>
                  </button>
                </li>
              )
            })}
          </ol>
        )}
        {slots.length > 0 && busiest && slots[0] && busiest.inc_lo !== slots[0].inc_lo && (
          <p className="shell-line">
            Busiest covering band in this shell:{' '}
            <span className="num">
              {formatBand(busiest.inc_lo)}–{formatBand(busiest.inc_hi)}°
            </span>
            , {formatBand(busiest.debris)} tracked debris.
          </p>
        )}
        {slots.length > 0 && (
          <p className="shell-note">Counts are the whole 10° band. Tracked objects only, a lower bound.</p>
        )}
        {altitude < 300 && slots.length > 0 && (
          <p className="shell-note">
            The catalog grid starts at 300 km, so this list is the {listedLo.toLocaleString('en-US')}–
            {(listedLo + 50).toLocaleString('en-US')} km shell. The globe is at{' '}
            {Math.round(altitude).toLocaleString('en-US')} km.
          </p>
        )}

        <button
          className="debris-toggle"
          type="button"
          aria-pressed={pickRegion}
          onClick={() => onPickRegion(!pickRegion)}
        >
          {pickRegion ? 'Picking a region' : 'Pick a region'}
        </button>
        {pickRegion && pickedLat == null && <p className="shell-note">Click a point on the globe.</p>}
        {pickedLat != null && (
          <p className="shell-line">
            To pass over this latitude you need an inclination of at least{' '}
            <span className="num">{formatBand(Math.abs(pickedLat))}°</span>.
          </p>
        )}
        <p className="shell-note">A low orbit passes over a place. It does not stay there.</p>

        <label className="field">
          <span className="field-label">
            Inclination
            <span className="num">{Math.round(inclination)}°</span>
          </span>
          <input
            type="range"
            min={0}
            max={180}
            step={1}
            value={inclination}
            onChange={(event) => {
              commit()
              onInclination(Number(event.target.value))
            }}
          />
        </label>

        {shellError && <p className="shell-note">{shellError}</p>}
        {!shells && !shellError && <p className="shell-note">Loading shell counts</p>}
        {current && (
          <p
            className="shell-line"
            title="CelesTrak SATCAT. Mean altitude is (apogee + perigee) / 2. Tracked objects only, lower bound."
          >
            <span className="num">{formatCount(shellTotal(current))}</span> tracked ·{' '}
            <span className="num">{shellRange(current)}</span> · {majorityLabel(current).toLowerCase()}
          </p>
        )}

        <details className="fold">
          <summary>Examples</summary>
          <div className="presets beat-presets">
            <button type="button" onClick={() => onScene({ altitude: 525, debrisOnly: false })}>
              Quiet 500 km
            </button>
            <button type="button" onClick={() => onScene({ altitude: 825, debrisOnly: true })}>
              Debris at 800 km
            </button>
          </div>
        </details>

        <button
          className="debris-toggle"
          type="button"
          aria-pressed={debrisOnly}
          onClick={() => onDebrisOnly(!debrisOnly)}
        >
          {debrisOnly ? 'Debris only' : 'Show debris only'}
        </button>
      </section>

      <section className="step step-impact">
        <h2 className="step-title">
          <span className="step-num num">3</span>
          Impact
        </h2>
        <div className="impact-score">
          {ready && place ? (
            <>
              <button
                type="button"
                className="impact-rating"
                data-tone={tone}
                aria-describedby="impact-tip"
                aria-label={
                  place.band_inc_lo != null && place.band_inc_hi != null
                    ? `${formatScore(place.score)} out of 100 for the ${formatBand(place.band_inc_lo)}–${formatBand(place.band_inc_hi)}° band`
                    : `${formatScore(place.score)} out of 100, ${tone}`
                }
              >
                <span className="impact-num num">{formatScore(place.score)}</span>
                <span className="impact-den">/100</span>
                <span className="impact-verdict">
                  {place.band_inc_lo != null && place.band_inc_hi != null
                    ? `${formatBand(place.band_inc_lo)}–${formatBand(place.band_inc_hi)}°`
                    : tone}
                </span>
              </button>
              {place.band_inc_lo != null && (
                <p className="shell-line">
                  This {formatBand(place.band_inc_lo)}–{formatBand(place.band_inc_hi ?? place.band_inc_lo)}° band
                  {shellLabel ? ` in the ${shellLabel} shell` : ''}. More tracked satellites or debris in the band
                  lowers the score.
                </p>
              )}
              <div id="impact-tip" className="impact-tip" role="tooltip">
                <p>
                  The altitude shell sets how long wreckage stays and how dense the shell is. Tracked objects in this
                  10° inclination band move the number up or down. A band with nothing tracked is not empty space.
                </p>
                <p>
                  Wreckage {yearsLabel(place.dead_sat_lifetime_years)} ·{' '}
                  <span className="num">{formatCollisionCount(place.collisions_per_year)}</span> collisions/yr
                  (first-order, whole shell)
                  {place.band_tracked != null && (
                    <>
                      {' '}
                      · <span className="num">{formatBand(place.band_tracked)}</span> tracked in this band
                    </>
                  )}
                  {place.band_debris != null && (
                    <>
                      {' '}
                      · <span className="num">{formatBand(place.band_debris)}</span> debris
                    </>
                  )}
                  {' '}
                  · {formatCount(Math.round(place.objects_before))} in the whole shell.
                </p>
                <p>Tracked objects only, lower bound.</p>
              </div>
            </>
          ) : (
            <p className="impact-rating impact-empty" aria-label="No score yet">
              <span className="impact-num num">–</span>
              <span className="impact-den">/100</span>
            </p>
          )}
        </div>
        {ready && miss && (
          <button
            type="button"
            className="quieter miss-card"
            onClick={() => miss.mean_alt_km != null && onScene({ altitude: miss.mean_alt_km, debrisOnly: true })}
          >
            <strong>
              {miss.name_1.replace(/\s*\[.+$/, '')} vs {miss.name_2.replace(/\s*\[.+$/, '')}
            </strong>
            {(miss.miss_distance_km * 1000).toFixed(0)} m · {miss.relative_speed_km_s.toFixed(1)} km/s ·{' '}
            {miss.time_utc.slice(0, 10)}
            <span>Closest miss this week · SOCRATES</span>
          </button>
        )}
      </section>

      {ready && (
        <details className="fold">
          <summary>Save & compare</summary>
          <input
            type="text"
            className="save-name"
            value={saveName}
            maxLength={40}
            placeholder="Name this placement"
            aria-label="Placement name"
            onChange={(e) => setSaveName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') savePlacement()
            }}
          />
          <button type="button" className="suggest" disabled={!place} onClick={savePlacement}>
            Save
          </button>
          {saved.length > 0 && (
            <ol className="saved-list">
              {saved.map((row) => {
                const open = openSaveId === row.id
                return (
                  <li key={row.id} className="saved-item">
                    <button
                      type="button"
                      className="saved-head"
                      aria-expanded={open}
                      onClick={() => setOpenSaveId(open ? null : row.id)}
                    >
                      <span className="saved-name">{row.name}</span>
                      <span className="num">{row.score}/100</span>
                      <span className="saved-caret" aria-hidden="true">
                        {open ? '▾' : '▸'}
                      </span>
                    </button>
                    <button
                      type="button"
                      className="saved-remove"
                      aria-label={`Remove ${row.name}`}
                      onClick={() => {
                        setSaved((rows) => rows.filter((item) => item.id !== row.id))
                        if (open) setOpenSaveId(null)
                      }}
                    >
                      ×
                    </button>
                    {open && (
                      <div className="saved-details">
                        <dl>
                          <dt>Altitude</dt>
                          <dd className="num">{row.altitude.toLocaleString('en-US')} km</dd>
                          <dt>Inclination</dt>
                          <dd className="num">{row.inclination}°</dd>
                          <dt>Satellites</dt>
                          <dd className="num">{formatCount(row.count)}</dd>
                          <dt>Score</dt>
                          <dd className="num">{row.score}/100</dd>
                        </dl>
                        <button
                          type="button"
                          className="saved-view"
                          onClick={() =>
                            onScene({
                              altitude: row.altitude,
                              inclination: row.inclination,
                              count: row.count,
                              focus: true,
                            })
                          }
                        >
                          Show on globe
                        </button>
                      </div>
                    )}
                  </li>
                )
              })}
            </ol>
          )}
        </details>
      )}

      <button type="button" className="quieter" onClick={onVisualizeShell}>
        <strong>Visualize this shell</strong>
        Illustration of nearby objects
      </button>
    </div>
  )
}
