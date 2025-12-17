<template>
  <div class="app">
    <header class="topbar">
      <div class="left">
        <h1>Digital Twin (Vue + Three.js)</h1>
      </div>
      <div class="controls">
        <label>
          Home ID
          <input v-model="homeId" />
        </label>
        <button @click="refreshHomeConfig">Refresh Config</button>
        <button @click="loadLatestMesh">Load Latest Mesh</button>
      </div>
    </header>

    <main class="content">
      <section class="scene">
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
          No mesh loaded. Generate one via <span class="mono">/api/v1/generate_3d</span> then load
          <span class="mono">/api/v1/3d_model/latest</span>.
        </div>
      </section>

      <aside class="panel">
        <div class="panelTabs">
          <button :class="{ active: panelTab === 'monitor' }" @click="panelTab = 'monitor'">
            Monitor
          </button>
          <button :class="{ active: panelTab === 'plan' }" @click="panelTab = 'plan'">2D Plan</button>
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
          v-else
          :homeId="homeId"
          :sensors="sensorList"
          @generated="applyMeshModel"
        />
      </aside>
    </main>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import ControlOverlay from './components/ControlOverlay.vue'
import PlanUploader from './components/PlanUploader.vue'
import SensorPanel from './components/SensorPanel.vue'
import TwinScene from './components/TwinScene.vue'
import { api } from './services/api'
import { createTwinSocket } from './services/socket'

const homeId = ref('main_home_config')
const meshData = ref(null)
const meshInfo = ref(null)

const securityStatus = ref('Safe')
const sensors = ref({})
const sensorsVersion = ref(0)
const roomsById = ref({})
const selectedRoomId = ref('')

const panelTab = ref('monitor')

const connected = ref({ api: false, socket: false })
const errors = ref([])

const visibility = ref({
  floor: true,
  walls: true,
  ceiling: true,
  sensors: true,
  wireframe: false,
})

const worldOffset = computed(() => meshData.value?.metadata?.world_offset || { x: 0, y: 0, z: 0 })

const sensorList = computed(() =>
  Object.values(sensors.value).sort((a, b) => String(a.id).localeCompare(String(b.id)))
)

const roomSummaries = computed(() => {
  const summary = {}

  // Seed rooms from config (even if there are no sensors)
  for (const [id, room] of Object.entries(roomsById.value || {})) {
    summary[id] = {
      id,
      name: room?.name || id,
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
        name: roomMeta?.name || id,
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
        name: sensor.room_name || rid,
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
    pushError(e?.response?.data?.error || e?.message || 'Failed to load /api/v1/home_config')
  }
}

async function loadLatestMesh() {
  try {
    const data = await api.getLatest3DModel(homeId.value)
    applyMeshModel(data)
  } catch (e) {
    pushError(e?.response?.data?.error || e?.message || 'Failed to load latest 3D model')
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

  socket.io.on('error', (err) => pushError(err?.message || 'socket error'))
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
</style>
