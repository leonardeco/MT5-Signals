# MT5 Quant — terminal de señales

Panel para leer el mercado en MetaTrader 5, medir si una idea tiene ventaja y, solo entonces, dejar que el auto-trading toque la cuenta. El motor corre en Windows, al lado del terminal. Vercel publica el panel; no puede ejecutar órdenes ni hablar con MetaTrader.

## Cómo operar

1. Abre MetaTrader 5 e inicia sesión (demo mientras la prueba a futuro no termine).
2. Doble clic en `start_terminal.bat`.
3. El panel queda en [http://localhost:5173](http://localhost:5173). El motor escucha solo en `127.0.0.1:8000`.

El engranaje del encabezado guarda otra dirección del motor. En este PC no hace falta cambiarla.

Sin el terminal abierto no hay precios reales: las velas de relleno no generan ni ejecutan señales.

## Qué está permitido operar solo

El auto-trading sigue apagado. Ningún par del motor intradía pasó el filtro (ambos tramos del backtest ≥ +0.05R, al menos 30 operaciones por tramo y t ≥ 2, con spread, comisión y deslizamiento).

La hipótesis con mejor resultado, tendencia de 12 meses en diario, dio +0.067R neto y t 2.22, pero el Sharpe deflactado quedó en 0.61, por debajo del 0.95 fijado antes de mirar los datos. No se automatiza. La prueba en sombra (`python forward.py run` o el panel «Prueba a futuro») mide esas reglas congeladas sin enviar órdenes.

Ejecutar a mano una señal pide confirmación y deja constancia de que es lectura de contexto.

## Reglas que no se negocian

Están en `docs/constitution.md`. Resumen: no auto-trading sin el filtro, costes en todo backtest, hipótesis registrada antes de correrla, tests en verde, y el cierre de emergencia solo toca las órdenes del bot (magic `202605`) salvo que lo confirmes.

## Publicar el panel

El build de `frontend/` es una página estática. Después de desplegarla:

1. Copia `allowed_origins.local.example` a `allowed_origins.local`.
2. Escribe la URL exacta del panel (por ejemplo `https://tu-proyecto.vercel.app`).
3. Reinicia `start_terminal.bat`.

El navegador solo puede unir esa página con el motor de este PC. Cualquier otro sitio sigue recibiendo 403 en las órdenes.

## Tests

```bash
python -m pytest tests -q
```

## Arranque manual

```bash
python -m uvicorn main:app --host 127.0.0.1 --port 8000
cd frontend && npm install && npm run dev
```
