<template>
  <div class="wrap">
    <div class="tabs">
      <button :class="{ active: mode === 'form' }" @click="mode = 'form'">Form</button>
      <button :class="{ active: mode === 'json' }" @click="mode = 'json'">JSON</button>
    </div>

    <div class="hint">
      <div class="mono">POST /api/v1/generate_3d</div>
      <div class="muted">
        Define <span class="mono">rooms[].polygon</span> and <span class="mono">rooms[].openings</span>
        then generate a mesh.
      </div>
    </div>

    <div v-if="mode === 'form'" class="form">
      <div class="row">
        <label class="field">
          <span>Room ID</span>
          <input v-model.trim="roomId" />
        </label>
        <label class="field">
          <span>Name</span>
          <input v-model.trim="roomName" />
        </label>
      </div>

      <div class="row">
        <label class="field">
          <span>Wall Height</span>
          <input v-model.number="wallHeight" type="number" step="0.1" min="0.1" />
        </label>
        <label class="field">
          <span>Wall Thickness</span>
          <input v-model.number="wallThickness" type="number" step="0.01" min="0.01" />
        </label>
      </div>

      <div class="row">
        <label class="check">
          <input v-model="useCsg" type="checkbox" />
          Use CSG (trimesh+shapely)
        </label>
      </div>

      <div class="section">
        <div class="sectionHead">
          <div class="title">Polygon (x, y)</div>
          <div class="actions">
            <button @click="addPoint">Add Point</button>
            <button @click="autoFitPolygon">Auto-fit to sensors</button>
          </div>
        </div>

        <div class="table">
          <div v-for="(p, idx) in polygon" :key="idx" class="tableRow">
            <div class="idx mono">{{ idx + 1 }}</div>
            <input v-model.number="p.x" type="number" step="0.1" />
            <input v-model.number="p.y" type="number" step="0.1" />
            <button class="danger" @click="removePoint(idx)">×</button>
          </div>
        </div>

        <canvas ref="previewCanvas" class="preview" width="320" height="180"></canvas>
      </div>

      <div class="section">
        <div class="sectionHead">
          <div class="title">Openings (doors/windows)</div>
          <div class="actions">
            <button @click="addOpening">Add</button>
          </div>
        </div>

        <div class="openings">
          <div v-for="(op, idx) in openings" :key="op.id" class="opening">
            <div class="openingHead">
              <div class="mono">{{ op.id }}</div>
              <button class="danger" @click="removeOpening(idx)">Remove</button>
            </div>
            <div class="grid">
              <label>
                <span>Type</span>
                <select v-model="op.type">
                  <option value="door">door</option>
                  <option value="window">window</option>
                </select>
              </label>
              <label>
                <span>Center X</span>
                <input v-model.number="op.cx" type="number" step="0.1" />
              </label>
              <label>
                <span>Center Y</span>
                <input v-model.number="op.cy" type="number" step="0.1" />
              </label>
              <label>
                <span>Width</span>
                <input v-model.number="op.width" type="number" step="0.1" min="0.01" />
              </label>
              <label>
                <span>Height</span>
                <input v-model.number="op.height" type="number" step="0.1" min="0.01" />
              </label>
              <label>
                <span>Bottom</span>
                <input v-model.number="op.bottom" type="number" step="0.1" min="0" />
              </label>
            </div>
          </div>
        </div>
      </div>

      <div class="cta">
        <button :disabled="submitting || !formReady" class="primary" @click="generate(formPayload)">
          {{ submitting ? 'Generating…' : 'Generate 3D' }}
        </button>
        <button :disabled="submitting" @click="copyPreviewJson">Copy JSON</button>
        <button :disabled="submitting" @click="resetForm">Reset</button>
      </div>

      <details class="details">
        <summary>Payload preview</summary>
        <pre class="mono">{{ previewJson }}</pre>
      </details>
    </div>

    <div v-else class="json">
      <div class="row">
        <input ref="fileInput" class="file" type="file" accept="application/json" @change="onFile" />
        <button @click="setJsonTemplate">Load template</button>
      </div>

      <textarea v-model="jsonText" class="textarea mono" spellcheck="false"></textarea>

      <div class="cta">
        <button :disabled="submitting" class="primary" @click="generateFromJson">
          {{ submitting ? 'Generating…' : 'Generate 3D' }}
        </button>
      </div>
    </div>

    <div v-if="status" class="status mono">{{ status }}</div>
    <div v-if="error" class="error mono">{{ error }}</div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'

import { api } from '../services/api'

const props = defineProps({
  homeId: { type: String, required: true },
  sensors: { type: Array, default: () => [] },
})

const emit = defineEmits(['generated'])

const mode = ref('form')
const submitting = ref(false)
const status = ref('')
const error = ref('')

const wallHeight = ref(2.8)
const wallThickness = ref(0.12)
const useCsg = ref(false)

const roomId = ref('room_1')
const roomName = ref('Room')

const polygon = ref([
  { x: 0, y: 0 },
  { x: 4, y: 0 },
  { x: 4, y: 3 },
  { x: 0, y: 3 },
])

const openings = ref([
  { id: 'door_1', type: 'door', cx: 2, cy: 0, width: 0.9, height: 2.1, bottom: 0 },
])

const previewCanvas = ref(null)

const formReady = computed(() => polygon.value.length >= 3 && roomId.value.trim().length > 0)

const formPayload = computed(() => {
  return {
    home_id: props.homeId,
    params: {
      wall_height: Number(wallHeight.value || 2.8),
      wall_thickness: Number(wallThickness.value || 0.12),
      use_csg: Boolean(useCsg.value),
    },
    rooms: [
      {
        id: roomId.value,
        name: roomName.value || undefined,
        polygon: polygon.value.map((p) => [Number(p.x || 0), Number(p.y || 0)]),
        openings: openings.value.map((op) => ({
          id: op.id,
          type: op.type,
          center: [Number(op.cx || 0), Number(op.cy || 0)],
          width: Number(op.width || 0.9),
          height: Number(op.height || 2.1),
          bottom: Number(op.bottom || 0),
        })),
      },
    ],
  }
})

const previewJson = computed(() => JSON.stringify(formPayload.value, null, 2))

const jsonText = ref('')

function setJsonTemplate() {
  jsonText.value = previewJson.value
}

function addPoint() {
  const last = polygon.value[polygon.value.length - 1] || { x: 0, y: 0 }
  polygon.value.push({ x: Number(last.x) + 1, y: Number(last.y) })
}

function removePoint(index) {
  polygon.value.splice(index, 1)
}

function addOpening() {
  const nextId = `opening_${openings.value.length + 1}`
  openings.value.push({ id: nextId, type: 'window', cx: 2, cy: 1.5, width: 1.2, height: 1.0, bottom: 1 })
}

function removeOpening(index) {
  openings.value.splice(index, 1)
}

function resetForm() {
  roomId.value = 'room_1'
  roomName.value = 'Room'
  wallHeight.value = 2.8
  wallThickness.value = 0.12
  useCsg.value = false
  polygon.value = [
    { x: 0, y: 0 },
    { x: 4, y: 0 },
    { x: 4, y: 3 },
    { x: 0, y: 3 },
  ]
  openings.value = [
    { id: 'door_1', type: 'door', cx: 2, cy: 0, width: 0.9, height: 2.1, bottom: 0 },
  ]
}

function autoFitPolygon() {
  const locations = (props.sensors || [])
    .map((s) => s.location)
    .filter((loc) => Array.isArray(loc) && loc.length >= 2)

  if (!locations.length) {
    polygon.value = [
      { x: 0, y: 0 },
      { x: 4, y: 0 },
      { x: 4, y: 3 },
      { x: 0, y: 3 },
    ]
    return
  }

  const xs = locations.map((l) => Number(l[0] || 0))
  const ys = locations.map((l) => Number(l[1] || 0))
  const minX = Math.min(...xs) - 1
  const maxX = Math.max(...xs) + 1
  const minY = Math.min(...ys) - 1
  const maxY = Math.max(...ys) + 1

  polygon.value = [
    { x: minX, y: minY },
    { x: maxX, y: minY },
    { x: maxX, y: maxY },
    { x: minX, y: maxY },
  ]
}

async function generate(payload) {
  error.value = ''
  status.value = ''
  submitting.value = true
  try {
    const resp = await api.generate3D(payload)
    const meshId = resp?.result?.mesh_id
    if (!meshId) throw new Error('mesh_id missing from /generate_3d response')

    const model = await api.get3DModel(meshId)
    status.value = `generated: ${meshId}`
    emit('generated', model)
  } catch (e) {
    error.value = e?.response?.data?.error || e?.message || 'Failed to generate 3D'
  } finally {
    submitting.value = false
  }
}

function copyPreviewJson() {
  navigator.clipboard?.writeText(previewJson.value)
  status.value = 'copied payload JSON'
}

function parseJsonText() {
  try {
    const obj = JSON.parse(jsonText.value || '')
    if (!obj || typeof obj !== 'object') throw new Error('payload must be a JSON object')
    if (!obj.home_id) obj.home_id = props.homeId
    return obj
  } catch (e) {
    throw new Error(e?.message || 'Invalid JSON')
  }
}

async function generateFromJson() {
  try {
    const payload = parseJsonText()
    await generate(payload)
  } catch (e) {
    error.value = e?.message || 'Invalid JSON'
  }
}

function onFile(event) {
  const file = event?.target?.files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = () => {
    jsonText.value = String(reader.result || '')
  }
  reader.readAsText(file)
}

function drawPreview() {
  const canvas = previewCanvas.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  if (!ctx) return

  const w = canvas.width
  const h = canvas.height
  ctx.clearRect(0, 0, w, h)

  const pts = polygon.value.map((p) => [Number(p.x || 0), Number(p.y || 0)])
  if (pts.length < 2) return

  const xs = pts.map((p) => p[0])
  const ys = pts.map((p) => p[1])
  const minX = Math.min(...xs)
  const maxX = Math.max(...xs)
  const minY = Math.min(...ys)
  const maxY = Math.max(...ys)

  const pad = 12
  const spanX = Math.max(1e-6, maxX - minX)
  const spanY = Math.max(1e-6, maxY - minY)
  const scale = Math.min((w - pad * 2) / spanX, (h - pad * 2) / spanY)

  const toCanvas = (x, y) => {
    const cx = pad + (x - minX) * scale
    const cy = h - (pad + (y - minY) * scale)
    return [cx, cy]
  }

  // Polygon fill
  ctx.beginPath()
  pts.forEach((p, idx) => {
    const [cx, cy] = toCanvas(p[0], p[1])
    if (idx === 0) ctx.moveTo(cx, cy)
    else ctx.lineTo(cx, cy)
  })
  ctx.closePath()
  ctx.fillStyle = 'rgba(96, 165, 250, 0.10)'
  ctx.strokeStyle = 'rgba(96, 165, 250, 0.80)'
  ctx.lineWidth = 2
  ctx.fill()
  ctx.stroke()

  // Points
  ctx.fillStyle = 'rgba(255, 255, 255, 0.9)'
  pts.forEach((p, idx) => {
    const [cx, cy] = toCanvas(p[0], p[1])
    ctx.beginPath()
    ctx.arc(cx, cy, 3, 0, Math.PI * 2)
    ctx.fill()
    ctx.fillStyle = 'rgba(255, 255, 255, 0.75)'
    ctx.font = '11px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace'
    ctx.fillText(String(idx + 1), cx + 6, cy - 6)
    ctx.fillStyle = 'rgba(255, 255, 255, 0.9)'
  })

  // Openings
  ctx.fillStyle = 'rgba(255, 176, 32, 0.85)'
  for (const op of openings.value) {
    const [cx, cy] = toCanvas(Number(op.cx || 0), Number(op.cy || 0))
    ctx.beginPath()
    ctx.arc(cx, cy, 4, 0, Math.PI * 2)
    ctx.fill()
  }
}

watch(
  () => [polygon.value, openings.value],
  () => drawPreview(),
  { deep: true }
)

watch(
  () => mode.value,
  (m) => {
    if (m === 'json' && !jsonText.value) {
      setJsonTemplate()
    }
  }
)

onMounted(() => {
  drawPreview()
})
</script>

<style scoped>
.wrap {
  padding: 14px;
}

.tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
}

.tabs button {
  padding: 7px 10px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(255, 255, 255, 0.04);
  color: rgba(255, 255, 255, 0.85);
  cursor: pointer;
}

.tabs button.active {
  background: rgba(96, 165, 250, 0.16);
  border-color: rgba(96, 165, 250, 0.4);
}

.hint {
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.03);
  margin-bottom: 12px;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono',
    'Courier New', monospace;
}

.muted {
  color: rgba(255, 255, 255, 0.65);
  font-size: 13px;
  margin-top: 4px;
}

.row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin-bottom: 10px;
}

.field span {
  display: block;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.7);
  margin-bottom: 6px;
}

input,
select,
textarea {
  width: 100%;
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(0, 0, 0, 0.2);
  color: rgba(255, 255, 255, 0.9);
  box-sizing: border-box;
}

.check {
  grid-column: 1 / -1;
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.8);
}

.check input {
  width: auto;
}

.section {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.sectionHead {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}

.title {
  font-weight: 700;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.9);
}

.actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.actions button {
  padding: 6px 9px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(255, 255, 255, 0.04);
  color: rgba(255, 255, 255, 0.85);
  cursor: pointer;
  font-size: 12px;
}

.table {
  display: grid;
  gap: 8px;
}

.tableRow {
  display: grid;
  grid-template-columns: 28px 1fr 1fr 34px;
  gap: 8px;
  align-items: center;
}

.idx {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.7);
}

.danger {
  border: 1px solid rgba(255, 77, 77, 0.25);
  background: rgba(255, 77, 77, 0.1);
  color: rgba(255, 255, 255, 0.9);
  cursor: pointer;
}

.preview {
  width: 100%;
  height: 180px;
  margin-top: 10px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(0, 0, 0, 0.2);
}

.openings {
  display: grid;
  gap: 10px;
}

.opening {
  padding: 10px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.03);
}

.openingHead {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.grid span {
  display: block;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.7);
  margin-bottom: 6px;
}

.cta {
  display: flex;
  gap: 10px;
  margin-top: 14px;
}

.primary {
  background: rgba(96, 165, 250, 0.2);
  border: 1px solid rgba(96, 165, 250, 0.45);
}

.primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.details {
  margin-top: 12px;
}

.details pre {
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.8);
  padding: 10px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(0, 0, 0, 0.2);
  overflow: auto;
}

.json .textarea {
  height: 320px;
  resize: vertical;
}

.file {
  grid-column: 1 / -1;
}

.status {
  margin-top: 12px;
  padding: 10px;
  border-radius: 12px;
  border: 1px solid rgba(34, 197, 94, 0.25);
  background: rgba(34, 197, 94, 0.1);
  font-size: 12px;
}

.error {
  margin-top: 12px;
  padding: 10px;
  border-radius: 12px;
  border: 1px solid rgba(255, 77, 77, 0.25);
  background: rgba(255, 77, 77, 0.1);
  font-size: 12px;
}

@media (max-width: 980px) {
  .row {
    grid-template-columns: 1fr;
  }
  .cta {
    flex-direction: column;
  }
  .grid {
    grid-template-columns: 1fr;
  }
}
</style>

