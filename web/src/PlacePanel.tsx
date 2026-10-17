import { useEffect, useRef, useState } from 'react'
import { closestMiss, placeAt, rankShells, type NearMiss, type PlaceResult, type RankRow } from './events.ts'
import { majorityLabel, shellForAltitude, shellRange, shellTotal, type ShellRow } from './shells.ts'

const COUNTS = [
  { label: '1', value: 1 },
  { label: '1,000', value: 1000 },
  { label: '1,000,000', value: 1_000_000 },
]

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
  if (score >= 70) return 'safer'
  if (score >= 45) return 'mixed'
  return 'crowded'
}

function formatScore(score: number) {
  return Number.isInteger(score) ? String(Math.round(score)) : score.toFixed(1)
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
  onCount: (value: number) => void
  onSize: (value: number) => void
  onDebrisOnly: (value: boolean) => void
  onScene: (scene: {
    altitude: number
    inclination?: number
    count?: number
    debrisOnly?: boolean
    focus?: boolean
  }) => void
  onVisualizeShell: () => void
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
  onCount,
  onSize,
  onDebrisOnly,
  onScene,
  onVisualizeShell,
}: PlacePanelProps) {
  const current = shells ? shellForAltitude(shells, altitude) : null
  const [place, setPlace] = useState<PlaceResult | null>(null)
  const [ranks, setRanks] = useState<RankRow[]>([])
  const [showRanks, setShowRanks] = useState(false)
  const [miss, setMiss] = useState<NearMiss | null>(null)
  const [saved, setSaved] = useState<SavedPlacement[]>([])
  const nextSaveId = useRef(1)
  const [saveName, setSaveName] = useState('')
  const [openSaveId, setOpenSaveId] = useState<number | null>(null)
  const [touched, setTouched] = useState(false)
  const dims = dimsFor(size)
  const ready = altitudeChosen || touched
  const tone = ready && place ? scoreTone(place.score) : null

  function commit() {
    setTouched(true)
  }

  useEffect(() => {
    const nextDims = dimsFor(size)
    const timer = window.setTimeout(() => {
      void placeAt(altitude, inclination, count, nextDims)
        .then(setPlace)
        .catch(() => setPlace(null))
    }, 220)
    return () => window.clearTimeout(timer)
  }, [altitude, inclination, count, size])

  useEffect(() => {
    const nextDims = dimsFor(size)
    const timer = window.setTimeout(() => {
      void rankShells(count, 5, nextDims)
        .then(setRanks)
        .catch(() => setRanks([]))
    }, 220)
    return () => window.clearTimeout(timer)
  }, [count, size])

  useEffect(() => {
    void closestMiss()
      .then(setMiss)
      .catch(() => setMiss(null))
  }, [])

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
        <div className="presets count-presets" role="group" aria-label="Satellite count">
          {COUNTS.map((item) => (
            <button
              key={item.value}
              type="button"
              aria-pressed={count === item.value}
              onClick={() => {
                if (item.value !== count) commit()
                onCount(item.value)
              }}
            >
              <span className="num">{item.label}</span>
              <span>sats</span>
            </button>
          ))}
        </div>
        {!COUNTS.some((item) => item.value === count) && (
          <p className="shell-line">
            <span className="num">{formatCount(count)}</span> sats
          </p>
        )}
      </section>

      <section className="step">
        <h2 className="step-title">
          <span className="step-num num">2</span>
          Where
        </h2>
        <button
          type="button"
          className="suggest"
          aria-expanded={showRanks}
          onClick={() => setShowRanks((open) => !open)}
        >
          Suggest safest shells
        </button>
        {showRanks && ranks.length > 0 && (
          <ol className="rank-list">
            {ranks.map((row) => {
              const mid = row.alt_lo + 25
              const active = altitude >= row.alt_lo && altitude < row.alt_hi
              return (
                <li key={row.alt_lo}>
                  <button
                    type="button"
                    className="rank-row"
                    aria-pressed={active}
                    onClick={() => {
                      commit()
                      onAltitude(mid)
                    }}
                  >
                    <span className="rank-score num">{row.score}</span>
                    <span>
                      <strong>
                        {row.alt_lo}–{row.alt_hi} km
                      </strong>
                      <span className="rank-reason">{row.reason}</span>
                    </span>
                  </button>
                </li>
              )
            })}
          </ol>
        )}

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

        <div className="presets beat-presets">
          <button type="button" onClick={() => onScene({ altitude: 900, count: 1_000_000, debrisOnly: false })}>
            <span>1M at 900 km</span>
            <span>self-crowding</span>
          </button>
          <button type="button" onClick={() => onScene({ altitude: 525, debrisOnly: false })}>
            <span>Safest 500 km</span>
            <span>clears in years</span>
          </button>
          <button type="button" onClick={() => onScene({ altitude: 825, debrisOnly: true })}>
            <span>Debris 800 km</span>
            <span>junk stays</span>
          </button>
        </div>

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
                aria-label={`${formatScore(place.score)} out of 100, ${tone}`}
              >
                <span className="impact-num num">{formatScore(place.score)}</span>
                <span className="impact-den">/100</span>
                <span className="impact-verdict">{tone}</span>
              </button>
              <div id="impact-tip" className="impact-tip" role="tooltip">
                <p>Higher is safer. Score mixes collision harm, how long wreckage stays, and how dense this shell is today.</p>
                <p>
                  Wreckage {yearsLabel(place.dead_sat_lifetime_years)} ·{' '}
                  <span className="num">{formatCollisionCount(place.collisions_per_year)}</span> collisions/yr
                  (first-order) · {formatCount(Math.round(place.objects_before))} objects already here.
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
        <section className="step">
          <h2 className="step-title">
            <span className="step-num num">4</span>
            Save & compare
          </h2>
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
        </section>
      )}

      <button type="button" className="quieter" onClick={onVisualizeShell}>
        <strong>Visualize this shell</strong>
        Illustration of nearby objects
      </button>
    </div>
  )
}
