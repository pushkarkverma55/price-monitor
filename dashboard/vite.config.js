import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// build straight into ../docs (GitHub Pages root); data JSONs live in docs/data
export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: './',
  build: {
    outDir: '../docs',
    emptyOutDir: false,
    copyPublicDir: false, // docs/data already holds the JSONs the scraper exports
  },
})
