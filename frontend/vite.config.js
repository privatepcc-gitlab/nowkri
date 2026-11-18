import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// /api calls are forwarded to the FastAPI backend on port 8001
export default defineConfig({
  plugins: [react()],
  server: { host: '127.0.0.1', port: 5173, proxy: { '/api': 'http://127.0.0.1:8001' } },
})
