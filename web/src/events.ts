/** Shared globe events. The agent emits these; the globe consumes them. */

export interface FocusOrbit {
  altitude_km: number
  inclination_deg: number
}

export interface AskResult {
  answer: string
  focus: FocusOrbit | null
  tool_calls: { name: string; arguments: Record<string, unknown> }[]
  reasoner?: 'chalk' | 'local' | 'local_fallback'
}

export async function askGrok(question: string): Promise<AskResult> {
  const response = await fetch('/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  })
  const payload = (await response.json().catch(() => ({}))) as AskResult & { detail?: string }
  if (!response.ok) {
    throw new Error(typeof payload.detail === 'string' ? payload.detail : `Ask failed (${response.status})`)
  }
  return payload
}

export async function listenGrok(blob: Blob): Promise<string> {
  const body = new FormData()
  body.append('file', blob, 'clip.webm')
  const response = await fetch('/listen', { method: 'POST', body })
  const payload = (await response.json().catch(() => ({}))) as { text?: string; detail?: string }
  if (!response.ok) {
    throw new Error(typeof payload.detail === 'string' ? payload.detail : `STT failed (${response.status})`)
  }
  if (!payload.text) throw new Error('STT returned no text')
  return payload.text
}

export interface NearbyObject {
  name: string
  type: string
  alt_km: number
}

export interface Neighborhood {
  picked: NearbyObject
  nearby: NearbyObject[]
  mix: { satellite: number; debris: number; 'rocket body': number; unknown: number }
  pickedIndex: number
  nearbyIndices: number[]
}

function mixLabel(kind: string, n: number) {
  if (kind === 'debris') return `${n} debris`
  if (kind === 'rocket body') return n === 1 ? '1 rocket body' : `${n} rocket bodies`
  if (kind === 'satellite') return n === 1 ? '1 satellite' : `${n} satellites`
  return n === 1 ? `1 ${kind}` : `${n} ${kind}`
}

export function neighborhoodPrompt(hood: Neighborhood): string {
  const mixBits = (Object.entries(hood.mix) as [string, number][])
    .filter(([, n]) => n > 0)
    .map(([kind, n]) => mixLabel(kind, n))
  const named = hood.nearby
    .slice(0, 5)
    .map((obj) => `${obj.name.replace(/\s*\[.+$/, '')} (${obj.type})`)
    .join(', ')
  return [
    `Cinematic illustration of a low Earth orbit neighborhood around ${hood.picked.name.replace(/\s*\[.+$/, '')}, a ${hood.picked.type} near ${Math.round(hood.picked.alt_km)} km.`,
    mixBits.length ? `Closest tracked objects: ${mixBits.join(', ')}.` : '',
    named ? `Named neighbors include ${named}.` : '',
    'Pale working satellites, amber tumbling debris, Earth below, dark space.',
    'No text, no diagrams, no numbers, not a photograph of real spacecraft.',
  ]
    .filter(Boolean)
    .join(' ')
}

export async function imagineGrok(prompt: string): Promise<{ url?: string; b64_json?: string; label: string }> {
  const response = await fetch('/imagine', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt }),
  })
  if (!response.ok) throw new Error(`Imagine failed (${response.status})`)
  return response.json()
}

export async function speakGrok(text: string): Promise<Blob> {
  const response = await fetch('/speak', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  })
  if (!response.ok) {
    throw new Error(`Voice failed (${response.status})`)
  }
  return response.blob()
}

export interface PlaceResult {
  score: number
  collisions_per_year: number
  dead_sat_lifetime_years: number
  objects_before: number
  note: string
}

export async function placeAt(altKm: number, incDeg = 53, count = 1000): Promise<PlaceResult> {
  const response = await fetch('/place', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ alt_km: altKm, inc_deg: incDeg, dims_m: [4, 2, 1], count }),
  })
  if (!response.ok) throw new Error(`Place failed (${response.status})`)
  return response.json() as Promise<PlaceResult>
}

export interface RankRow {
  alt_lo: number
  alt_hi: number
  score: number
  collisions_per_year: number
  dead_sat_lifetime_years: number
  objects: number
  reason: string
}

export async function rankShells(count: number, top = 5): Promise<RankRow[]> {
  const response = await fetch(`/rank?dims=4,2,1&count=${count}&top=${top}`)
  if (!response.ok) throw new Error(`Rank failed (${response.status})`)
  const payload = (await response.json()) as { rows?: RankRow[] }
  return payload.rows ?? []
}

export interface NearMiss {
  name_1: string
  name_2: string
  miss_distance_km: number
  relative_speed_km_s: number
  time_utc: string
  max_probability: number
  mean_alt_km: number | null
}

export async function closestMiss(): Promise<NearMiss | null> {
  const response = await fetch('/close_approaches?limit=1')
  if (!response.ok) throw new Error(`Close approaches failed (${response.status})`)
  const payload = (await response.json()) as { rows?: NearMiss[] }
  return payload.rows?.[0] ?? null
}
