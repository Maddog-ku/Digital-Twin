<template>
  <div class="floor-manager-container">
    <div class="panel-header">
      <h2>樓層管理 (CAD 模式)</h2>
    </div>

    <div class="floor-list">
      <div v-for="floor in floors" :key="floor.id" class="floor-item">
        <span class="floor-name">第 {{ floor.level }} 層</span>
        <div class="floor-actions">
          <button @click="$emit('toggle-floor', floor.id)">👁️</button>
        </div>
      </div>
    </div>

    <div class="upload-section">
      <h3>📂 匯入新樓層</h3>

      <div class="input-group">
        <label>選擇 DXF 檔案</label>
        <input
          type="file"
          ref="fileInput"
          accept=".dxf"
          @change="handleFileSelect"
        />
        <p v-if="selectedFile" class="file-name">已選擇: {{ selectedFile.name }}</p>
      </div>

      <div class="settings-grid">
        <div class="input-group">
          <label>樓層 (Level)</label>
          <input type="number" v-model.number="form.level" min="1" />
        </div>

        <div class="input-group">
          <label>樓高 (Height - m)</label>
          <input type="number" v-model.number="form.height" step="0.1" />
        </div>

        <div class="input-group">
          <label>牆壁圖層 (Layer Name)</label>
          <input
            type="text"
            v-model="form.targetLayer"
            placeholder="例如: WALL"
          />
          <small class="hint">請輸入 CAD 中畫牆壁的圖層名稱</small>
        </div>
      </div>

      <button
        class="upload-btn"
        :disabled="!selectedFile || isProcessing"
        @click="uploadDxf"
      >
        <span v-if="isProcessing">處理中...</span>
        <span v-else>生成 3D 模型</span>
      </button>

      <p v-if="errorMessage" class="error-msg">{{ errorMessage }}</p>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import axios from 'axios'

const emit = defineEmits(['floor-added', 'toggle-floor'])

const floors = ref([])
const selectedFile = ref(null)
const isProcessing = ref(false)
const errorMessage = ref('')
const fileInput = ref(null)

const form = reactive({
  level: 1,
  height: 3.0,
  targetLayer: 'WALL',
})

const handleFileSelect = (event) => {
  const file = event.target.files[0]
  errorMessage.value = ''

  if (!file) return

  if (!file.name.toLowerCase().endsWith('.dxf')) {
    errorMessage.value = '錯誤：請上傳 .dxf 格式的 CAD 檔案'
    selectedFile.value = null
    event.target.value = ''
    return
  }

  selectedFile.value = file
}

const uploadDxf = async () => {
  if (!selectedFile.value) return

  isProcessing.value = true
  errorMessage.value = ''

  const formData = new FormData()
  formData.append('file', selectedFile.value)
  formData.append('level', form.level)
  formData.append('height', form.height)
  formData.append('target_layers', form.targetLayer)

  try {
    const response = await axios.post(
      'http://localhost:5050/api/v1/auto_generate_from_dxf',
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      }
    )

    const newFloorData = response.data.data

    floors.value.push({
      id: newFloorData.id,
      level: newFloorData.level,
      raw: newFloorData,
    })

    floors.value.sort((a, b) => a.level - b.level)

    emit('floor-added', newFloorData)

    form.level += 1
    selectedFile.value = null
    if (fileInput.value) fileInput.value.value = ''
    alert('匯入成功！')
  } catch (error) {
    console.error(error)
    const msg = error.response?.data?.error || '上傳失敗，請檢查後端連線'
    errorMessage.value = msg
  } finally {
    isProcessing.value = false
  }
}
</script>

<style scoped>
.floor-manager-container {
  padding: 20px;
  background: #1e1e1e;
  color: #fff;
  border-radius: 8px;
  max-width: 400px;
}

.panel-header h2 {
  margin: 0 0 10px 0;
}

.floor-list {
  margin-bottom: 20px;
}

.floor-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px;
  background: #2a2a2a;
  border-radius: 6px;
  margin-bottom: 8px;
}

.floor-actions button {
  background: transparent;
  border: none;
  color: #fff;
  cursor: pointer;
}

.upload-section h3 {
  margin-top: 0;
}

.input-group {
  margin-bottom: 15px;
  display: flex;
  flex-direction: column;
}

.input-group label {
  font-size: 0.9em;
  color: #aaa;
  margin-bottom: 5px;
}

.input-group input {
  padding: 8px;
  background: #333;
  border: 1px solid #555;
  color: white;
  border-radius: 4px;
}

.settings-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.upload-btn {
  width: 100%;
  padding: 10px;
  background-color: #4caf50;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-weight: bold;
}

.upload-btn:disabled {
  background-color: #555;
  cursor: not-allowed;
}

.error-msg {
  color: #ff6b6b;
  font-size: 0.9em;
  margin-top: 10px;
}

.hint {
  font-size: 0.8em;
  color: #666;
}

.file-name {
  margin: 6px 0 0 0;
  font-size: 12px;
  color: #b3b3b3;
}
</style>
