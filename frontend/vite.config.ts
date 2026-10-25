import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // Dev: the app calls same-origin /api which is proxied to the backend.
      // Prod build: the API base is absolute (http://localhost:8000/api) because
      // the backend serves dist/ at "/".
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
