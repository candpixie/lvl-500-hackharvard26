import { useEffect, useState } from 'react'
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

interface PlacePanelProps {
  altitude: number
  inclination: number
  count: number
  shells: ShellRow[] | null
  shellError: string | null
  debrisOnly: boolean
  onAltitude: (value: number) => void
  onInclination: (value: number) => void
  onCount: (value: number) => void
  onDebrisOnly: (value: boolean) => void
  onScene: (scene: { altitude: number; count?: number; debrisOnly?: boolean }) => void
  onVisualizeShell: () => void
}

export default function PlacePanel({
  altitude,
  inclination,
  count,
  shells,
  shellError,
  debrisOnly,
  onAltitude,
  onInclination,
  onCount,
  onDebrisOnly,
  onScene,
  onVisualizeShell,
}: PlacePanelProps) {
  const current = shells ? shellForAltitude(shells, altitude) : null
  const [place, setPlace] = useState<PlaceResult | null>(null)
  const [ranks, setRanks] = useState<RankRow[]>([])
  const [miss, setMiss] = useState<NearMiss | null>(null)

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void placeAt(altitude, inclination, count)
        .then(setPlace)
        .catch(() => setPlace(null))
    }, 220)
    return () => window.clearTimeout(timer)
  }, [altitude, inclination, count])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void rankShells(count, 5)
        .then(setRanks)
        .catch(() => setRanks([]))
    }, 220)
    return () => window.clearTimeout(timer)
  }, [count])

  useEffect(() => {
    void closestMiss()
      .then(setMiss)
      .catch(() => setMiss(null))
  }, [])

  return (
    <div className="panel">
      {shellError && <p className="shell-note">{shellError}</p>}
      {!shells && !shellError && <p className="shell-note">Loading shell counts</p>}
      {current && (
        <>
          <p className="shell-count num">{formatCount(shellTotal(current))}</p>
          <p className="shell-range num">{shellRange(current)}</p>
          <p className="shell-majority">{majorityLabel(current)}</p>
          {place && (
            <p
              className="shell-note"
              title={`${place.note}. Expected collisions per year is a first-order model. Lifetime is approximate.`}
            >
              <span className="num">{Math.round(place.score)}/100</span>, higher is safer · wreckage stays
              <span className="num">{yearsLabel(place.dead_sat_lifetime_years)}</span>
              <br />
              <span className="num">{formatCollisionCount(place.collisions_per_year)}</span> expected collisions per
              year (first-order model)
              <br />
              <span className="num">{formatCount(count)} × 4 m</span> sats · tracked objects only, lower bound
            </p>
          )}
          <p
            className="source"
            title="CelesTrak SATCAT, objects with no decay date. Mean altitude is (apogee + perigee) / 2."
          >
            CelesTrak SATCAT · 50 km shells
          </p>
        </>
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

      <div className="presets count-presets">
        {COUNTS.map((item) => (
          <button
            key={item.value}
            type="button"
            aria-pressed={count === item.value}
            onClick={() => onCount(item.value)}
          >
            <span>{item.label}</span>
            <span>sats</span>
          </button>
        ))}
      </div>

      <label className="field">
        <span className="field-label">
          <span className="mark">Altitude</span>
          <span className="num">{Math.round(altitude).toLocaleString('en-US')} km</span>
        </span>
        <input
          type="range"
          min={200}
          max={1950}
          step={10}
          value={altitude}
          onChange={(event) => onAltitude(Number(event.target.value))}
        />
      </label>

      <label className="field">
        <span className="field-label">
          Inclination
          <span>{Math.round(inclination)}°</span>
        </span>
        <input
          type="range"
          min={0}
          max={180}
          step={1}
          value={inclination}
          onChange={(event) => onInclination(Number(event.target.value))}
        />
      </label>
      <p className="shell-note">
        4×2×1 m · altitude exaggerated <span className="num">5.5×</span>
        <br />
        Enlarged, not to scale
      </p>

      <button type="button" className="quieter" onClick={onVisualizeShell}>
        <strong>Visualize this shell</strong>
        Grok Imagine · illustration of nearby objects
      </button>

      {ranks.length > 0 && (
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
                  onClick={() => onAltitude(mid)}
                >
                  <span className="rank-score">{row.score}</span>
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

      {miss && (
        <button
          type="button"
          className="quieter miss-card"
          onClick={() => miss.mean_alt_km != null && onScene({ altitude: miss.mean_alt_km, debrisOnly: true })}
        >
          <strong>
            {miss.name_1.replace(/\s*\[.+$/, '')} vs {miss.name_2.replace(/\s*\[.+$/, '')}
          </strong>
          {(miss.miss_distance_km * 1000).toFixed(0)} m · {miss.relative_speed_km_s.toFixed(1)} km/s · {miss.time_utc.slice(0, 10)}
          <span>SOCRATES closest miss this week · tracked objects only</span>
        </button>
      )}

      <button
        className="debris-toggle"
        type="button"
        aria-pressed={debrisOnly}
        onClick={() => onDebrisOnly(!debrisOnly)}
      >
        {debrisOnly ? 'Debris only' : 'Show debris only'}
      </button>
    </div>
  )
}
