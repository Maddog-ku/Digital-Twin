<template>
  <div class="app">
    <header class="topbar">
      <div class="left">
        <h1>數位分身（Vue + Three.js）</h1>
      </div>
      <div class="controls">
        <label>
          家庭 ID
          <input v-model="homeId" />
        </label>
        <button @click="refreshHomeConfig">重新載入設定</button>
        <button @click="loadLatestMesh">載入最新模型</button>
        <button v-if="currentMeshId" class="danger" @click="removeCurrentModel">移除 3D 模型</button>
      </div>
    </header>

    <main class="content">
      <section class="scene" :class="{ uploading: sceneMode === 'upload' }">
        <div class="sceneSwitcher">
          <button :class="{ active: sceneMode === 'viewer' }" @click="sceneMode = 'viewer'">
            3D 視圖
          </button>
          <button :class="{ active: sceneMode === 'upload' }" @click="sceneMode = 'upload'">
            AI 圖片上傳
          </button>
        </div>

        <div v-if="sceneMode === 'upload'" class="uploadWrapper">
          <ImageUploadPanel :homeId="homeId" @generated="handleModelGenerated" />
        </div>
        <template v-else>
          <TwinScene
            :meshData="meshData"
            :sensors="sensorList"
            :worldOffset="worldOffset"
            :visibility="visibility"
            :sensorsVersion="sensorsVersion"
            :selectedRoomId="selectedRoomId"
            @roomClick="selectRoom"
          />
          <ControlOverlay v-model="visibility" />

          <div v-if="!meshData" class="hint">
            尚未載入模型。可透過 <span class="mono">/api/v1/generate_3d</span> 或
            <span class="mono">/api/v1/auto_generate_from_image</span> 生成，接著載入
            <span class="mono">/api/v1/3d_model/latest</span>。
          </div>
        </template>
      </section>

      <aside class="panel">
        <div class="panelTabs">
          <button :class="{ active: panelTab === 'monitor' }" @click="panelTab = 'monitor'">
            監控
          </button>
          <button :class="{ active: panelTab === 'plan' }" @click="panelTab = 'plan'">2D 平面圖</button>
          <button :class="{ active: panelTab === 'floors' }" @click="panelTab = 'floors'">
            樓層
          </button>
        </div>

        <SensorPanel
          v-if="panelTab === 'monitor'"
          :sensors="sensorList"
          :rooms="roomSummaries"
          :selectedRoomId="selectedRoomId"
          :securityStatus="securityStatus"
          :meshInfo="meshInfo"
          :worldOffset="worldOffset"
          :errors="errors"
          :connected="connected"
          @selectRoom="selectRoom"
        />

        <PlanUploader
          v-else-if="panelTab === 'plan'"
          :homeId="homeId"
          :sensors="sensorList"
          @generated="handleModelGenerated"
        />
        <FloorManager
          v-else
          :homeId="homeId"
          @update-mesh="loadMeshById"
          @view-floor="viewFloor"
        />
      </aside>
    </main>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import ControlOverlay from './components/ControlOverlay.vue'
import FloorManager from './components/FloorManager.vue'
import ImageUploadPanel from './components/ImageUploadPanel.vue'
import PlanUploader from './components/PlanUploader.vue'
import SensorPanel from './components/SensorPanel.vue'
import TwinScene from './components/TwinScene.vue'
import { api } from './services/api'
import { createTwinSocket } from './services/socket'

const homeId = ref('main_home_config')
const meshData = ref(null)
const meshInfo = ref(null)
const currentMeshId = computed(() => meshInfo.value?.mesh_id || null)

const securityStatus = ref('Safe')
const sensors = ref({})
const sensorsVersion = ref(0)
const roomsById = ref({})
const selectedRoomId = ref('')

const panelTab = ref('monitor')
const sceneMode = ref('viewer')

const connected = ref({ api: false, socket: false })
const errors = ref([])

const visibility = ref({
  floor: true,
  walls: true,
  ceiling: true,
  sensors: true,
  wireframe: false,
  wallOpacity: 1,
  floorOpacity: 1,
  ceilingOpacity: 1,
  cameraMode: 'orbit',
})

const worldOffset = computed(() => meshData.value?.metadata?.world_offset || { x: 0, y: 0, z: 0 })

const sensorList = computed(() =>
  Object.values(sensors.value).sort((a, b) => String(a.id).localeCompare(String(b.id)))
)

const roomSummaries = computed(() => {
  const summary = {}
  const displayName = (id, name) => {
    if (name) return name
    return id === 'unknown' ? '未知' : id
  }

  // Seed rooms from config (even if there are no sensors)
  for (const [id, room] of Object.entries(roomsById.value || {})) {
    summary[id] = {
      id,
      name: displayName(id, room?.name),
      sensors: [],
      alertCount: 0,
    }
  }

  // Seed rooms from the loaded mesh metadata (useful when generating custom plans)
  const meshRooms = meshData.value?.metadata?.rooms
  if (meshRooms && typeof meshRooms === 'object') {
    for (const [id, roomMeta] of Object.entries(meshRooms)) {
      if (summary[id]) continue
      summary[id] = {
        id,
        name: displayName(id, roomMeta?.name),
        sensors: [],
        alertCount: 0,
      }
    }
  }

  for (const sensor of sensorList.value) {
    const rid = String(sensor.room_id || 'unknown')
    if (!summary[rid]) {
      summary[rid] = {
        id: rid,
        name: displayName(rid, sensor.room_name),
        sensors: [],
        alertCount: 0,
      }
    }
    summary[rid].sensors.push(sensor)
    if (sensor.is_alert) summary[rid].alertCount += 1
  }

  return Object.values(summary).sort((a, b) => {
    if (a.id === 'unknown') return 1
    if (b.id === 'unknown') return -1
    return String(a.name || a.id).localeCompare(String(b.name || b.id))
  })
})

let socket = null
const removing = ref(false)

function pushError(message) {
  if (!message) return
  const next = [String(message), ...errors.value]
  errors.value = next.slice(0, 8)
}

function applyHomeConfig(home) {
  if (home?.home_id && !homeId.value) {
    homeId.value = home.home_id
  }
  if (home?.security_status) {
    securityStatus.value = home.security_status
  }

  const nextRooms = {}
  const nextSensors = {}
  for (const room of home?.rooms || []) {
    nextRooms[room.id] = { id: room.id, name: room.name, owner: room.owner }
    for (const sensor of room?.sensors || []) {
      nextSensors[sensor.id] = {
        ...sensor,
        id: sensor.id,
        room_id: room.id,
        room_name: room.name,
      }
    }
  }
  roomsById.value = nextRooms
  sensors.value = nextSensors
  sensorsVersion.value += 1

  if (!selectedRoomId.value && home?.rooms?.length) {
    selectedRoomId.value = home.rooms[0].id
  }
}

function applySensorUpdate(update) {
  if (!update?.sensor_id) return
  const id = update.sensor_id
  const existing = sensors.value[id] || { id }

  sensors.value[id] = {
    ...existing,
    id,
    type: update.type ?? existing.type,
    status: update.new_status ?? existing.status,
    is_alert: Boolean(update.is_alert),
    location: update.location ?? existing.location,
    room_id: update.room_id ?? existing.room_id,
    room_name: update.room_name ?? existing.room_name,
  }
  sensorsVersion.value += 1
}

async function refreshHomeConfig() {
  try {
    const data = await api.getHomeConfig()
    connected.value.api = true
    applyHomeConfig(data)
  } catch (e) {
    connected.value.api = false
    pushError(e?.response?.data?.error || e?.message || '無法載入 /api/v1/home_config')
  }
}

async function loadLatestMesh() {
  try {
    const data = await api.getLatest3DModel(homeId.value)
    applyMeshModel(data)
  } catch (e) {
    pushError(e?.response?.data?.error || e?.message || '無法載入最新 3D 模型')
  }
}

async function loadMeshById(meshId) {
  if (!meshId) return
  try {
    const data = await api.get3DModel(meshId)
    applyMeshModel(data)
  } catch (e) {
    pushError(e?.response?.data?.error || e?.message || `無法載入模型 ${meshId}`)
  }
}

function applyMeshModel(model) {
  const data = model?.data ? model : model?.result ? model.result : model
  if (!data?.mesh_id) return
  meshInfo.value = {
    mesh_id: data.mesh_id,
    mesh_format: data.mesh_format,
    created_at: data.created_at,
  }
  if (data.data) {
    meshData.value = data.data
    const rooms = data.data?.metadata?.rooms
    const roomIds = rooms && typeof rooms === 'object' ? Object.keys(rooms) : []
    if (!selectedRoomId.value && roomIds.length) {
      selectedRoomId.value = roomIds[0]
    }
  }
  sceneMode.value = 'viewer'
}

function handleModelGenerated(model) {
  applyMeshModel(model)
}

function viewFloor(floor) {
  sceneMode.value = 'viewer'
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

async function removeCurrentModel() {
  if (removing.value) return
  if (!currentMeshId.value && !meshData.value) return
  if (!window.confirm('確定要移除目前的 3D 模型嗎？')) return

  removing.value = true
  try {
    if (currentMeshId.value) {
      await api.delete3DModel(currentMeshId.value).catch((err) => {
        // 允許前端仍然清除，但保留錯誤訊息
        pushError(err?.response?.data?.error || err?.message || '刪除模型失敗')
      })
    }
  } finally {
    meshData.value = null
    meshInfo.value = null
    selectedRoomId.value = ''
    sceneMode.value = 'upload'
    window.scrollTo({ top: 0, behavior: 'smooth' })
    removing.value = false
  }
}

function selectRoom(roomId) {
  if (!roomId) return
  selectedRoomId.value = String(roomId)
  panelTab.value = 'monitor'
}

function connectSocket() {
  socket = createTwinSocket()
  socket.on('connect', () => {
    connected.value.socket = true
  })
  socket.on('disconnect', () => {
    connected.value.socket = false
  })

  socket.on('sensor_update', (payload) => applySensorUpdate(payload))
  socket.on('security_status_update', (payload) => {
    if (payload?.status) securityStatus.value = payload.status
  })

  socket.io.on('error', (err) => pushError(err?.message || 'Socket 錯誤'))
}

onMounted(async () => {
  await refreshHomeConfig()
  connectSocket()
})

onBeforeUnmount(() => {
  socket?.disconnect()
  socket = null
})
</script>

<style scoped>
.panelTabs {
  display: flex;
  gap: 8px;
  padding: 12px 12px 0;
}

.panelTabs button {
  flex: 1;
  padding: 8px 10px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(255, 255, 255, 0.04);
  color: rgba(255, 255, 255, 0.85);
  cursor: pointer;
}

.panelTabs button.active {
  background: rgba(96, 165, 250, 0.16);
  border-color: rgba(96, 165, 250, 0.4);
}

.hint {
  position: absolute;
  left: 12px;
  right: 12px;
  bottom: 12px;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(10, 16, 30, 0.7);
  backdrop-filter: blur(10px);
  color: rgba(255, 255, 255, 0.85);
  font-size: 13px;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono',
    'Courier New', monospace;
}

.sceneSwitcher {
  position: absolute;
  top: 12px;
  right: 12px;
  display: flex;
  gap: 8px;
  z-index: 3;
}

.sceneSwitcher button {
  padding: 8px 10px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(15, 26, 45, 0.75);
  color: rgba(255, 255, 255, 0.9);
  cursor: pointer;
  backdrop-filter: blur(8px);
}

.sceneSwitcher button.active {
  background: rgba(96, 165, 250, 0.2);
  border-color: rgba(96, 165, 250, 0.4);
}

.uploadWrapper {
  position: absolute;
  inset: 0;
  padding: 20px;
  overflow: auto;
  display: grid;
  place-items: center;
}
</style>
