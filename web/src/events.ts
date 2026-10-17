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
