export interface OrbitCounts {
  satellite: number
  debris: number
  'rocket body': number
  unknown: number
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
      names: string[]
      types: string[]
      epoch: string
    }
  | { kind: 'positions'; positions: Float32Array }
  | { kind: 'error'; message: string }
