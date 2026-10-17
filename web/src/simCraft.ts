import {
  BoxGeometry,
  Color,
  ConeGeometry,
  CylinderGeometry,
  DodecahedronGeometry,
  Group,
  Mesh,
  MeshPhongMaterial,
  Vector3,
} from 'three'
import { exaggeratePoint } from './pick.ts'

const SCALE = 1.7
const outward = new Vector3()
const radial = new Vector3()
const up = new Vector3(0, 1, 0)

function paint(color: string) {
  return new MeshPhongMaterial({
    color: new Color(color),
    emissive: new Color(color),
    emissiveIntensity: 0.55,
    shininess: 18,
  })
}

function satelliteMesh() {
  const mat = paint('#d7e2ee')
  const panel = paint('#4d7ecc')
  const group = new Group()
  const bus = new Mesh(new BoxGeometry(0.55, 0.36, 0.4), mat)
  const left = new Mesh(new BoxGeometry(0.95, 0.08, 0.52), panel)
  left.position.x = -0.78
  const right = new Mesh(new BoxGeometry(0.95, 0.08, 0.52), panel)
  right.position.x = 0.78
  group.add(bus, left, right)
  return group
}

function debrisMesh() {
  const rock = new Mesh(new DodecahedronGeometry(0.48, 0), paint('#F2A541'))
  rock.scale.set(1.3, 0.72, 0.95)
  const group = new Group()
  group.add(rock)
  return group
}

function rocketMesh() {
  const group = new Group()
  const body = new Mesh(new CylinderGeometry(0.14, 0.17, 1.2, 8), paint('#cfc8f4'))
  const nose = new Mesh(new ConeGeometry(0.17, 0.34, 8), paint('#8C7AE6'))
  nose.position.y = 0.76
  group.add(body, nose)
  return group
}

function unknownMesh() {
  const group = new Group()
  group.add(new Mesh(new BoxGeometry(0.42, 0.42, 0.42), paint('#8B97A6')))
  return group
}

function craftFor(type: string) {
  if (type === 'debris') return debrisMesh()
  if (type === 'rocket body') return rocketMesh()
  if (type === 'unknown') return unknownMesh()
  return satelliteMesh()
}

export interface SimActor {
  index: number
  name: string
  type: string
  mesh: Group
}

export function createSimActors(
  indices: number[],
  names: string[],
  types: string[],
  positions: Float32Array,
  exaggerate: number,
) {
  const root = new Group()
  const actors: SimActor[] = []
  for (const index of indices) {
    const mesh = craftFor(types[index] ?? 'unknown')
    mesh.scale.setScalar(index === indices[0] ? SCALE * 1.4 : SCALE)
    mesh.rotateY((index % 11) * 0.4)
    root.add(mesh)
    actors.push({
      index,
      name: (names[index] ?? 'unknown').replace(/\s*\[.+$/, ''),
      type: types[index] ?? 'unknown',
      mesh,
    })
  }

  const place = (pos: Float32Array) => {
    for (const actor of actors) {
      const i = actor.index
      const [x, y, z] = exaggeratePoint(pos[i * 3], pos[i * 3 + 1], pos[i * 3 + 2], exaggerate)
      outward.set(x, y, z)
      const radius = outward.length() || 1
      radial.copy(outward).multiplyScalar(1 / radius)
      actor.mesh.position.copy(outward)
      actor.mesh.quaternion.setFromUnitVectors(up, radial)
    }
  }

  place(positions)

  return {
    root,
    actors,
    update: place,
    dispose() {
      root.removeFromParent()
      root.traverse((child) => {
        if (child instanceof Mesh) {
          child.geometry.dispose()
          const material = child.material
          if (Array.isArray(material)) material.forEach((item) => item.dispose())
          else material.dispose()
        }
      })
    },
  }
}

export function simCameraRig(x: number, y: number, z: number) {
  const target = new Vector3(x, y, z)
  const radialDir = target.clone().normalize()
  const tangent = new Vector3().crossVectors(radialDir, up)
  if (tangent.lengthSq() < 1e-8) tangent.set(1, 0, 0)
  tangent.normalize()
  const eye = target.clone().add(tangent.multiplyScalar(22)).add(radialDir.multiplyScalar(9))
  return { target, eye }
}
