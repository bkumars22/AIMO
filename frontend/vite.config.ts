import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: process.env.VITE_API_BASE_URL ?? 'http://localhost:8080',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
      '/ai': {
        target: process.env.VITE_AI_ENGINE_URL ?? 'http://localhost:8001',
        changeOrigin: true,
        ws: true,
        rewrite: (p) => p.replace(/^\/ai/, ''),
      },
    },
  },
})
