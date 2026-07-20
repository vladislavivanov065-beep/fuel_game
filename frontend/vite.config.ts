import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  preview: {
    // Railway assigns a random *.up.railway.app subdomain per deploy;
    // allow the whole domain instead of hardcoding one that will change.
    // Railway's own healthcheck probe additionally connects using the Host
    // header "healthcheck.railway.app", which does NOT match that wildcard
    // (it's a distinct hostname on railway.app, not a *.up.railway.app
    // subdomain) — without it Vite returns 403 for every healthcheck
    // attempt and the deploy is marked unhealthy even though the app is up.
    allowedHosts: ['.up.railway.app', 'healthcheck.railway.app'],
  },
})
