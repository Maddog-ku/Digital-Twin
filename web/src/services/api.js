import axios from 'axios'

const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  timeout: 15_000,
})

export const api = {
  async getHomeConfig() {
    const { data } = await client.get('/api/v1/home_config')
    return data
  },

  async getLatest3DModel(homeId) {
    const { data } = await client.get('/api/v1/3d_model/latest', {
      params: { home_id: homeId },
    })
    return data
  },

  async get3DModel(meshId) {
    const { data } = await client.get(`/api/v1/3d_model/${meshId}`)
    return data
  },

  async generate3D(payload) {
    const { data } = await client.post('/api/v1/generate_3d', payload)
    return data
  },
}

