import { io } from 'socket.io-client'

export function createTwinSocket() {
  const base = import.meta.env.VITE_SOCKET_BASE_URL || ''
  const url = base ? `${base}/twin` : '/twin'

  return io(url, {
    path: '/socket.io',
    transports: ['websocket', 'polling'],
    reconnection: true,
    reconnectionAttempts: Infinity,
    reconnectionDelayMax: 2000,
  })
}

