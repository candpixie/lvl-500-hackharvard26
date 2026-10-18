import { useEffect, useRef } from 'react'

interface Star {
  x: number
  y: number
  r: number
  phase: number
  speed: number
  color: string
}

// Small fixed-seed generator so the sky looks the same on every load.
function seeded(seed: number) {
  let t = seed
  return () => {
    t = (t + 0x6d2b79f5) | 0
    let n = Math.imul(t ^ (t >>> 15), 1 | t)
    n = (n + Math.imul(n ^ (n >>> 7), 61 | n)) ^ n
    return ((n ^ (n >>> 14)) >>> 0) / 4294967296
  }
}

export default function Stars({ className = 'home-stars' }: { className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = ref.current
    const ctx = canvas?.getContext('2d')
    if (!canvas || !ctx) return
    const rand = seeded(500)
    const stars: Star[] = Array.from({ length: 260 }, () => ({
      x: rand(),
      y: rand(),
      r: 0.4 + rand() * 1.1,
      phase: rand() * Math.PI * 2,
      speed: 0.8 + rand() * 1.8,
      color: rand() < 0.12 ? '224, 164, 76' : '201, 214, 227',
    }))
    let width = 0
    let height = 0
    let frame = 0

    const fit = () => {
      const ratio = window.devicePixelRatio || 1
      width = canvas.clientWidth
      height = canvas.clientHeight
      canvas.width = Math.round(width * ratio)
      canvas.height = Math.round(height * ratio)
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0)
    }

    const draw = (ms: number) => {
      ctx.clearRect(0, 0, width, height)
      const t = ms / 1000
      for (const star of stars) {
        const twinkle = 0.5 + 0.5 * Math.sin(t * star.speed + star.phase)
        ctx.fillStyle = `rgba(${star.color}, ${(0.1 + 0.9 * twinkle).toFixed(3)})`
        ctx.beginPath()
        ctx.arc(star.x * width, star.y * height, star.r, 0, Math.PI * 2)
        ctx.fill()
      }
      frame = requestAnimationFrame(draw)
    }

    fit()
    draw(0)
    window.addEventListener('resize', fit)
    return () => {
      cancelAnimationFrame(frame)
      window.removeEventListener('resize', fit)
    }
  }, [])

  return <canvas ref={ref} className={className} aria-hidden="true" />
}
