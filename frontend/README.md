# Panel de MT5 Señales

React 19 + Vite 8 + [lightweight-charts](https://github.com/tradingview/lightweight-charts).

```powershell
npm ci
npm run dev       # http://localhost:5180
npm run build     # dist/
npm run preview   # http://localhost:4180
npm run lint
```

- `src/api.ts` concentra la dirección del motor (por defecto `http://127.0.0.1:8765`), la comprobación de identidad (`/status` → `service: mt5-senales`) y los WebSocket.
- `vercel.json` define los encabezados de seguridad del panel publicado.

Arquitectura completa en [../docs/arquitectura.md](../docs/arquitectura.md).
