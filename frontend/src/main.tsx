import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { Analytics } from '@vercel/analytics/react'
import { SpeedInsights } from '@vercel/speed-insights/react'
import './index.css'
import App from './App.tsx'

// Solo miden visitas y rendimiento de la página publicada; no reciben datos de la cuenta
const onVercel = window.location.hostname.endsWith('.vercel.app')

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
    {onVercel && <Analytics />}
    {onVercel && <SpeedInsights />}
  </StrictMode>,
)
