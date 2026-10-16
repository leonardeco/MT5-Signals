import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Puertos propios: 5173/8000 los usan otros proyectos de este PC.
// strictPort: si el puerto está ocupado Vite falla en vez de saltar a otro que el motor no acepta.
export default defineConfig({
  plugins: [react()],
  server: { port: 5180, strictPort: true },
  preview: { port: 4180, strictPort: true },
})
