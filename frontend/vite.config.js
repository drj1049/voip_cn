import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Vite is the tool that runs the dev server and builds the dashboard.
// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  // Only used by "npm run dev". In production the backend serves the built files itself.
  server: {
    port: 3000,
    open: false
  }
})
