/// <reference types="vitest" />
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  test: {
    environment: "jsdom",
    globals: true,
  },
  plugins: [react()],
})
