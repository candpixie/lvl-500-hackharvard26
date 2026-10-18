import {
  BoxGeometry,
  BufferGeometry,
  Color,
  ConeGeometry,
  CylinderGeometry,
  DodecahedronGeometry,
  Float32BufferAttribute,
  InstancedBufferAttribute,
  InstancedMesh,
  Matrix4,
  OctahedronGeometry,
  ShaderMaterial,
  Vector3,
} from 'three'
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js'
import type { ObjectFact, OrbitCounts } from './orbit.ts'

const EXAGGERATION = 5.5
const SCALE: Record<keyof OrbitCounts, number> = {
  satellite: 1.45,
  debris: 0.9,
  'rocket body': 1.15,
  unknown: 0.72,
}

const TYPE_COLOR: Record<keyof OrbitCounts, string> = {
  satellite: '#C9D6E3',
  debris: '#F2A541',
  'rocket body': '#8C7AE6',
  unknown: '#8B97A6',
}

const outward = new Vector3()
const radial = new Vector3()
const east = new Vector3()
const north = new Vector3()
const panel = new Vector3()
const along = new Vector3()
const up = new Vector3(0, 1, 0)
const fallback = new Vector3(1, 0, 0)
const matrix = new Matrix4()

function paint(geometry: BufferGeometry, rgb: readonly [number, number, number]) {
  const count = geometry.getAttribute('position').count
  const colors = new Float32Array(count * 3)
  for (let index = 0; index < count; index++) {
    colors[index * 3] = rgb[0]
    colors[index * 3 + 1] = rgb[1]
    colors[index * 3 + 2] = rgb[2]
  }
  geometry.setAttribute('color', new Float32BufferAttribute(colors, 3))
  return geometry
}

function place(geometry: BufferGeometry, x: number, y: number, z: number) {
  geometry.translate(x, y, z)
  return geometry
}

function satelliteGeometry() {
  const body: readonly [number, number, number] = [0.9, 0.92, 0.95]
  const gold: readonly [number, number, number] = [0.76, 0.62, 0.34]
  const frame: readonly [number, number, number] = [0.14, 0.18, 0.26]
  const cellA: readonly [number, number, number] = [0.2, 0.38, 0.74]
  const cellB: readonly [number, number, number] = [0.42, 0.64, 0.9]
  const metal: readonly [number, number, number] = [0.78, 0.82, 0.86]
  const parts: BufferGeometry[] = []
  const add = (
    geometry: BufferGeometry,
    rgb: readonly [number, number, number],
    x = 0,
    y = 0,
    z = 0,
  ) => {
    parts.push(paint(place(geometry, x, y, z), rgb))
  }

  add(new BoxGeometry(0.42, 0.28, 0.32), body)
  add(new BoxGeometry(0.36, 0.06, 0.34), gold, 0, 0.1, 0)
  add(new BoxGeometry(0.16, 0.06, 0.08), frame, 0.29, 0, 0)
  add(new BoxGeometry(0.16, 0.06, 0.08), frame, -0.29, 0, 0)

  for (const side of [-1, 1]) {
    const wing = side * 0.98
    add(new BoxGeometry(1.12, 0.028, 0.56), frame, wing, 0, 0)
    for (let cell = 0; cell < 4; cell++) {
      const x = side * (0.62 + cell * 0.24)
      add(new BoxGeometry(0.18, 0.016, 0.44), cell % 2 === 0 ? cellA : cellB, x, 0.02, 0)
    }
  }

  add(new CylinderGeometry(0.02, 0.16, 0.045, 12), metal, 0, 0.22, 0)
  add(new CylinderGeometry(0.012, 0.012, 0.1, 6), metal, 0, 0.29, 0)
  add(new CylinderGeometry(0.018, 0.018, 0.2, 6), metal, 0, 0.14, 0.2)

  const merged = mergeGeometries(parts)
  for (const part of parts) part.dispose()
  if (!merged) throw new Error('Could not build the satellite model')
  return merged
}

function debrisGeometry() {
  const rock = paint(new DodecahedronGeometry(0.46, 0), [0.949, 0.647, 0.255])
  rock.scale(1.25, 0.72, 0.9)
  return rock
}

function rocketGeometry() {
  const body = paint(new CylinderGeometry(0.13, 0.16, 1.25, 8), [1, 1, 1])
  const nose = paint(new ConeGeometry(0.16, 0.34, 8), [0.82, 0.82, 0.88])
  nose.translate(0, 0.78, 0)
  const merged = mergeGeometries([body, nose])
  body.dispose()
  nose.dispose()
  if (!merged) throw new Error('Could not build the rocket model')
  return merged
}

function unknownGeometry() {
  return paint(new OctahedronGeometry(0.38, 0), [1, 1, 1])
}

const GEOMETRY: Record<keyof OrbitCounts, () => BufferGeometry> = {
  satellite: satelliteGeometry,
  debris: debrisGeometry,
  'rocket body': rocketGeometry,
  unknown: unknownGeometry,
}

export interface Fleet {
  update(positions: Float32Array): void
  setVisible(visible: boolean): void
  dispose(): void
}

export function createFleet(
  facts: ObjectFact[],
  altitudes: Float32Array,
  kinds: Float32Array,
  material: ShaderMaterial,
  add: (mesh: InstancedMesh) => void,
): Fleet {
  const order: (keyof OrbitCounts)[] = ['satellite', 'debris', 'rocket body', 'unknown']
  const buckets: Record<keyof OrbitCounts, number[]> = {
    satellite: [],
    debris: [],
    'rocket body': [],
    unknown: [],
  }
  for (let index = 0; index < facts.length; index++) buckets[facts[index].type].push(index)

  const slots: { mesh: InstancedMesh; index: number; scale: number }[] = new Array(facts.length)
  const meshes: InstancedMesh[] = []

  for (const type of order) {
    const members = buckets[type]
    if (members.length === 0) continue
    const geometry = GEOMETRY[type]()
    const mesh = new InstancedMesh(geometry, material, members.length)
    mesh.frustumCulled = false
    mesh.instanceColor = new InstancedBufferAttribute(new Float32Array(members.length * 3), 3)
    const tint = new Color(type === 'satellite' ? '#ffffff' : TYPE_COLOR[type])
    const alt = new Float32Array(members.length)
    const kind = new Float32Array(members.length)
    const ids = new Float32Array(members.length)
    for (let local = 0; local < members.length; local++) {
      const point = members[local]
      slots[point] = { mesh, index: local, scale: SCALE[type] }
      alt[local] = altitudes[point]
      kind[local] = kinds[point]
      ids[local] = point
      tint.toArray(mesh.instanceColor.array as Float32Array, local * 3)
    }
    geometry.setAttribute('aAlt', new InstancedBufferAttribute(alt, 1))
    geometry.setAttribute('aKind', new InstancedBufferAttribute(kind, 1))
    geometry.setAttribute('aId', new InstancedBufferAttribute(ids, 1))
    mesh.instanceColor.needsUpdate = true
    mesh.visible = false
    add(mesh)
    meshes.push(mesh)
  }

  const update = (positions: Float32Array) => {
    const dirty = new Set<InstancedMesh>()
    for (let index = 0; index < slots.length; index++) {
      const slot = slots[index]
      if (!slot) continue
      const x = positions[index * 3]
      const y = positions[index * 3 + 1]
      const z = positions[index * 3 + 2]
      const length = Math.hypot(x, y, z) || 1
      const realRel = Math.max(length / 100 - 1, 0)
      const radius = 100 * (1 + Math.min(realRel, 0.5) * EXAGGERATION)
      const placed = radius / length
      outward.set(x * placed, y * placed, z * placed)
      radial.copy(outward).multiplyScalar(1 / radius)
      east.crossVectors(radial, up)
      if (east.lengthSq() < 1e-8) east.crossVectors(radial, fallback)
      east.normalize()
      north.crossVectors(east, radial).normalize()
      const spin = (index % 24) * 0.26
      const cos = Math.cos(spin)
      const sin = Math.sin(spin)
      panel.set(east.x * cos + north.x * sin, east.y * cos + north.y * sin, east.z * cos + north.z * sin)
      along.set(north.x * cos - east.x * sin, north.y * cos - east.y * sin, north.z * cos - east.z * sin)
      const scale = slot.scale
      panel.multiplyScalar(scale)
      radial.multiplyScalar(scale)
      along.multiplyScalar(scale)
      matrix.makeBasis(panel, radial, along)
      matrix.setPosition(outward)
      slot.mesh.setMatrixAt(slot.index, matrix)
      dirty.add(slot.mesh)
    }
    for (const mesh of dirty) mesh.instanceMatrix.needsUpdate = true
  }

  return {
    update,
    setVisible(visible: boolean) {
      for (const mesh of meshes) mesh.visible = visible
    },
    dispose() {
      for (const mesh of meshes) {
        mesh.geometry.dispose()
        mesh.removeFromParent()
      }
    },
  }
}
