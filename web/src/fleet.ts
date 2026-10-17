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

function satelliteGeometry() {
  const bus = paint(new BoxGeometry(0.5, 0.34, 0.36), [0.93, 0.95, 0.98])
  const panel = new BoxGeometry(0.98, 0.04, 0.56)
  paint(panel, [0.35, 0.58, 0.92])
  const left = panel.clone()
  left.translate(-0.76, 0, 0)
  const right = panel.clone()
  right.translate(0.76, 0, 0)
  const dish = paint(new CylinderGeometry(0.04, 0.13, 0.07, 8), [0.62, 0.66, 0.7])
  dish.translate(0, 0.2, 0)
  const merged = mergeGeometries([bus, left, right, dish])
  bus.dispose()
  panel.dispose()
  left.dispose()
  right.dispose()
  dish.dispose()
  if (!merged) throw new Error('Could not build the satellite model')
  return merged
}

function debrisGeometry() {
  const rock = paint(new DodecahedronGeometry(0.46, 0), [1, 1, 1])
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
    dispose() {
      for (const mesh of meshes) {
        mesh.geometry.dispose()
        mesh.removeFromParent()
      }
    },
  }
}
