import { defineConfig } from 'vite'
import preact from '@preact/preset-vite'

export default defineConfig({
  plugins: [preact()],
  server: {
    port: 5176,
    proxy: {
      '/health': 'http://127.0.0.1:9100',
      '/agent': 'http://127.0.0.1:9100',
    },
  },
  build: {
    outDir: 'dist',
  },
})
