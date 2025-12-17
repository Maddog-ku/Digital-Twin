<template>
  <div class="overlay">
    <div class="title">View</div>
    <label class="row">
      <input type="checkbox" :checked="modelValue.floor" @change="toggle('floor', $event)" />
      Floor
    </label>
    <label class="row">
      <input type="checkbox" :checked="modelValue.walls" @change="toggle('walls', $event)" />
      Walls
    </label>
    <label class="row">
      <input type="checkbox" :checked="modelValue.ceiling" @change="toggle('ceiling', $event)" />
      Ceiling
    </label>
    <label class="row">
      <input type="checkbox" :checked="modelValue.sensors" @change="toggle('sensors', $event)" />
      Sensors
    </label>
    <div class="divider" />
    <label class="row">
      <input
        type="checkbox"
        :checked="modelValue.wireframe"
        @change="toggle('wireframe', $event)"
      />
      Wireframe
    </label>
  </div>
</template>

<script setup>
const props = defineProps({
  modelValue: {
    type: Object,
    required: true,
  },
})

const emit = defineEmits(['update:modelValue'])

function toggle(key, event) {
  emit('update:modelValue', {
    ...props.modelValue,
    [key]: event.target.checked,
  })
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

input[type='checkbox'] {
  accent-color: #60a5fa;
}
</style>

