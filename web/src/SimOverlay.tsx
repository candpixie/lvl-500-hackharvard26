import { useState } from 'react'
import type { Neighborhood } from './events.ts'

interface SimOverlayProps {
  hood: Neighborhood
  image: { src: string; label: string } | null
  phase: 'still' | 'live'
  onEnterLive: () => void
  onExit: () => void
}

function shortName(name: string) {
  return name.replace(/\s*\[.+$/, '')
}

export default function SimOverlay({ hood, image, phase, onEnterLive, onExit }: SimOverlayProps) {
  const [leaving, setLeaving] = useState(false)

  function enter() {
    if (leaving) return
    setLeaving(true)
    window.setTimeout(onEnterLive, 480)
  }

  if (phase === 'still' && image) {
    return (
      <div
        className={`sim-still${leaving ? ' is-leaving' : ''}`}
        onWheel={(event) => {
          if (event.deltaY > 8) enter()
        }}
      >
        <img src={image.src} alt={image.label} />
        <p className="sim-hint">Scroll out to enter the neighborhood · drag to look around once you are in</p>
        <button type="button" className="sim-enter" onClick={enter}>
          Enter neighborhood
        </button>
      </div>
    )
  }

  return (
    <div className="sim-hud">
      <p className="kicker">Neighborhood sim</p>
      <p className="sim-title">{shortName(hood.picked.name)}</p>
      <p className="sim-meta">
        {hood.picked.type} · {Math.round(hood.picked.alt_km)} km · drag to look · scroll to move
      </p>
      <ul className="sim-near">
        {hood.nearby.slice(0, 6).map((obj) => (
          <li key={`${obj.name}-${obj.alt_km}`}>
            <span className={`sim-dot sim-dot-${obj.type === 'rocket body' ? 'rocket' : obj.type}`} />
            {shortName(obj.name)}
          </li>
        ))}
      </ul>
      <button type="button" className="sim-exit" onClick={onExit}>
        Back to globe
      </button>
    </div>
  )
}
