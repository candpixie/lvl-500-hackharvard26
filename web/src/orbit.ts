export interface OrbitCounts {
  satellite: number
  debris: number
  'rocket body': number
  unknown: number
}

export interface ObjectFact {
  name: string
  norad: number
  type: keyof OrbitCounts
  owner: string | null
  launch: string | null
  apogee: number | null
  perigee: number | null
  meanKm: number
  inclination: number | null
  radar: number | null
  constellation: string | null
  groups: string[]
  sourceGroup: string
}

export type WorkerOut =
  | {
      kind: 'ready'
      count: number
      catalog: number
      counts: OrbitCounts
      colors: Float32Array
      positions: Float32Array
      altitudes: Float32Array
      kinds: Float32Array
      epoch: string
      facts: ObjectFact[]
    }
  | { kind: 'positions'; positions: Float32Array }
  | { kind: 'error'; message: string }
