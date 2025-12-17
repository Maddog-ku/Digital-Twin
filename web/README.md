# Digital Twin Web (Vue + Three.js)

This folder contains the new Vue 3 frontend for the Digital Twin backend.

## Run (dev)

1. Start the backend (Flask/SocketIO) on `http://localhost:5050`.
2. In this folder:

```bash
npm install
npm run dev
```

Vite is configured with a dev proxy, so the frontend can call:
- `GET /api/v1/home_config`
- `GET /api/v1/3d_model/latest?home_id=...`
- Socket.IO at `/twin`

without CORS issues during development (`web/vite.config.js`).

## First-time mesh

If you don't have a mesh persisted yet, you can:
- Open the **2D Plan** tab and click **Generate 3D**, or
- Call `POST /api/v1/generate_3d` manually and then load `latest`.

## Config

Optional env vars (Vite):
- `VITE_API_BASE_URL` (default: same origin, recommended for production)
- `VITE_SOCKET_BASE_URL` (default: same origin)
