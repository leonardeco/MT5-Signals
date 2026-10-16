# Despliegue

## Piezas

| Pieza | Dónde vive | Cómo se actualiza |
|---|---|---|
| Motor | Este PC, junto a MetaTrader 5 | `git pull` y reiniciar `start_terminal.bat` |
| Panel local | Este PC (`localhost:5180`) | Vite recarga solo al cambiar el código |
| Panel publicado | [mt5-signals.vercel.app](https://mt5-signals.vercel.app) | Automático en cada push a `main` |
| Código | [github.com/leonardeco/MT5-Signals](https://github.com/leonardeco/MT5-Signals) | Push |

El motor no se puede llevar a Vercel: la librería `MetaTrader5` habla con el terminal por memoria compartida en Windows, y Vercel ejecuta funciones Linux efímeras.

## Vercel

| Ajuste | Valor |
|---|---|
| Proyecto | `mt5-signals` |
| Root Directory | `frontend` |
| Framework | Vite (`npm run build` → `dist`) |
| Rama de producción | `main` |
| Previews | Una URL por cada pull request |
| Configuración | `frontend/vercel.json`: encabezados de seguridad y caché inmutable de `/assets` |

Variable opcional: `VITE_API_BASE` cambia la dirección por defecto del motor en el build. Sin ella se usa `http://127.0.0.1:8765`, y cada navegador puede cambiarla con el engranaje.

## Permisos del panel publicado

El motor lee `allowed_origins.local`, que no se sube a git:

```text
https://mt5-signals.vercel.app            # solo lectura
https://mt5-signals.vercel.app operar     # también envía órdenes
```

Después de editarlo hay que reiniciar el motor. La plantilla está en `allowed_origins.local.example`. Antes de añadir `operar`, lee [por qué es de solo lectura](riesgo-y-seguridad.md#por-qué-el-panel-publicado-es-de-solo-lectura).

## CI

`.github/workflows/ci.yml`, en cada push y pull request:

- **Motor**: `pytest` en `windows-latest`, porque `MetaTrader5` solo se publica para Windows. Los tests no necesitan el terminal; los que requieren la caché de historial se saltan solos.
- **Panel**: `npm ci`, `npm run lint` y `npm run build`.

## Integraciones

Activas:

| Integración | Para qué |
|---|---|
| Despliegue continuo desde GitHub | Cada push a `main` publica; cada PR tiene su preview |
| Vercel Web Analytics | Visitas a la página publicada, sin cookies. No recibe datos de la cuenta |
| Vercel Speed Insights | Core Web Vitals reales del panel |
| Encabezados de seguridad | CSP, anti-iframe, `nosniff`, `no-referrer` |

Para que Analytics y Speed Insights muestren datos, deben estar habilitados en el panel de Vercel: proyecto → *Analytics* y *Speed Insights* → *Enable*.

Posibles siguientes pasos, en orden de valor:

1. **Alertas al móvil desde el motor** (Telegram o push) cuando una señal pase a ACTIVADA o salte el kill switch. Va en el motor, no en Vercel: Vercel no ve tu PC.
2. **Acceso remoto privado con Tailscale** para mirar el panel desde el móvil, añadiendo antes un token en el motor. No uses un túnel público.
3. **Dominio propio** en Vercel, si quieres una URL fija y fácil de recordar. Recuerda añadirlo a `allowed_origins.local`.
