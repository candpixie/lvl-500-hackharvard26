import type { Neighborhood } from './events.ts'

interface NeighborhoodCardProps {
  hood: Neighborhood
  status: 'loading' | 'ready' | 'error'
  image: { src: string; label: string } | null
  onClose: () => void
  onEnterSim: () => void
}

export default function NeighborhoodCard({ hood, status, image, onClose, onEnterSim }: NeighborhoodCardProps) {
  const nearby = hood.nearby
    .slice(0, 4)
    .map((obj) => obj.name.replace(/\s*\[.+$/, ''))
    .join(' · ')

  return (
    <aside className="viz-card">
      <p className="kicker">Grok Imagine</p>
      <button type="button" className="viz-close" onClick={onClose}>
        Close
      </button>
      <p className="viz-title">
        {hood.picked.name.replace(/\s*\[.+$/, '')} · {Math.round(hood.picked.alt_km)} km
      </p>
      <p className="viz-meta">
        {hood.picked.type}
        {nearby ? ` · near ${nearby}` : ''}
      </p>
      {status === 'loading' && <p className="shell-note">Drawing an illustration of this neighborhood…</p>}
      {status === 'error' && <p className="shell-note">Imagine failed. The catalog facts above still hold.</p>}
      {image && (
        <button type="button" className="imagine-open" onClick={onEnterSim}>
          <figure className="imagine">
            <img src={image.src} alt={image.label} />
            <figcaption>{image.label}</figcaption>
          </figure>
          <span>Scroll out to enter the neighborhood</span>
        </button>
      )}
      {!image && status !== 'loading' && (
        <button type="button" className="quieter" onClick={onEnterSim}>
          <strong>Enter neighborhood</strong>
          Drag to look around · scroll to move
        </button>
      )}
    </aside>
  )
}
