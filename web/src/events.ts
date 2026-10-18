/** Shared globe events. The agent emits these; the globe consumes them. */

export interface FocusOrbit {
  altitude_km: number
  inclination_deg: number
  count?: number
  dims_m?: number[]
  latitude_deg?: number
  longitude_deg?: number
  raan_deg?: number
  place?: string
}

export interface AskToolCall {
  name: string
  arguments?: Record<string, unknown>
  result?: unknown
}

export type UiEvent =
  | {
      type: 'focusOrbit'
      altitude_km: number
      inclination_deg: number
      count?: number
      dims_m?: number[]
      latitude_deg?: number
      longitude_deg?: number
      raan_deg?: number
      place?: string
    }
  | { type: 'selectObject'; norad: number }
  | { type: 'showApproach'; norad_1: number; norad_2: number }

export interface AskContext {
  altitude_km: number
  inclination_deg: number
  selected_norad: number | null
}

export interface AskResult {
  answer: string
  focus: FocusOrbit | null
  ui_events?: UiEvent[]
  tool_calls: AskToolCall[]
  reasoner?: 'chalk' | 'local' | 'local_fallback'
}

function missionFromArgs(args: Record<string, unknown> | undefined): Pick<FocusOrbit, 'count' | 'dims_m'> {
  if (!args) return {}
  const next: Pick<FocusOrbit, 'count' | 'dims_m'> = {}
  if (typeof args.count === 'number' && Number.isFinite(args.count) && args.count > 0) {
    next.count = Math.round(args.count)
  }
  if (Array.isArray(args.dims_m) && args.dims_m.length > 0) {
    const dims = args.dims_m.map(Number).filter((value) => Number.isFinite(value))
    if (dims.length > 0) next.dims_m = dims
  }
  return next
}

function missionFromCalls(calls: AskToolCall[] | undefined): Pick<FocusOrbit, 'count' | 'dims_m'> {
  if (!calls?.length) return {}
  const first = calls[0]
  if (first.name !== 'rank_shells' && first.name !== 'place_satellites' && first.name !== 'rank_locations') return {}
  return missionFromArgs(first.arguments)
}

function missionFromAny(calls: AskToolCall[] | undefined): Pick<FocusOrbit, 'count' | 'dims_m'> {
  if (!calls) return {}
  for (const call of calls) {
    if (call.name === 'rank_shells' || call.name === 'place_satellites' || call.name === 'rank_locations') {
      return missionFromArgs(call.arguments)
    }
  }
  return {}
}

/** Copy count/size from Ask onto focus so the HUD scores the same mission. */
export function focusWithMission(result: AskResult): FocusOrbit | null {
  if (!result.focus) return null
  let count = result.focus.count
  let dims = result.focus.dims_m
  const chalk = result.tool_calls.find((call) => call.name === 'ask_chalk')
  const body = chalk?.result
  if (body && typeof body === 'object') {
    const nested = body as { focus?: FocusOrbit; tool_calls?: AskToolCall[] }
    const fromChalk = missionFromCalls(nested.tool_calls)
    count ??= nested.focus?.count ?? fromChalk.count
    dims ??= nested.focus?.dims_m ?? fromChalk.dims_m
  }
  const fromLocal = missionFromCalls(result.tool_calls)
  const fromAny = missionFromAny(result.tool_calls)
  count ??= fromLocal.count ?? fromAny.count
  dims ??= fromLocal.dims_m ?? fromAny.dims_m
  return {
    ...result.focus,
    ...(count != null ? { count } : {}),
    ...(dims ? { dims_m: dims } : {}),
  }
}

/** Normalize ask payload into a list of UI events (supports legacy `focus` only). */
export function eventsFromAsk(result: AskResult): UiEvent[] {
  const focus = focusWithMission(result)
  const others = (result.ui_events ?? []).filter((event) => event.type !== 'focusOrbit')
  if (focus) {
    return [
      {
        type: 'focusOrbit',
        altitude_km: focus.altitude_km,
        inclination_deg: focus.inclination_deg,
        count: focus.count,
        dims_m: focus.dims_m,
        latitude_deg: focus.latitude_deg,
        longitude_deg: focus.longitude_deg,
        raan_deg: focus.raan_deg,
        place: focus.place,
      },
      ...others,
    ]
  }
  return result.ui_events?.length ? result.ui_events : []
}

export async function askGrok(question: string, context?: AskContext): Promise<AskResult> {
  const response = await fetch('/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, context }),
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
  band_inc_lo?: number
  band_inc_hi?: number
  band_tracked?: number
  band_debris?: number
}

export async function placeAt(
  altKm: number,
  incDeg = 53,
  count = 1,
  dims: number[] = [4, 2, 1],
): Promise<PlaceResult> {
  const response = await fetch('/place', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ alt_km: altKm, inc_deg: incDeg, dims_m: dims, count }),
  })
  if (!response.ok) throw new Error(`Place failed (${response.status})`)
  return response.json() as Promise<PlaceResult>
}

export interface LocationSlot {
  alt_lo: number
  alt_hi: number
  altitude_km: number
  inclination_deg: number
  inc_lo: number
  inc_hi: number
  reaches_deg: number
  latitude_deg: number
  longitude_deg: number
  raan_deg: number
  covering_lo: number
  covering_hi: number
  band_covers: boolean
  debris: number
  total: number
  satellites: number
  rocket_bodies: number
}

export interface LocationRank {
  region: { id: string; name: string; label: string; min_reach_deg: number }
  rows: LocationSlot[]
  busiest?: LocationSlot
  note: string
  caveat?: string
  answer?: string
}

export async function rankLocations(region: string, altitudeKm?: number, top = 5): Promise<LocationRank> {
  const params = new URLSearchParams({ region, top: String(top) })
  if (altitudeKm != null) params.set('alt_km', String(altitudeKm))
  const response = await fetch(`/locations?${params}`)
  const payload = (await response.json().catch(() => ({}))) as LocationRank & { detail?: string }
  if (!response.ok) {
    throw new Error(typeof payload.detail === 'string' ? payload.detail : `Locations failed (${response.status})`)
  }
  return payload
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
