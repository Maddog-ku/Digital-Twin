<template>
  <div class="floorManager">
    <div class="head">
      <div>
        <div class="title">樓層管理</div>
        <div class="hint mono">/api/v1/homes/{{ homeId }}/floors</div>
      </div>
      <div class="pill">{{ floors.length }} 層</div>
    </div>

    <div v-if="loading" class="status mono">載入中…</div>
    <div v-else-if="!floors.length" class="status mono">尚未新增樓層，請上傳圖片。</div>

    <div v-else class="list">
      <div v-for="floor in floors" :key="floor.level" class="item">
        <div class="meta">
          <div class="level">第 {{ floor.level }} 層</div>
          <div class="muted mono">{{ floor.mesh_id || floor.full_mesh_id || '無 mesh_id' }}</div>
        </div>
        <div class="actions">
          <button @click="viewFloor(floor)">檢視</button>
          <button class="danger" @click="deleteFloor(floor.level)">刪除</button>
        </div>
      </div>
    </div>

    <div class="divider" />

    <div class="add">
      <div class="title">新增樓層</div>
      <div class="row">
        <label>
          <span>層數</span>
          <select v-model.number="newFloorLevel">
            <option :value="1">1F</option>
            <option :value="2">2F</option>
            <option :value="3">3F</option>
            <option :value="4">4F</option>
          </select>
        </label>
        <label>
          <span>比例 (pixel_to_meter_ratio)</span>
          <input v-model.number="scaleRatio" type="number" step="0.001" min="0.001" />
        </label>
        <label>
          <span>樓層高度 (m)</span>
          <input v-model.number="floorHeight" type="number" step="0.1" min="0.1" />
        </label>
      </div>
      <label class="file">
        <span>平面圖圖片</span>
        <input type="file" accept="image/*" @change="handleFileSelect" />
        <div v-if="selectedFile" class="muted">{{ selectedFile.name }}</div>
      </label>
      <div class="cta">
        <button class="primary" :disabled="!selectedFile || uploading" @click="uploadFloor">
          {{ uploading ? '上傳中…' : '上傳並堆疊' }}
        </button>
      </div>
      <div v-if="error" class="error mono">{{ error }}</div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'

import { api } from '../services/api'

const props = defineProps({
  homeId: { type: String, required: true },
})

const emit = defineEmits(['update-mesh', 'view-floor'])

const floors = ref([])
const loading = ref(false)
const uploading = ref(false)
const error = ref('')

const newFloorLevel = ref(1)
const selectedFile = ref(null)
const scaleRatio = ref(0.01)
const floorHeight = ref(3.0)

async function fetchFloors() {
  loading.value = true
  error.value = ''
  try {
    const res = await api.listFloors(props.homeId)
    floors.value = Array.isArray(res?.floors) ? [...res.floors].sort((a, b) => a.level - b.level) : []
  } catch (e) {
    error.value = e?.response?.data?.error || e?.message || '無法取得樓層列表'
  } finally {
    loading.value = false
  }
}

function handleFileSelect(event) {
  selectedFile.value = event?.target?.files?.[0] || null
}

async function uploadFloor() {
  if (!selectedFile.value) return
  uploading.value = true
  error.value = ''
  try {
    const form = new FormData()
    form.append('image', selectedFile.value)
    form.append('level', newFloorLevel.value)
    form.append('pixel_to_meter_ratio', scaleRatio.value)
    form.append('height', floorHeight.value)

    const res = await api.uploadFloor(props.homeId, form)
    const floorInfo = {
      level: Number(newFloorLevel.value),
      ...(res?.floor || res || {}),
    }

    const existingIdx = floors.value.findIndex((f) => Number(f.level) === floorInfo.level)
    if (existingIdx !== -1) floors.value.splice(existingIdx, 1)
    floors.value.push(floorInfo)
    floors.value.sort((a, b) => Number(a.level) - Number(b.level))

    const fullMeshId = res?.full_mesh_id || res?.mesh_id || floorInfo?.mesh_id
    if (fullMeshId) emit('update-mesh', fullMeshId)

    // auto prep next level
    newFloorLevel.value = floorInfo.level + 1
    selectedFile.value = null
  } catch (e) {
    error.value = e?.response?.data?.error || e?.message || '上傳樓層失敗'
  } finally {
    uploading.value = false
  }
}

async function deleteFloor(level) {
  if (!window.confirm(`刪除第 ${level} 層？`)) return
  try {
    await api.deleteFloor(props.homeId, level)
    floors.value = floors.value.filter((f) => Number(f.level) !== Number(level))
    const remaining = floors.value[0]
    const meshId = remaining?.full_mesh_id || remaining?.mesh_id
    if (meshId) emit('update-mesh', meshId)
  } catch (e) {
    error.value = e?.response?.data?.error || e?.message || '刪除樓層失敗'
  }
}

function viewFloor(floor) {
  emit('view-floor', floor)
  const meshId = floor?.full_mesh_id || floor?.mesh_id
  if (meshId) emit('update-mesh', meshId)
}

onMounted(() => {
  fetchFloors()
})
</script>

<style scoped>
.floorManager {
  padding: 14px;
  display: grid;
  gap: 12px;
}

.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.title {
  font-weight: 800;
}

.hint {
  color: rgba(255, 255, 255, 0.65);
  font-size: 12px;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono',
    'Courier New', monospace;
}

.pill {
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(96, 165, 250, 0.16);
  border: 1px solid rgba(96, 165, 250, 0.45);
  font-size: 12px;
}

.list {
  display: grid;
  gap: 10px;
}

.item {
  padding: 10px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.03);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.meta {
  display: grid;
  gap: 4px;
}

.level {
  font-weight: 700;
}

.muted {
  color: rgba(255, 255, 255, 0.7);
  font-size: 12px;
}

.actions {
  display: flex;
  gap: 8px;
}

button {
  padding: 7px 10px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(255, 255, 255, 0.06);
  color: rgba(255, 255, 255, 0.9);
  cursor: pointer;
}

.danger {
  background: rgba(255, 77, 77, 0.18);
  border-color: rgba(255, 77, 77, 0.35);
}

.divider {
  height: 1px;
  background: rgba(255, 255, 255, 0.08);
}

.add {
  display: grid;
  gap: 10px;
}

.row {
  display: grid;
  gap: 10px;
  grid-template-columns: 1fr 1fr 1fr;
}

label {
  display: grid;
  gap: 6px;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.85);
}

select,
input[type='number'],
input[type='file'] {
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(0, 0, 0, 0.2);
  color: rgba(255, 255, 255, 0.92);
}

.file {
  border: 1px dashed rgba(255, 255, 255, 0.2);
  border-radius: 12px;
  padding: 10px;
}

.cta {
  display: flex;
  gap: 10px;
}

.primary {
  background: rgba(96, 165, 250, 0.2);
  border-color: rgba(96, 165, 250, 0.45);
}

.status {
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.04);
}

.error {
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid rgba(255, 77, 77, 0.25);
  background: rgba(255, 77, 77, 0.08);
}

@media (max-width: 980px) {
  .row {
    grid-template-columns: 1fr;
  }
}
</style>
