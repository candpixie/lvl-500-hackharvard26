import { useEffect, useRef } from 'react'
import '@fontsource-variable/jost'
import '@fontsource-variable/geist'
import '@fontsource-variable/geist-mono'
import Stars from './Stars.tsx'
import './home.css'

interface HomeProps {
  onStart: () => void
  onResearch: () => void
}

// The same coastline file the globe view uses, drawn as a flat orthographic sphere.
// Each ring is stored as [lon, lat, lon, lat, ...] in radians.
type Ring = Float32Array

function ringsFrom(geometry: { type: string; coordinates: unknown }): Ring[] {
  const polygons =
    geometry.type === 'Polygon'
      ? [geometry.coordinates as number[][][]]
      : geometry.type === 'MultiPolygon'
        ? (geometry.coordinates as number[][][][])
        : []
  const rings: Ring[] = []
  for (const polygon of polygons) {
    for (const ring of polygon) {
      const out = new Float32Array(ring.length * 2)
      ring.forEach(([lon, lat], i) => {
        out[i * 2] = (lon * Math.PI) / 180
        out[i * 2 + 1] = (lat * Math.PI) / 180
      })
      rings.push(out)
    }
  }
  return rings
}

const OCEAN = '#18232f'
const LAND_FILL = 'rgba(40, 58, 74, 0.4)'
const COAST = 'rgba(168, 196, 216, 0.22)'
const TILT = (24 * Math.PI) / 180

function Earth() {
  const ref = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = ref.current
    const ctx = canvas?.getContext('2d')
    if (!canvas || !ctx) return
    let rings: Ring[] = []
    let width = 0
    let height = 0
    let frame = 0
    let last = -1000
    let alive = true

    void fetch('/land-110m.geojson')
      .then((response) => (response.ok ? response.json() : null))
      .then((land: { features?: { geometry: { type: string; coordinates: unknown } }[] } | null) => {
        if (!alive || !land?.features) return
        rings = land.features.flatMap((feature) => ringsFrom(feature.geometry))
      })
      .catch(() => {})

    const fit = () => {
      const ratio = Math.min(window.devicePixelRatio || 1, 2)
      width = canvas.clientWidth
      height = canvas.clientHeight
      canvas.width = Math.round(width * ratio)
      canvas.height = Math.round(height * ratio)
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0)
    }

    const draw = (ms: number) => {
      frame = requestAnimationFrame(draw)
      if (ms - last < 33) return
      last = ms
      ctx.clearRect(0, 0, width, height)

      const radius = Math.max(width * 0.85, height * 1.1)
      const cx = width / 2
      const cy = height - height * 0.3 + radius
      const lon0 = (ms / 1000) * 0.05 + 0.2
      const sinT = Math.sin(TILT)
      const cosT = Math.cos(TILT)

      const halo = ctx.createRadialGradient(cx, cy, radius * 0.99, cx, cy, radius * 1.09)
      halo.addColorStop(0, 'rgba(215, 230, 244, 0.11)')
      halo.addColorStop(1, 'rgba(215, 230, 244, 0)')
      ctx.fillStyle = halo
      ctx.beginPath()
      ctx.arc(cx, cy, radius * 1.09, 0, Math.PI * 2)
      ctx.fill()

      const body = ctx.createRadialGradient(cx, cy - radius * 0.55, radius * 0.1, cx, cy, radius)
      body.addColorStop(0, '#202e3e')
      body.addColorStop(0.7, OCEAN)
      body.addColorStop(1, '#080d14')
      ctx.fillStyle = body
      ctx.beginPath()
      ctx.arc(cx, cy, radius, 0, Math.PI * 2)
      ctx.fill()

      ctx.save()
      ctx.beginPath()
      ctx.arc(cx, cy, radius, 0, Math.PI * 2)
      ctx.clip()
      ctx.fillStyle = LAND_FILL
      ctx.strokeStyle = COAST
      ctx.lineWidth = 0.8
      for (const ring of rings) {
        let front = 0
        ctx.beginPath()
        for (let i = 0; i < ring.length; i += 2) {
          const phi = ring[i + 1]
          const dl = ring[i] - lon0
          const cosPhi = Math.cos(phi)
          const cosC = sinT * Math.sin(phi) + cosT * cosPhi * Math.cos(dl)
          let x = cosPhi * Math.sin(dl)
          let y = cosT * Math.sin(phi) - sinT * cosPhi * Math.cos(dl)
          if (cosC >= 0) {
            front += 1
          } else {
            const len = Math.hypot(x, y) || 1
            x /= len
            y /= len
          }
          const sx = cx + radius * x
          const sy = cy - radius * y
          if (i === 0) ctx.moveTo(sx, sy)
          else ctx.lineTo(sx, sy)
        }
        if (front === 0) continue
        ctx.closePath()
        ctx.fill()
        ctx.stroke()
      }
      ctx.restore()

      const rim = ctx.createLinearGradient(0, cy - radius, 0, cy - radius + height * 0.3)
      rim.addColorStop(0, 'rgba(215, 230, 244, 0.24)')
      rim.addColorStop(1, 'rgba(215, 230, 244, 0)')
      ctx.strokeStyle = rim
      ctx.lineWidth = 1.5
      ctx.beginPath()
      ctx.arc(cx, cy, radius, 0, Math.PI * 2)
      ctx.stroke()
    }

    fit()
    frame = requestAnimationFrame(draw)
    window.addEventListener('resize', fit)
    return () => {
      alive = false
      cancelAnimationFrame(frame)
      window.removeEventListener('resize', fit)
    }
  }, [])

  return <canvas ref={ref} className="home-earth" aria-hidden="true" />
}

export default function Home({ onStart, onResearch }: HomeProps) {
  return (
    <main className="home">
      <Stars />
      <Earth />

      <header className="home-top">
        <span className="home-mark">lvl 500</span>
        <button type="button" className="home-link" onClick={onResearch}>
          Research &amp; Sustainability
        </button>
      </header>

      <section className="home-hero">
        <h1 className="home-title">
          <span className="home-lvl">lvl</span>
          <span>500</span>
        </h1>
        <p className="home-lede">
          Orbital parking, level by level. Find an open spot before you launch.
        </p>
        <div className="home-actions">
          <button type="button" className="home-start" onClick={onStart}>
            Get started
          </button>
          <button type="button" className="home-ghost" onClick={onResearch}>
            Research &amp; Sustainability
          </button>
        </div>
      </section>

      <footer className="home-foot">
        Tracked objects only, a lower bound · CelesTrak SATCAT and SOCRATES
      </footer>
    </main>
  )
}
