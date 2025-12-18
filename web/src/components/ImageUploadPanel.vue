<template>
  <div class="card">
    <div class="head">
      <div>
        <div class="title">圖片上傳產生 3D</div>
        <div class="hint mono">POST /api/v1/auto_generate_from_image</div>
      </div>
      <div class="homeId">
        <div class="label">Home ID</div>
        <div class="mono value">{{ homeId }}</div>
      </div>
    </div>

    <div class="grid">
      <label class="field">
        <span>平面圖圖片（png/jpg）</span>
        <input ref="fileInput" type="file" accept="image/*" @change="onFile" />
        <div v-if="fileName" class="muted">已選擇：{{ fileName }}</div>
      </label>
      <label class="field">
        <span>比例標定（實際長度，單位：公尺）</span>
        <input
          v-model.number="pixelToMeterRatio"
          type="number"
          step="0.01"
          min="0.01"
          placeholder="例：門寬 0.90"
        />
        <div class="muted">
          將實際長度換算成 <span class="mono">pixel_to_meter_ratio</span> 傳給後端，避免模型失真。
        </div>
      </label>
    </div>

    <div class="cta">
      <button class="primary" :disabled="!ready || submitting" @click="submit">
        {{ submitting ? '產生中…' : '上傳並生成' }}
      </button>
      <button :disabled="submitting" @click="reset">重設</button>
    </div>

    <div v-if="status" class="status mono">{{ status }}</div>
    <div v-if="error" class="error mono">{{ error }}</div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'

import { api } from '../services/api'

const props = defineProps({
  homeId: { type: String, required: true },
})

const emit = defineEmits(['generated'])

const fileInput = ref(null)
const file = ref(null)
const pixelToMeterRatio = ref(0.9)

const submitting = ref(false)
const status = ref('')
const error = ref('')

const ready = computed(() => {
  return Boolean(file.value) && Number(pixelToMeterRatio.value) > 0
})

const fileName = computed(() => (file.value ? `${file.value.name}（${fmtSize(file.value.size)}）` : ''))

function fmtSize(bytes) {
  if (!Number.isFinite(bytes)) return '0B'
  if (bytes < 1024) return `${bytes}B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`
  return `${(bytes / 1024 / 1024).toFixed(1)}MB`
}

function onFile(event) {
  file.value = event?.target?.files?.[0] || null
  status.value = ''
  error.value = ''
}

function reset() {
  file.value = null
  pixelToMeterRatio.value = 0.9
  status.value = ''
  error.value = ''
  if (fileInput.value) fileInput.value.value = ''
}

async function submit() {
  error.value = ''
  status.value = ''
  if (!ready.value) {
    error.value = '請選擇圖片並填入比例'
    return
  }

  const form = new FormData()
  form.append('image', file.value)
  form.append('pixel_to_meter_ratio', String(pixelToMeterRatio.value))
  if (props.homeId) {
    form.append('home_id', props.homeId)
  }

  submitting.value = true
  try {
    const resp = await api.autoGenerateFromImage(form)
    const meshId = resp?.result?.mesh_id || resp?.mesh_id
    if (!meshId) throw new Error('回應缺少 mesh_id')

    status.value = `生成完成：${meshId}`
    const model = await api.get3DModel(meshId)
    emit('generated', model)
  } catch (e) {
    error.value = e?.response?.data?.error || e?.message || '上傳或生成 3D 失敗'
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.card {
  position: relative;
  padding: 16px;
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(10, 16, 30, 0.7);
  backdrop-filter: blur(10px);
  color: rgba(255, 255, 255, 0.9);
}

.head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.title {
  font-weight: 800;
  letter-spacing: 0.4px;
}

.hint {
  color: rgba(255, 255, 255, 0.65);
  font-size: 12px;
  margin-top: 4px;
}

.homeId {
  text-align: right;
}

.label {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.65);
  letter-spacing: 0.4px;
}

.value {
  font-size: 12px;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono',
    'Courier New', monospace;
}

.grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.field {
  display: grid;
  gap: 8px;
  font-size: 13px;
}

.field span {
  color: rgba(255, 255, 255, 0.75);
}

input[type='file'] {
  padding: 10px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.03);
  color: rgba(255, 255, 255, 0.9);
}

input[type='number'] {
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(0, 0, 0, 0.25);
  color: rgba(255, 255, 255, 0.92);
}

.muted {
  color: rgba(255, 255, 255, 0.7);
}

.cta {
  margin-top: 14px;
  display: flex;
  gap: 10px;
}

button {
  padding: 8px 12px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(255, 255, 255, 0.08);
  color: rgba(255, 255, 255, 0.9);
  cursor: pointer;
}

.primary {
  background: rgba(96, 165, 250, 0.2);
  border-color: rgba(96, 165, 250, 0.4);
}

button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
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
  .grid {
    grid-template-columns: 1fr;
  }
  .head {
    flex-direction: column;
  }
  .homeId {
    text-align: left;
  }
}
</style>
