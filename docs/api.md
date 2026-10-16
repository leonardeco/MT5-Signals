# API del motor

Base: `http://127.0.0.1:8765`. La documentación interactiva está en `/docs` mientras el motor corre.

**Permisos.** `GET` y WebSocket aceptan los orígenes de lectura y de operación. `POST` exige un origen con permiso de operar. Las peticiones sin cabecera `Origin` (scripts locales, curl) se aceptan porque solo pueden venir de este PC. Ver [Riesgo y seguridad](riesgo-y-seguridad.md#el-motor).

## Lectura

| Método | Ruta | Respuesta |
|---|---|---|
| GET | `/status` | `service` (`mt5-senales`), `version`, `can_trade` del origen que pregunta, `local_panel`, `mt5_connected`, `mt5_status`, `watchlist`, `magic`, `autotrading`, `bot_mode` |
| GET | `/market` | Última foto del escáner (igual que el WebSocket): cuenta, riesgo, señales, posiciones y bitácora |
| GET | `/candles/{symbol}?tf=M15&bars=300` | Velas y EMA 21/50/200. `tf`: M1, M5, M15, H1, H4, D1; `bars` entre 50 y 1500. `simulated: true` sin MT5 |
| GET | `/history` | Últimas 50 operaciones de la bitácora, con R, MAE/MFE y deslizamiento |
| GET | `/journal/stats` | Expectativa en R por símbolo frente a la media del backtest |
| GET | `/backtest` | Último backtest guardado y si hay un cálculo en curso |
| GET | `/forward` | Configuración congelada y último resultado de la prueba a futuro |

## WebSocket

| Ruta | Mensajes |
|---|---|
| `/ws/signals` | `MARKET_UPDATE` cada 1,5 s |
| `/ws/chart/{symbol}?tf=M15` | `TICK_BAR` cada 0,5 s con la vela en curso y las EMA |

Un origen no permitido recibe el cierre `1008`.

## Operación (requiere permiso de operar)

| Método | Ruta | Cuerpo | Notas |
|---|---|---|---|
| POST | `/execute` | `{symbol, direction, volume, sl, tp, tp1?, score?}` | 503 sin MT5, 403 con kill switch. El lote se recalcula en el servidor y solo puede bajar; con `tp1` se envían dos órdenes |
| POST | `/close/{ticket}` | — | Cierra una posición |
| POST | `/close-all` | — | Cierra solo las posiciones con el `MAGIC_NUMBER` del bot |
| POST | `/bot/autotrading` | `{enabled}` | No se puede activar con el kill switch bloqueado |
| POST | `/bot/mode` | `{mode}` | `SNIPER`, `INSTITUTIONAL` o `DYNAMIC` |
| POST | `/risk/reset` | — | Desbloquea el kill switch del día |
| POST | `/backtest/run?days=180` | — | Requiere MT5 |
| POST | `/forward/run` | — | Requiere MT5 y reglas congeladas |

## Errores

Todas las respuestas de error traen `{"detail": "..."}` en español, pensado para mostrarse tal cual en el panel. Un origen de solo lectura que intenta operar recibe 403 con `Este panel es de solo lectura. Opera desde http://localhost:5180`.
