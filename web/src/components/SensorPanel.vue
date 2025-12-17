<template>
  <div class="wrap">
    <div class="section">
      <div class="k">Security</div>
      <div class="v">
        <span class="pill" :class="statusClass">{{ securityStatus || 'unknown' }}</span>
      </div>
    </div>

    <div class="section">
      <div class="k">Mesh</div>
      <div class="v">
        <div v-if="meshInfo?.mesh_id">
          <div class="mono">{{ meshInfo.mesh_id }}</div>
          <div class="muted">{{ meshInfo.created_at || '' }}</div>
        </div>
        <div v-else class="muted">No mesh loaded</div>
      </div>
    </div>

    <div class="section">
      <div class="k">World Offset</div>
      <div class="v mono">
        x={{ fmt(worldOffset?.x) }}, y={{ fmt(worldOffset?.y) }}, z={{ fmt(worldOffset?.z) }}
      </div>
    </div>

    <div class="section">
      <div class="k">Connection</div>
      <div class="v muted">
        API: {{ connected?.api ? 'ok' : '—' }} · Socket: {{ connected?.socket ? 'ok' : '—' }}
      </div>
    </div>

    <div class="section">
      <div class="k">Rooms</div>
      <div class="v muted">{{ rooms.length }} total · {{ sensors.length }} sensors</div>
    </div>

    <div class="rooms">
      <button
        v-for="room in rooms"
        :key="room.id"
        class="roomRow"
        :class="{ active: room.id === selectedRoomId, alert: room.alertCount > 0 }"
        @click="emit('selectRoom', room.id)"
      >
        <div class="roomTop">
          <div class="roomName">{{ room.name || room.id }}</div>
          <div v-if="room.alertCount > 0" class="badge">ALERT</div>
        </div>
        <div class="roomMeta muted">
          {{ room.sensors.length }} sensors · {{ room.alertCount }} alert
        </div>
      </button>
    </div>

    <div class="section">
      <div class="k">Selected</div>
      <div class="v">
        <div v-if="selectedRoom" class="selectedTitle">
          <div class="mono">{{ selectedRoom.id }}</div>
          <div class="muted">{{ selectedRoom.name || '' }}</div>
        </div>
        <div v-else class="muted">Click a room in 3D or select above.</div>
      </div>
    </div>

    <div v-if="selectedRoom" class="list">
      <div
        v-for="sensor in selectedRoom.sensors"
        :key="sensor.id"
        class="row"
        :class="{ alert: sensor.is_alert }"
      >
        <div class="id mono">{{ sensor.id }}</div>
        <div class="meta">
          <div class="line">
            <span class="type">{{ sensor.type }}</span>
            <span class="room muted">· {{ sensor.room_name || sensor.room_id || 'unknown room' }}</span>
          </div>
          <div class="status">{{ sensor.status }}</div>
          <div class="loc mono muted">
            {{ fmtLoc(sensor.location) }}
          </div>
        </div>
      </div>
    </div>

    <div v-if="errors?.length" class="errors">
      <div class="k">Errors</div>
      <div v-for="(e, idx) in errors" :key="idx" class="err mono">
        {{ e }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  sensors: { type: Array, default: () => [] },
  rooms: { type: Array, default: () => [] },
  selectedRoomId: { type: String, default: '' },
  securityStatus: { type: String, default: '' },
  meshInfo: { type: Object, default: null },
  worldOffset: { type: Object, default: null },
  errors: { type: Array, default: () => [] },
  connected: { type: Object, default: null },
})

const emit = defineEmits(['selectRoom'])

const statusClass = computed(() => {
  const s = (props.securityStatus || '').toLowerCase()
  if (s === 'critical') return 'critical'
  if (s === 'warning') return 'warning'
  if (s === 'safe') return 'safe'
  return 'unknown'
})

const selectedRoom = computed(() => {
  if (!props.selectedRoomId) return null
  return props.rooms.find((r) => String(r.id) === String(props.selectedRoomId)) || null
})

function fmt(value) {
  const n = Number(value)
  if (!Number.isFinite(n)) return '0.00'
  return n.toFixed(2)
}

function fmtLoc(location) {
  if (!location || !Array.isArray(location) || location.length < 2) return 'loc: —'
  const [x, y, z = 0] = location
  return `loc: [${fmt(x)}, ${fmt(y)}, ${fmt(z)}]`
}
</script>

<style scoped>
.wrap {
  padding: 14px 14px 20px;
}

.section {
  display: grid;
  grid-template-columns: 120px 1fr;
  gap: 10px;
  padding: 10px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.k {
  color: rgba(255, 255, 255, 0.75);
  font-weight: 600;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.6px;
}

.v {
  min-width: 0;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono',
    'Courier New', monospace;
}

.muted {
  color: rgba(255, 255, 255, 0.65);
  font-size: 13px;
}

.pill {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 999px;
  font-weight: 700;
  letter-spacing: 0.4px;
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.pill.safe {
  background: rgba(34, 197, 94, 0.12);
  color: rgba(34, 197, 94, 0.95);
}

.pill.warning {
  background: rgba(255, 176, 32, 0.12);
  color: rgba(255, 176, 32, 0.95);
}

.pill.critical {
  background: rgba(255, 77, 77, 0.14);
  color: rgba(255, 77, 77, 0.95);
}

.pill.unknown {
  background: rgba(255, 255, 255, 0.06);
  color: rgba(255, 255, 255, 0.8);
}

.list {
  padding: 10px 0 0;
  display: grid;
  gap: 8px;
}

.rooms {
  display: grid;
  gap: 8px;
  padding: 10px 0 4px;
}

.roomRow {
  text-align: left;
  padding: 10px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(255, 255, 255, 0.03);
  color: rgba(255, 255, 255, 0.92);
  cursor: pointer;
}

.roomRow.active {
  border-color: rgba(96, 165, 250, 0.35);
  background: rgba(96, 165, 250, 0.08);
}

.roomRow.alert {
  border-color: rgba(255, 77, 77, 0.35);
  background: rgba(255, 77, 77, 0.08);
}

.roomTop {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.roomName {
  font-weight: 700;
  font-size: 13px;
}

.roomMeta {
  margin-top: 2px;
}

.badge {
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.4px;
  padding: 3px 8px;
  border-radius: 999px;
  background: rgba(255, 77, 77, 0.18);
  border: 1px solid rgba(255, 77, 77, 0.35);
  color: rgba(255, 255, 255, 0.92);
}

.selectedTitle {
  display: grid;
  gap: 2px;
}

.row {
  display: grid;
  grid-template-columns: 90px 1fr;
  gap: 10px;
  padding: 10px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(255, 255, 255, 0.03);
}

.row.alert {
  border-color: rgba(255, 77, 77, 0.35);
  background: rgba(255, 77, 77, 0.08);
}

.id {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.85);
}

.type {
  font-weight: 700;
  font-size: 13px;
}

.status {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.88);
}

.loc {
  font-size: 12px;
}

.errors {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.err {
  margin-top: 8px;
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid rgba(255, 77, 77, 0.25);
  background: rgba(255, 77, 77, 0.1);
  font-size: 12px;
  color: rgba(255, 255, 255, 0.9);
}
</style>
