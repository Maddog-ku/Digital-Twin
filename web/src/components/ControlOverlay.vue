<template>
  <div class="overlay">
    <div class="title">顯示</div>
    <label class="row">
      <input type="checkbox" :checked="modelValue.floor" @change="toggle('floor', $event)" />
      地板
    </label>
    <label class="row">
      <input type="checkbox" :checked="modelValue.walls" @change="toggle('walls', $event)" />
      牆面
    </label>
    <label class="row">
      <input type="checkbox" :checked="modelValue.ceiling" @change="toggle('ceiling', $event)" />
      天花板
    </label>
    <label class="row">
      <input type="checkbox" :checked="modelValue.sensors" @change="toggle('sensors', $event)" />
      感測器
    </label>
    <div class="divider" />
    <label class="row">
      <input
        type="checkbox"
        :checked="modelValue.wireframe"
        @change="toggle('wireframe', $event)"
      />
      線框
    </label>
    <div class="divider" />
    <div class="subtitle">視角</div>
    <div class="modeRow">
      <button :class="{ active: cameraMode === 'orbit' }" @click="setCameraMode('orbit')">軌道</button>
      <button
        :class="{ active: cameraMode === 'first-person' }"
        @click="setCameraMode('first-person')"
      >
        第一人稱
      </button>
    </div>
    <label class="row">
      <input
        type="checkbox"
        :checked="isWallTransparent"
        @change="setWallTransparency($event.target.checked)"
      />
      半透明牆壁
    </label>
    <div class="slider">
      <div class="subtitle">樓層透明度</div>
      <input
        type="range"
        min="0.1"
        max="1"
        step="0.05"
        :value="floorOpacity"
        @input="setFloorOpacity($event.target.value)"
      />
      <div class="sliderValue">{{ (floorOpacity * 100).toFixed(0) }}%</div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  modelValue: {
    type: Object,
    required: true,
  },
})

const emit = defineEmits(['update:modelValue'])

const cameraMode = computed(() => props.modelValue?.cameraMode || 'orbit')
const isWallTransparent = computed(() => Number(props.modelValue?.wallOpacity ?? 1) < 0.99)
const floorOpacity = computed(() => {
  const raw = Number(props.modelValue?.floorOpacity ?? 1)
  if (!Number.isFinite(raw)) return 1
  return Math.min(1, Math.max(0.1, raw))
})

function setValue(partial) {
  emit('update:modelValue', {
    ...props.modelValue,
    ...partial,
  })
}

function toggle(key, event) {
  setValue({ [key]: event.target.checked })
}

function setCameraMode(mode) {
  setValue({ cameraMode: mode === 'first-person' ? 'first-person' : 'orbit' })
}

function setWallTransparency(checked) {
  const opacity = checked ? 0.35 : 1
  setValue({ wallOpacity: opacity, walls: true })
}

function setFloorOpacity(value) {
  const val = Math.min(1, Math.max(0.1, Number(value)))
  setValue({ floorOpacity: val, ceilingOpacity: val, floor: true, ceiling: true })
}
</script>

<style scoped>
.overlay {
  position: absolute;
  top: 12px;
  left: 12px;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(10, 16, 30, 0.7);
  backdrop-filter: blur(10px);
  font-size: 13px;
  color: rgba(255, 255, 255, 0.9);
  user-select: none;
}

.title {
  font-weight: 600;
  margin-bottom: 8px;
  letter-spacing: 0.2px;
}

.row {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 4px 0;
  cursor: pointer;
}

.divider {
  height: 1px;
  margin: 8px 0;
  background: rgba(255, 255, 255, 0.08);
}

.subtitle {
  font-weight: 600;
  margin-bottom: 6px;
  letter-spacing: 0.2px;
}

.modeRow {
  display: flex;
  gap: 8px;
  margin-bottom: 6px;
}

.modeRow button {
  flex: 1;
  padding: 6px 8px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.06);
  color: rgba(255, 255, 255, 0.9);
  cursor: pointer;
}

.modeRow button.active {
  background: rgba(96, 165, 250, 0.16);
  border-color: rgba(96, 165, 250, 0.4);
}

.slider {
  margin-top: 8px;
  display: grid;
  gap: 6px;
}

.slider input[type='range'] {
  width: 180px;
}

.sliderValue {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.75);
}

input[type='checkbox'] {
  accent-color: #60a5fa;
}
</style>
