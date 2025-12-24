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

  async autoGenerateFromDxf(formData) {
    const { data } = await client.post('/api/v1/auto_generate_from_dxf', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return data
  },

  async delete3DModel(meshId) {
    if (!meshId) return
    const { data } = await client.delete(`/api/v1/3d_model/${meshId}`)
    return data
  },

  async listFloors(homeId) {
    const { data } = await client.get(`/api/v1/homes/${homeId}/floors`)
    return data
  },

  async uploadFloor(homeId, formData) {
    const { data } = await client.post(`/api/v1/homes/${homeId}/floors`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return data
  },

  async deleteFloor(homeId, level) {
    const { data } = await client.delete(`/api/v1/homes/${homeId}/floors/${level}`)
    return data
  },
}
