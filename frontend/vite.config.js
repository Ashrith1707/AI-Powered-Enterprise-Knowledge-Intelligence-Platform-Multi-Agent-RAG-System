import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Development ports (do not change without updating the docs):
//   Frontend: http://localhost:5173
//   Backend:  http://127.0.0.1:8001  (proxied below)
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: false,
    allowedHosts: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    chunkSizeWarningLimit: 1200,
  },
})
