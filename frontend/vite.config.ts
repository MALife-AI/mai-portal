import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: true, // 0.0.0.0 — WSL/외부 네트워크에서 접속 가능
    port: 5173,
    strictPort: false,
    proxy: {
      '/api': {
        target: 'http://localhost:9001',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://localhost:9001',
        changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          'react-vendor': ['react', 'react-dom', 'react-router-dom'],
          'motion': ['framer-motion'],
          'charts': ['recharts'],
          'markdown': ['react-markdown', 'remark-gfm'],
          'ui': ['lucide-react', 'clsx'],
          'state': ['zustand'],
        },
      },
    },
    chunkSizeWarningLimit: 600,
  },
})
