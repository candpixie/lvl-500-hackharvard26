import { useEffect, useState } from 'react'
import { placeAt, type PlaceResult } from './events.ts'
import { majorityLabel, shellForAltitude, shellRange, shellTotal, type ShellRow } from './shells.ts'

function formatCount(value: number) {
  return value.toLocaleString('en-US')
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
              Score {place.score}/100 · wreckage stays ~{Math.round(place.dead_sat_lifetime_years)} yr
              <br />
              {place.collisions_per_year < 1
                ? `${place.collisions_per_year.toFixed(2)} collisions/yr`
                : `${Math.round(place.collisions_per_year).toLocaleString('en-US')} collisions/yr`}
              {' · 1,000 × 4 m sats · tracked objects only, lower bound'}
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
      <p className="shell-note">Altitude exaggerated 5.5×</p>
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
