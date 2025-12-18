<template>
  <div ref="container" class="container"></div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, watch, ref } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { FirstPersonControls } from 'three/examples/jsm/controls/FirstPersonControls.js'

const props = defineProps({
  meshData: { type: Object, default: null },
  sensors: { type: Array, default: () => [] },
  worldOffset: { type: Object, default: () => ({ x: 0, y: 0, z: 0 }) },
  visibility: { type: Object, required: true },
  sensorsVersion: { type: Number, default: 0 },
  selectedRoomId: { type: String, default: '' },
})

const emit = defineEmits(['roomClick'])

const container = ref(null)

let renderer
let scene
let camera
let orbitControls
let fpControls
let controlMode = 'orbit'
let clock
let resizeObserver
let animationId

let rootGroup
let meshGroup
let sensorGroup
let roomOverlayGroup

let floorMesh = null
let wallsMesh = null
let ceilingMesh = null
let layerMeshes = []

const sensorMeshes = new Map()
let sharedSensorGeometry = null

const roomOverlayMeshes = new Map() // room_id -> Mesh
let alertRoomIds = new Set()
const raycaster = new THREE.Raycaster()
const pointer = new THREE.Vector2()

function initThree() {
  scene = new THREE.Scene()
  scene.background = new THREE.Color(0x0b1220)

  camera = new THREE.PerspectiveCamera(60, 1, 0.01, 2000)
  camera.position.set(6, 5, 6)
  clock = new THREE.Clock()

  renderer = new THREE.WebGLRenderer({
    antialias: true,
    alpha: false,
    powerPreference: 'high-performance',
  })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
  renderer.shadowMap.enabled = true
  renderer.shadowMap.type = THREE.PCFSoftShadowMap

  container.value.appendChild(renderer.domElement)

  orbitControls = new OrbitControls(camera, renderer.domElement)
  orbitControls.enableDamping = true
  orbitControls.dampingFactor = 0.08
  orbitControls.target.set(0, 0, 0)

  fpControls = new FirstPersonControls(camera, renderer.domElement)
  fpControls.enabled = false
  fpControls.lookSpeed = 0.12
  fpControls.movementSpeed = 2.5
  fpControls.lookVertical = true
  setControlMode(props.visibility?.cameraMode)

  const hemi = new THREE.HemisphereLight(0xbfd9ff, 0x1b2a44, 0.75)
  scene.add(hemi)

  const dir = new THREE.DirectionalLight(0xffffff, 1.1)
  dir.position.set(8, 12, 6)
  dir.castShadow = true
  dir.shadow.mapSize.set(2048, 2048)
  scene.add(dir)

  const grid = new THREE.GridHelper(30, 30, 0x2a3a55, 0x1e2a40)
  grid.position.set(0, 0, 0)
  scene.add(grid)

  rootGroup = new THREE.Group()
  // Backend geometry is Z-up (x,y plan, z height). Convert to Three.js Y-up:
  // local (x,y,z) -> world (x,z,y) by applying scaleZ=-1 then rotX=+90deg.
  rootGroup.rotation.x = Math.PI / 2
  rootGroup.scale.z = -1
  scene.add(rootGroup)

  meshGroup = new THREE.Group()
  rootGroup.add(meshGroup)

  roomOverlayGroup = new THREE.Group()
  rootGroup.add(roomOverlayGroup)

  sensorGroup = new THREE.Group()
  rootGroup.add(sensorGroup)

  sharedSensorGeometry = new THREE.SphereGeometry(0.08, 16, 16)

  resizeObserver = new ResizeObserver(() => onResize())
  resizeObserver.observe(container.value)
  onResize()
}

function onResize() {
  if (!container.value || !renderer || !camera) return
  const { width, height } = container.value.getBoundingClientRect()
  if (width <= 0 || height <= 0) return

  renderer.setSize(width, height, false)
  camera.aspect = width / height
  camera.updateProjectionMatrix()
}

function buildGeometry(part) {
  const geometry = new THREE.BufferGeometry()
  const positions = (part?.vertices || []).flat()
  const indices = (part?.faces || []).flat()

  geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
  geometry.setIndex(indices)
  geometry.computeVertexNormals()
  geometry.computeBoundingSphere()
  return geometry
}

function disposeMesh(mesh) {
  if (!mesh) return
  meshGroup.remove(mesh)
  if (mesh.geometry) mesh.geometry.dispose()
  if (mesh.material) mesh.material.dispose()
}

function disposeRoomOverlays() {
  if (!roomOverlayGroup) return
  for (const [, mesh] of roomOverlayMeshes.entries()) {
    roomOverlayGroup.remove(mesh)
    mesh.geometry?.dispose()
    mesh.material?.dispose()
  }
  roomOverlayMeshes.clear()
}

function clearSensorMeshes() {
  if (!sensorGroup) return
  for (const [, mesh] of sensorMeshes.entries()) {
    sensorGroup.remove(mesh)
    if (mesh.material) mesh.material.dispose()
  }
  sensorMeshes.clear()
}

function clearScene() {
  disposeMesh(floorMesh)
  disposeMesh(wallsMesh)
  disposeMesh(ceilingMesh)
  floorMesh = null
  wallsMesh = null
  ceilingMesh = null

  if (Array.isArray(layerMeshes) && layerMeshes.length && meshGroup) {
    for (const entry of layerMeshes) {
      if (!entry?.mesh) continue
      meshGroup.remove(entry.mesh)
      entry.mesh.geometry?.dispose()
      if (entry.mesh.material) {
        if (Array.isArray(entry.mesh.material)) entry.mesh.material.forEach((m) => m?.dispose())
        else entry.mesh.material.dispose()
      }
    }
  }
  layerMeshes = []

  disposeRoomOverlays()
  clearSensorMeshes()
}

function makeMaterial(colorHex, { wireframe = false, opacity = 1.0 } = {}) {
  return new THREE.MeshStandardMaterial({
    color: colorHex,
    metalness: 0.02,
    roughness: 0.9,
    side: THREE.DoubleSide,
    wireframe,
    transparent: opacity < 1.0,
    opacity,
  })
}

function setControlMode(mode) {
  const next = mode === 'first-person' ? 'first-person' : 'orbit'
  controlMode = next
  if (orbitControls) orbitControls.enabled = next === 'orbit'
  if (fpControls) fpControls.enabled = next === 'first-person'
  if (renderer?.domElement) {
    renderer.domElement.style.cursor = next === 'first-person' ? 'crosshair' : 'auto'
  }
}

function rebuildModel() {
  clearScene()

  if (!props.meshData) return

  const wireframe = Boolean(props.visibility?.wireframe)

  if (Array.isArray(props.meshData.layers) && props.meshData.layers.length) {
    const wallOpacity = Math.max(0.1, Math.min(1, Number(props.visibility?.wallOpacity ?? 1)))
    const floorOpacity = Math.max(0.1, Math.min(1, Number(props.visibility?.floorOpacity ?? 1)))
    const ceilingOpacity = Math.max(0.1, Math.min(1, Number(props.visibility?.ceilingOpacity ?? floorOpacity)))

    for (const layer of props.meshData.layers) {
      const zOffset = Number(layer?.z_offset || 0)

      if (layer.floor) {
        const geometry = buildGeometry(layer.floor)
        const material = makeMaterial(0x2d6a4f, { wireframe, opacity: floorOpacity })
        const mesh = new THREE.Mesh(geometry, material)
        mesh.position.y = zOffset
        mesh.receiveShadow = true
        mesh.visible = Boolean(props.visibility?.floor)
        meshGroup.add(mesh)
        layerMeshes.push({ mesh, type: 'floor' })
      }

      if (layer.walls) {
        const geometry = buildGeometry(layer.walls)
        const material = makeMaterial(0xf3f4f6, { wireframe, opacity: wallOpacity })
        const mesh = new THREE.Mesh(geometry, material)
        mesh.position.y = zOffset
        mesh.castShadow = true
        mesh.receiveShadow = true
        mesh.visible = Boolean(props.visibility?.walls)
        meshGroup.add(mesh)
        layerMeshes.push({ mesh, type: 'walls' })
      }

      if (layer.ceiling) {
        const geometry = buildGeometry(layer.ceiling)
        const material = makeMaterial(0xd1d5db, { wireframe, opacity: ceilingOpacity })
        const mesh = new THREE.Mesh(geometry, material)
        mesh.position.y = zOffset
        mesh.receiveShadow = true
        mesh.visible = Boolean(props.visibility?.ceiling)
        meshGroup.add(mesh)
        layerMeshes.push({ mesh, type: 'ceiling' })
      }
    }
  } else if (props.meshData.floor) {
    const geometry = buildGeometry(props.meshData.floor)
    const material = makeMaterial(0x2d6a4f, { wireframe })
    floorMesh = new THREE.Mesh(geometry, material)
    floorMesh.receiveShadow = true
    floorMesh.visible = Boolean(props.visibility?.floor)
    meshGroup.add(floorMesh)
  }

  if (props.meshData.walls) {
    const geometry = buildGeometry(props.meshData.walls)
    const material = makeMaterial(0xf3f4f6, { wireframe })
    wallsMesh = new THREE.Mesh(geometry, material)
    wallsMesh.castShadow = true
    wallsMesh.receiveShadow = true
    wallsMesh.visible = Boolean(props.visibility?.walls)
    meshGroup.add(wallsMesh)
  }

  if (props.meshData.ceiling) {
    const geometry = buildGeometry(props.meshData.ceiling)
    const material = makeMaterial(0xd1d5db, { wireframe, opacity: 0.7 })
    ceilingMesh = new THREE.Mesh(geometry, material)
    ceilingMesh.receiveShadow = true
    ceilingMesh.visible = Boolean(props.visibility?.ceiling)
    meshGroup.add(ceilingMesh)
  }

  fitCameraToModel()
}

function normalizeRing(points) {
  if (!Array.isArray(points)) return []
  let ring = points
    .filter((p) => Array.isArray(p) && p.length >= 2)
    .map((p) => [Number(p[0] || 0), Number(p[1] || 0)])

  // Remove trailing repeated start point
  if (ring.length >= 2) {
    const [x0, y0] = ring[0]
    const [xn, yn] = ring[ring.length - 1]
    if (x0 === xn && y0 === yn) ring = ring.slice(0, -1)
  }

  // Remove consecutive duplicates
  const cleaned = []
  for (const p of ring) {
    const last = cleaned[cleaned.length - 1]
    if (!last || last[0] !== p[0] || last[1] !== p[1]) cleaned.push(p)
  }
  return cleaned
}

function signedArea2D(ring) {
  let area = 0
  for (let i = 0; i < ring.length; i++) {
    const [x1, y1] = ring[i]
    const [x2, y2] = ring[(i + 1) % ring.length]
    area += x1 * y2 - x2 * y1
  }
  return area / 2
}

function triangulateEarClipping(ringIn) {
  const ring = normalizeRing(ringIn)
  if (ring.length < 3) return []

  const ringCCW = signedArea2D(ring) < 0 ? [...ring].reverse() : ring
  const n = ringCCW.length

  const cross = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
  const isPointInTriangle = (p, a, b, c) => {
    const eps = 1e-12
    const c1 = cross(a, b, p)
    const c2 = cross(b, c, p)
    const c3 = cross(c, a, p)
    return c1 >= -eps && c2 >= -eps && c3 >= -eps
  }

  const indices = Array.from({ length: n }, (_, i) => i)
  const triangles = []

  let guard = 0
  while (indices.length > 3 && guard < n * n) {
    guard += 1
    let earFound = false
    for (let pos = 0; pos < indices.length; pos++) {
      const prev = indices[(pos - 1 + indices.length) % indices.length]
      const curr = indices[pos]
      const next = indices[(pos + 1) % indices.length]

      const a = ringCCW[prev]
      const b = ringCCW[curr]
      const c = ringCCW[next]

      // convex corner in CCW polygon
      if (cross(a, b, c) <= 1e-12) continue

      let isEar = true
      for (const test of indices) {
        if (test === prev || test === curr || test === next) continue
        if (isPointInTriangle(ringCCW[test], a, b, c)) {
          isEar = false
          break
        }
      }
      if (!isEar) continue

      triangles.push([prev, curr, next])
      indices.splice(pos, 1)
      earFound = true
      break
    }
    if (!earFound) break
  }

  if (indices.length === 3) triangles.push([indices[0], indices[1], indices[2]])

  // Map back to original ring indices if we reversed
  if (ringCCW !== ring) {
    const mapIndex = (i) => n - 1 - i
    return triangles.map(([a, b, c]) => [mapIndex(a), mapIndex(b), mapIndex(c)])
  }

  return triangles
}

function rebuildRoomOverlays() {
  disposeRoomOverlays()
  const rooms = props.meshData?.metadata?.rooms
  if (!rooms || typeof rooms !== 'object') return

  const xOff = Number(props.worldOffset?.x || 0)
  const yOff = Number(props.worldOffset?.y || 0)
  const zOff = Number(props.worldOffset?.z || 0)
  const zElev = 0.02 - zOff

  for (const [roomId, roomMeta] of Object.entries(rooms)) {
    const polygon = roomMeta?.polygon
    if (!Array.isArray(polygon)) continue

    const ring = normalizeRing(polygon).map(([x, y]) => [x - xOff, y - yOff])
    const triangles = triangulateEarClipping(ring)
    if (!triangles.length) continue

    const positions = ring.flatMap(([x, y]) => [x, y, zElev])
    const indices = triangles.flat()

    const geometry = new THREE.BufferGeometry()
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
    geometry.setIndex(indices)
    geometry.computeVertexNormals()

    const material = new THREE.MeshBasicMaterial({
      color: 0xff4d4d,
      transparent: true,
      opacity: 0,
      side: THREE.DoubleSide,
      depthWrite: false,
    })

    const mesh = new THREE.Mesh(geometry, material)
    mesh.renderOrder = 10
    mesh.userData.roomId = roomId
    roomOverlayGroup.add(mesh)
    roomOverlayMeshes.set(roomId, mesh)
  }
}

function fitCameraToModel() {
  const box = new THREE.Box3().setFromObject(meshGroup)
  if (!Number.isFinite(box.min.x) || !Number.isFinite(box.max.x)) return

  const size = box.getSize(new THREE.Vector3())
  const center = box.getCenter(new THREE.Vector3())

  const maxDim = Math.max(size.x, size.y, size.z)
  const dist = Math.max(2.5, maxDim * 1.5)

  orbitControls?.target.copy(center)
  camera.position.set(center.x + dist, center.y + dist * 0.7, center.z + dist)
  camera.near = 0.01
  camera.far = Math.max(200, dist * 10)
  camera.updateProjectionMatrix()
  if (orbitControls) orbitControls.update()
  else camera.lookAt(center)
}

function sensorColor(sensor) {
  if (sensor?.is_alert) return 0xff4d4d
  const type = String(sensor?.type || '').toLowerCase()
  if (type.includes('pir')) return 0x60a5fa
  if (type.includes('door')) return 0xfbbf24
  if (type.includes('smoke')) return 0xa78bfa
  if (type.includes('temp')) return 0x22d3ee
  return 0x22c55e
}

function recomputeAlertRooms() {
  const nextAlertRooms = new Set()
  for (const s of props.sensors || []) {
    if (s?.is_alert && s?.room_id) nextAlertRooms.add(String(s.room_id))
  }
  alertRoomIds = nextAlertRooms
}

function updateSensors() {
  if (!sensorGroup) return

  recomputeAlertRooms()

  const visible = Boolean(props.visibility?.sensors)
  sensorGroup.visible = visible
  if (!visible) return

  const keep = new Set()
  const xOff = Number(props.worldOffset?.x || 0)
  const yOff = Number(props.worldOffset?.y || 0)
  const zOff = Number(props.worldOffset?.z || 0)
  const lift = 0.08

  for (const sensor of props.sensors || []) {
    if (!sensor?.id) continue
    keep.add(sensor.id)

    const location = sensor.location
    if (!Array.isArray(location) || location.length < 2) continue

    const rawX = Number(location[0] || 0)
    const rawY = Number(location[1] || 0)
    const rawZ = Number(location[2] || 0)

    // Align with backend z-up convention: place at [x - off.x, z, y - off.y]
    const x = rawX - xOff
    const y = rawZ - zOff + lift
    const z = rawY - yOff

    let mesh = sensorMeshes.get(sensor.id)
    if (!mesh) {
      const material = new THREE.MeshStandardMaterial({
        color: sensorColor(sensor),
        metalness: 0.05,
        roughness: 0.5,
      })
      mesh = new THREE.Mesh(sharedSensorGeometry, material)
      mesh.castShadow = true
      mesh.name = `sensor:${sensor.id}`
      sensorGroup.add(mesh)
      sensorMeshes.set(sensor.id, mesh)
    }

    mesh.position.set(x, y, z)
    mesh.material.color.setHex(sensorColor(sensor))
  }

  for (const [id, mesh] of sensorMeshes.entries()) {
    if (keep.has(id)) continue
    sensorGroup.remove(mesh)
    if (mesh.material) mesh.material.dispose()
    sensorMeshes.delete(id)
  }
}

function updateVisibility() {
  if (floorMesh) floorMesh.visible = Boolean(props.visibility?.floor)
  if (wallsMesh) wallsMesh.visible = Boolean(props.visibility?.walls)
  if (ceilingMesh) ceilingMesh.visible = Boolean(props.visibility?.ceiling)
  if (sensorGroup) sensorGroup.visible = Boolean(props.visibility?.sensors)

  setControlMode(props.visibility?.cameraMode)

  const wireframe = Boolean(props.visibility?.wireframe)
  for (const mesh of [floorMesh, wallsMesh, ceilingMesh]) {
    if (!mesh) continue
    mesh.material.wireframe = wireframe
  }

  const wallOpacity = Math.max(0.1, Math.min(1, Number(props.visibility?.wallOpacity ?? 1)))
  if (wallsMesh?.material) {
    wallsMesh.material.opacity = wallOpacity
    wallsMesh.material.transparent = wallOpacity < 1 || wallsMesh.material.wireframe
  }

  const floorOpacity = Math.max(0.1, Math.min(1, Number(props.visibility?.floorOpacity ?? 1)))
  const ceilingOpacity = Math.max(0.1, Math.min(1, Number(props.visibility?.ceilingOpacity ?? floorOpacity)))

  if (floorMesh?.material) {
    floorMesh.material.opacity = floorOpacity
    floorMesh.material.transparent = floorOpacity < 1 || floorMesh.material.wireframe
  }
  if (ceilingMesh?.material) {
    ceilingMesh.material.opacity = ceilingOpacity
    ceilingMesh.material.transparent = ceilingOpacity < 1 || ceilingMesh.material.wireframe
  }

  if (Array.isArray(layerMeshes) && layerMeshes.length) {
    for (const entry of layerMeshes) {
      const m = entry.mesh
      if (!m?.material) continue
      if (entry.type === 'floor') {
        m.visible = Boolean(props.visibility?.floor)
        m.material.opacity = floorOpacity
        m.material.transparent = floorOpacity < 1 || m.material.wireframe
      } else if (entry.type === 'walls') {
        m.visible = Boolean(props.visibility?.walls)
        m.material.opacity = wallOpacity
        m.material.transparent = wallOpacity < 1 || m.material.wireframe
      } else if (entry.type === 'ceiling') {
        m.visible = Boolean(props.visibility?.ceiling)
        m.material.opacity = ceilingOpacity
        m.material.transparent = ceilingOpacity < 1 || m.material.wireframe
      }
      m.material.wireframe = wireframe
    }
  }
}

function updateRoomOverlayAnimation(timeMs) {
  if (!roomOverlayMeshes.size) return
  const t = timeMs / 1000
  const pulse = (Math.sin(t * 7.0) + 1) / 2 // 0..1
  const selected = props.selectedRoomId ? String(props.selectedRoomId) : ''

  for (const [roomId, mesh] of roomOverlayMeshes.entries()) {
    const isAlert = alertRoomIds.has(roomId)
    const isSelected = selected && roomId === selected
    if (isAlert) {
      mesh.material.color.setHex(0xff4d4d)
      mesh.material.opacity = 0.18 + pulse * 0.45
    } else if (isSelected) {
      mesh.material.color.setHex(0x60a5fa)
      mesh.material.opacity = 0.22
    } else {
      mesh.material.opacity = 0
    }
  }
}

function onPointerDown(event) {
  if (!renderer || !camera || !container.value) return
  if (!roomOverlayMeshes.size) return

  const rect = renderer.domElement.getBoundingClientRect()
  const x = ((event.clientX - rect.left) / rect.width) * 2 - 1
  const y = -(((event.clientY - rect.top) / rect.height) * 2 - 1)
  pointer.set(x, y)
  raycaster.setFromCamera(pointer, camera)

  const meshes = Array.from(roomOverlayMeshes.values())
  const hits = raycaster.intersectObjects(meshes, false)
  if (!hits.length) return

  const roomId = hits[0]?.object?.userData?.roomId
  if (roomId) emit('roomClick', roomId)
}

function loop() {
  animationId = requestAnimationFrame(loop)
  const delta = clock ? clock.getDelta() : 0
  if (controlMode === 'first-person') {
    fpControls?.update(delta)
  } else {
    orbitControls?.update()
  }
  updateRoomOverlayAnimation(performance.now())
  renderer?.render(scene, camera)
}

onMounted(() => {
  initThree()
  rebuildModel()
  rebuildRoomOverlays()
  updateSensors()
  updateVisibility()
  renderer?.domElement?.addEventListener('pointerdown', onPointerDown)
  loop()
})

onBeforeUnmount(() => {
  if (animationId) cancelAnimationFrame(animationId)
  resizeObserver?.disconnect()
  renderer?.domElement?.removeEventListener('pointerdown', onPointerDown)

  clearScene()
  sharedSensorGeometry?.dispose()

  orbitControls?.dispose()
  fpControls?.dispose()
  renderer?.dispose()

  if (renderer?.domElement && renderer.domElement.parentNode) {
    renderer.domElement.parentNode.removeChild(renderer.domElement)
  }
})

watch(
  () => props.meshData,
  (val) => {
    if (!val) {
      clearScene()
      return
    }
    rebuildModel()
    rebuildRoomOverlays()
    updateVisibility()
    updateSensors()
  }
)

watch(
  () => props.sensorsVersion,
  () => updateSensors()
)

watch(
  () => props.selectedRoomId,
  () => {
    // no-op; selection is applied during animation loop
  }
)

watch(
  () => props.visibility,
  () => updateVisibility(),
  { deep: true }
)
</script>

<style scoped>
.container {
  position: absolute;
  inset: 0;
}
</style>
