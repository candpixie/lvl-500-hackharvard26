import { useEffect, useState } from 'react'
import { placeAt, type PlaceResult } from './events.ts'
import { majorityLabel, shellForAltitude, shellRange, shellTotal, type ShellRow } from './shells.ts'

function formatCount(value: number) {
  return value.toLocaleString('en-US')
}

function formatCollisions(value: number) {
  const shown = value < 1 ? value.toFixed(2) : Math.round(value).toLocaleString('en-US')
  return `${shown} expected collisions per year (first-order model)`
}

interface PlacePanelProps {
  altitude: number
  shells: ShellRow[] | null
  shellError: string | null
  debrisOnly: boolean
  onAltitude: (value: number) => void
  onDebrisOnly: (value: boolean) => void
}

export default function PlacePanel({
  altitude,
  shells,
  shellError,
  debrisOnly,
  onAltitude,
  onDebrisOnly,
}: PlacePanelProps) {
  const current = shells ? shellForAltitude(shells, altitude) : null
  const [place, setPlace] = useState<PlaceResult | null>(null)

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void placeAt(altitude)
        .then(setPlace)
        .catch(() => setPlace(null))
    }, 220)
    return () => window.clearTimeout(timer)
  }, [altitude])

  return (
    <div className="panel">
      {shellError && <p className="shell-note">{shellError}</p>}
      {!shells && !shellError && <p className="shell-note">Loading shell counts</p>}
      {current && (
        <>
          <p className="shell-count">{formatCount(shellTotal(current))}</p>
          <p className="shell-range">{shellRange(current)}</p>
          <p className="shell-majority">{majorityLabel(current)}</p>
          {place && (
            <p
              className="shell-note"
              title={`${place.note}. Expected collisions per year is a first-order model. Lifetime is approximate.`}
            >
              {Math.round(place.score)}/100, higher is safer · wreckage stays ~
              {Math.round(place.dead_sat_lifetime_years)} yr
              <br />
              {formatCollisions(place.collisions_per_year)}
              <br />
              1,000 × 4 m sats · tracked objects only, lower bound
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
      <label className="field">
        <span className="field-label">
          Altitude
          <span>{Math.round(altitude).toLocaleString('en-US')} km</span>
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
      <p className="shell-note">
        Altitude exaggerated 5.5×
        <br />
        Enlarged, not to scale
      </p>
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
