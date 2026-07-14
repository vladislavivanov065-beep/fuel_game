import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  preview: {
    // Railway assigns a random *.up.railway.app subdomain per deploy;
    // allow the whole domain instead of hardcoding one that will change.
    allowedHosts: ['.up.railway.app'],
  },
})
