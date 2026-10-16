# Guía de uso

## Arranque

1. Abre MetaTrader 5 e inicia sesión. Mientras la prueba a futuro no termine, usa la cuenta demo.
2. Ejecuta `start_terminal.bat`.
3. Se abre [http://localhost:5180](http://localhost:5180). El encabezado debe decir **MT5 CONECTADO**.

| Puerto | Qué es |
|---|---|
| `127.0.0.1:8765` | Motor (FastAPI + MetaTrader 5). Solo escucha en este PC |
| `localhost:5180` | Panel local, el que puede operar |
| `localhost:4180` | `npm run preview` del build |

Estos puertos son propios a propósito: `8000` y `5173` los usa otro proyecto de este PC, y el panel acababa hablando con una API que no era la suya.

Arranque manual, si lo necesitas:

```powershell
python -m uvicorn main:app --host 127.0.0.1 --port 8765
cd frontend; npm run dev
```

## Rutina diaria

1. **Antes de la sesión** (02:00–15:00 hora de Colombia, lunes a viernes): comprueba que la banda roja «MT5 desconectado» no aparece y que el filtro de entorno no dice «Sin calendario».
2. **Durante la sesión**: el radar ordena las señales por score. El score describe confluencia técnica, **no** predice resultado. Lo que manda es el estado del plan:

   | Estado | Significado |
   |---|---|
   | PREPARANDO | Hay setup; el precio aún no llega a la zona |
   | EN ZONA | El precio está en la zona; falta el gatillo en M5 |
   | ACTIVADA | Gatillo confirmado: el plan se puede ejecutar durante 2 velas M5 |
   | EXPIRADA / INVALIDADA | Ventana cerrada o nivel de invalidación roto |
   | DESCARTADA | El plan no cumple las reglas de riesgo (stop demasiado corto o largo, poco recorrido) |

3. **Si ejecutas a mano**: el botón «Ejecutar» pide confirmación cuando el par no tiene ventaja demostrada. El motor recalcula el lote y nunca lo sube.
4. **Al cerrar el día**: revisa el diario (R, MAE/MFE) y, una vez por semana, pulsa «Calcular» en la prueba a futuro.

## Paneles

| Panel | Para qué |
|---|---|
| Encabezado | Balance, equidad, flotante, margen libre, PnL del día frente al kill switch, interruptor de auto-trading y dirección del motor (engranaje) |
| Gráfico | Velas M1 a D1 con EMA 21/50/200 y los niveles del plan seleccionado |
| QuantBot Copilot | Desglose del score en cinco pilares, filtros de entorno y bitácora en vivo |
| Radar de señales | Un plan por símbolo, con zona, SL, TP1/TP2, lote al 1 % y resultado histórico del mismo rango de score |
| Posiciones | Abiertas en MT5; cierre individual o de todas las del bot |
| Backtest | 180 días con costes, por símbolo, con tramos y embudo de setups |
| Prueba a futuro | Motor y H-B medidos solo después de la congelación de reglas |
| Diario | Últimas 50 operaciones, expectativa en R y comparación con el backtest |

## Panel publicado (Vercel)

[mt5-signals.vercel.app](https://mt5-signals.vercel.app) es la misma app. Funciona **solo en el PC del motor**, porque el navegador llama a `127.0.0.1:8765`.

- La primera vez, Chrome puede preguntar si la página puede acceder a dispositivos de tu red local. Pulsa «Permitir».
- Por defecto es de **solo lectura**: no muestra botones de ejecutar ni cerrar. Para operar, usa el panel local o lee [Despliegue](despliegue.md#permisos-del-panel-publicado).

## Problemas frecuentes

| Lo que ves | Causa | Qué hacer |
|---|---|---|
| «No encuentro el motor en http://127.0.0.1:8765» | El motor no corre | Ejecuta `start_terminal.bat`; revisa la ventana «MT5 Senales - Motor» |
| «En … responde otra aplicación» | Otro programa ocupa el puerto | Cierra ese programa o apunta el engranaje a la dirección correcta |
| Banda roja «MT5 desconectado» | Terminal cerrado o sin sesión | Abre MetaTrader e inicia sesión; el motor se reconecta solo cada 5 s |
| «Sin calendario» en las señales | El feed de noticias no respondió (a veces limita con 429) | Espera: reintenta cada 5 min y guarda la última descarga en `news_cache.json` para no depender de cada arranque |
| «Solo lectura» en Vercel | Comportamiento por defecto | Opera desde `localhost:5180` |
| El backtest no corre | MT5 desconectado o ya hay un cálculo en curso | Conecta MT5 y espera a que termine el anterior |
| `start_terminal.bat` dice «Otro programa ocupa el puerto 8765» | Hay otro servicio en ese puerto | `netstat -ano \| findstr :8765` muestra el PID que lo ocupa |
