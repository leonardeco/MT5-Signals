# Diagnóstico profundo y hoja de ruta (15-oct-2026)

## 1. Veredicto en una frase

La ingeniería de la app es razonable (validación de órdenes, lote por riesgo real, kill switch, backtest que usa
el mismo código que el escáner). **El cuello de botella no es el código: es que la idea de entrada no tiene ventaja.**
Pulir la interfaz, añadir indicadores o filtros sobre este motor no va a volverla rentable: ya se probaron 20 variantes
y ninguna se sostiene fuera de muestra (`research/INFORME_VARIANTES.md`). Para que la app sea "muy efectiva" hace falta
**otra hipótesis de entrada, validada con más datos y costes reales**, y que la ejecución en vivo se parezca a lo que
se simuló.

Ningún trabajo de ingeniería puede garantizar rentabilidad. Lo que sí se puede garantizar es que la app no se engañe
a sí misma: que solo active el auto-trading cuando haya evidencia estadística, y que mida en vivo lo que el backtest supuso.

## 2. Qué dice la evidencia externa (resumen de la investigación)

| Tema | Evidencia | Implicación para la app |
|---|---|---|
| Reglas técnicas simples en FX (medias, filtros) | Dieron rentabilidad en los 70-80 y **desaparecieron a principios de los 90**; las reglas menos estudiadas también se han erosionado (Neely, Weller y Ulrich, JFQA 2009) | Confirma lo que encontró nuestro backtest: EMAs + RSI + MACD en M15 rondan 0R |
| SMC: order blocks, FVG, barridos de liquidez | **No hay estudios independientes** que muestren ventaja; casi todo es material de vendedores; las definiciones no están estandarizadas | El bono FVG (+10) y el pilar "liquidez" no tienen respaldo; tratarlos como hipótesis, no como señal |
| Momentum de series temporales (1-12 meses) | Documentado en futuros de índices, divisas, materias primas y bonos (Moskowitz, Ooi y Pedersen 2012; "Trends Everywhere"). Discutido: Huang et al. 2020 dicen que la evidencia por activo es débil; en materias primas rindió peor tras 2009 | Es la hipótesis con más respaldo. Necesita **años** de datos D1, que MT5 sí entrega (no 340 días de M5) |
| Momentum intradía (la 1ª media hora predice la última) | Documentado en el ETF del S&P 500 (1993-2013), otros ETFs, futuros de índices, 4 futuros de materias primas y RUB/USD. No es universal (falla en varios mercados asiáticos) | Candidata directa para **US100** (apertura de contado 16:30 servidor). Para el oro no encontré estudios |
| Sobreajuste de backtests | El Sharpe "deflactado" y la probabilidad de sobreajuste (Bailey y López de Prado) exigen contar **todos** los intentos | Ya llevamos 20 intentos sobre los mismos datos: cada variante nueva debe superar un listón más alto |
| Herramientas profesionales (StrategyQuant X, Edgewonk, TradeZella, Tradervue) | Robustez: Monte Carlo (orden de operaciones, operaciones saltadas, ruido en spread/slippage), walk-forward, perfil de optimización. Diario: MAE/MFE, expectativa, coste de errores, rachas | Son las piezas que faltan para decidir con datos (ver fase 1 y 3) |

Sobre "ingeniería inversa de otras apps": estudié lo que esas herramientas documentan públicamente (funciones, métodos
de validación). No descompilé software de terceros: suele estar prohibido por su licencia y no aporta nada que la
documentación no diga.

## 3. Auditoría del código: defectos encontrados

Ya corregidos en esta sesión:

| # | Defecto | Riesgo | Arreglo |
|---|---|---|---|
| A1 | CORS `"*"` y WebSockets sin comprobar el origen | **Cualquier web abierta en el navegador** podía leer saldo y posiciones por WebSocket o lanzar `POST /close-all`, `/close/{ticket}`, `/risk/reset` contra `127.0.0.1:8000` (los POST sin cuerpo JSON no necesitan permiso CORS) | Lista de orígenes permitidos (frontend local), middleware que rechaza POST de otros orígenes con 403, cierre 1008 de WebSockets ajenos. 6 tests en `tests/test_api_origin.py` |
| A2 | `python backtest.py` se caía al imprimir "→" en la consola de Windows (cp1252) | El JSON se escribía, pero no se veía el resumen | `sys.stdout.reconfigure(encoding="utf-8")` |
| A3 | Filtro del auto-trading aceptaba ruido (n ≥ 30, media ≥ +0.05R) | Habría activado XAUUSD y USDJPY | Ambos tramos ≥ +0.05R con n ≥ 30 cada uno y t ≥ 2 (sesión anterior) |

**Fase 0 completada (15-oct-2026):** B1, B2, B4 y B7 resueltos. El cierre de emergencia solo toca el `MAGIC_NUMBER` del bot.
Sin calendario de menos de 12 h se bloquean las entradas, con un reintento cada 5 min como máximo.
`/execute` y el auto-trading recalculan el lote máximo en el servidor y nunca lo aumentan. La interfaz muestra el aviso
"sin ventaja demostrada", los tramos y el t-stat en lugar de "STRONG / BOT APROBADO / Score 75+", y pide confirmación
para ejecutar un par sin ventaja. La constitución está en `docs/constitution.md`. Tests: 76 en verde.

Pendientes (estado original de la auditoría; B1, B2, B4 y B7 ya están hechos):

| # | Defecto | Por qué importa | Propuesta |
|---|---|---|---|
| B1 | `emergency_close_all` (kill switch y botón "cerrar todo") cierra **todas** las posiciones de la cuenta, también las manuales o de otros EAs | Una operación manual tuya se liquidaría por la pérdida del bot | Filtrar por `MAGIC_NUMBER`, o preguntar en la UI "solo bot / todo" |
| B2 | El filtro de noticias **falla abierto**: si no se puede descargar el calendario, no bloquea nada y no avisa | El auto-trading operaría a ciegas durante NFP/FOMC | Si el calendario tiene más de 6 h sin actualizarse, bloquear el auto-trading y mostrar aviso |
| B3 | El filtro de "correlación USD" cuenta **todas** las posiciones, de cualquier divisa | Nombre engañoso; limita sin criterio | Contar exposición por divisa (EUR, GBP, JPY, USD, oro, índice) |
| B4 | `POST /execute` acepta cualquier volumen del cliente y guarda `signal_score=80` fijo | Un error en la UI puede mandar un lote enorme; la bitácora miente | Recalcular el lote máximo en el servidor y rechazar si el riesgo supera el %; guardar el score real |
| B5 | El parcial en TP1 y el paso a breakeven dependen de que la app esté abierta (sondeo cada 1,5 s) | Si se cierra la app o se cae Python, no hay parcial ni BE; además hay deslizamiento frente al backtest, que supone llenado exacto en TP1 | Abrir **dos órdenes** (mitad con TP1, mitad con TP2) para que el broker haga el parcial, o mover la gestión a un EA MQL5 dentro del terminal |
| B6 | Backtest sin comisión ni deslizamiento; spreads del demo ≈ 0 en EURUSD | Sobreestima resultados (el informe ya midió −0.05R a −0.07R por costes) | Modelo de costes por símbolo: spread real de ticks (`copy_ticks_range`) + comisión + deslizamiento |
| B7 | La UI etiqueta señales como STRONG / modo SNIPER por score, pero subir el score **empeora** los resultados | Transmite una calidad que los datos desmienten | Mostrar "sin ventaja demostrada" mientras ningún par pase el filtro; quitar o renombrar la escala |
| B8 | Reintentos de orden: solo cambia el modo de llenado; ante recotización (10004/10020) no reintenta con tick nuevo | Órdenes perdidas en mercado rápido | Reintento corto con tick fresco solo para esos códigos; registrar precio esperado vs ejecutado |

## 4. Hoja de ruta propuesta

**Fase 0 — Seguridad y honestidad (pequeña, 1 sesión).** B1, B2, B4, B7. El auto-trading sigue apagado.

**Fase 1 — Laboratorio de investigación fiable (lo más importante).**
- Cargador de historial largo: D1/H1 de varios años (MT5 lo da en D1) y ticks para spreads reales.
- Modelo de costes (B6) aplicado a todo backtest.
- Registro de hipótesis **antes** de mirar resultados (`research/hipotesis.yaml`) con contador global de intentos.
- Métricas de robustez: t-stat, Sharpe deflactado con el nº de intentos, Monte Carlo del orden de operaciones
  (drawdown al 95 %), walk-forward por bloques y bootstrap. Todo con tests.

**Fase 1 completada (15-oct-2026)**, ver `research/LABORATORIO.md`:
- Historial en caché: D1 desde 2000 (FX), 2004 (oro) y 2022 (US100); H1 desde 2017 (US100 desde 2022).
- Spread real medido: en el oro, los ticks dan 0.39 de mediana y las velas que usaba el backtest 0.15.
- `costs.py` lo aplica en `backtest.py` (y por tanto en el filtro del auto-trading) y en el laboratorio.
- Hay un registro con los 20 intentos previos y métricas de robustez (t, IC95, DSR, Monte Carlo, tramos, bloques).
- Control C-MOTOR-ACTUAL (340 días, 441 operaciones): +0.025R bruto, −0.065R de coste, **−0.04R neto**, t −0.72,
  DSR 0.005 → no pasa. El backtest de 180 días con costes deja todos los pares bloqueados.

**Fase 2 — Hipótesis nuevas con respaldo publicado (máx. 3, pre-registradas).**
- H-A *Momentum intradía US100*: signo del retorno de los primeros 30 min tras la apertura de contado → posición
  en los últimos 30 min de la sesión. Literatura: equity index ETFs y futuros.
- H-B *Tendencia multi-semana con volatilidad objetivo* en XAUUSD, US100 y las 3 divisas, sobre D1 de varios años
  (lookback 1-12 meses fijado de antemano, sin optimizar).
- H-C *Mismo motor actual como filtro de contexto, no como señal*: solo si H-A o H-B pasan, probar si el contexto
  intradía mejora su entrada.
- Criterio de éxito fijado antes: t ≥ 2 tras costes, ambos tramos positivos, Sharpe deflactado > 0.95.
  Si nada pasa, la conclusión válida es "no automatizar" y la app queda como herramienta de lectura y gestión de riesgo.

**Fase 3 — Ejecución y diario de nivel profesional.**
- B5 (órdenes divididas o EA MQL5 de gestión), B8 (reintentos y deslizamiento medido), B3.
- Diario con R-múltiplos, MAE/MFE por operación, expectativa por setup y por hora, coste de saltarse reglas,
  y comparación backtest vs vivo (la métrica que más revela si el backtest miente).

**Fase 4 — Prueba en vivo en demo, reglas congeladas, ≥ 3 meses** antes de considerar dinero real.

## Estado al cierre del 15-oct-2026

- **Fase 2 completada** (`research/INFORME_FASE2.md`). H-A (momentum intradía en US100) queda descartada: −0.06R neto.
  H-B (momentum de 12 meses en D1) da +0.067R neto, t 2.22, con los dos tramos positivos, pero su DSR es 0.61 < 0.95:
  no pasa el criterio y no se automatiza. H-C no se ejecuta.
- **Fase 3 completada:**
  - B8: reintento con tick nuevo solo ante recotización, precio cambiado o sin cotización, y precio pedido guardado
    para medir el deslizamiento.
  - B3: exposición por divisa (máximo 2 símbolos por divisa, oro o índice).
  - B5: con TP1, el plan se abre como **dos órdenes** (mitad con TP1 y mitad con TP2), así el broker cierra el parcial
    aunque la app esté apagada. El paso a breakeven de la pata TP2 sigue necesitando la app abierta.
  - Diario con R por pata y por plan, MAE/MFE en R (velas M1) y comparación vivo vs backtest (`/journal/stats`).
- **Fase 4 en marcha:** reglas congeladas el 15-oct-2026 08:10 UTC (`forward_config.json`).
  - `python forward.py run` o el panel "Prueba a futuro en sombra" miden el motor y H-B con datos posteriores, netos
    de costes y sin enviar órdenes.
  - Si alguien cambia `setups.py`, `signal_engine.py`, `backtest.py`, `costs.py` o `h_b.py`, el panel lo marca.
  - Hay que dejar que se acumulen meses: H-B da una operación al mes por símbolo, así que en 3 meses habrá unas 15.


## 5. Propuesta de constitución del proyecto (para aprobar)

Siguiendo tu costumbre, propongo `docs/constitution.md`:

1. EL SISTEMA no ejecuta auto-trading en un par salvo que `history_allows_auto` lo apruebe con el criterio vigente (ambos tramos ≥ +0.05R, n ≥ 30 por tramo, t ≥ 2).
2. Todo backtest que alimente decisiones incluye spread, comisión y deslizamiento por símbolo.
3. Toda hipótesis nueva se registra con su criterio de éxito antes de ejecutarse y suma al contador global de intentos.
4. Ningún cambio de lógica de señales, riesgo u órdenes se integra sin tests en `tests/` y `python -m pytest tests -q` en verde.
5. Sin MT5 conectado, la app no genera, registra ni ejecuta señales; los datos simulados solo sirven para la vista.
6. Las acciones que tocan la cuenta (órdenes, cierres, kill switch) solo afectan a las posiciones del bot (`MAGIC_NUMBER`) salvo confirmación explícita.
7. Stack: Python (FastAPI, MetaTrader5, pandas) + React/Vite; código, textos de UI y documentación en español.

## Fuentes

- [Neely, Weller y Ulrich — The Adaptive Markets Hypothesis: Evidence from the FX Market (WP Fed St. Louis 2006-046)](https://files.stlouisfed.org/files/htdocs/wp/2006/2006-046.pdf) · [resumen CXO](https://www.cxoadvisory.com/technical-trading/foreign-exchange-market-adaptation-to-technical-trading)
- [Moskowitz, Ooi y Pedersen — Time Series Momentum](https://fairmodel.econ.yale.edu/ec439/jpde.pdf) · [Quantpedia](https://quantpedia.com/strategies/time-series-momentum-effect/) · [Trends Everywhere](https://quantpedia.com/time-series-momentum-works-everywhere/) · [crítica: "Is it there?"](https://buttondown.com/mdickens/archive/contra-time-series-momentum-is-it-there/) · [replicación en materias primas 2025](https://run.unl.pt/bitstreams/3a74d44e-542e-440d-83b5-b5f44247f18f/download)
- [Gao, Han, Li y Zhou — Intraday Momentum](https://c.mql5.com/forextsd/forum/173/intraday_momentum_-_the_first_half-hour_return_predicts_the_last_half-hour_return.pdf) · [resumen Alpha Architect](https://alphaarchitect.com/2014/08/attention-prop-traders-the-first-half-hour-of-trading-predicts-the-last-half-hour/) · [Asia-Pacífico](https://ideas.repec.org/a/eee/pacfin/v80y2023ics0927538x2300152x.html)
- [Bailey y López de Prado — The Deflated Sharpe Ratio](https://papers.ssrn.com/abstract=2460551) · [implementación fynance](https://fynance.readthedocs.io/en/latest/generated/fynance.research.deflated_sharpe_ratio.html)
- [StrategyQuant — pruebas de robustez](https://strategyquant.com/blog/robustness-tests-and-analysis/) · [cross-checks](https://strategyquant.com/doc/strategyquant/cross-checks-automated-strategy-robustness-tests) · [SPP](https://strategyquant.com/blog/optimization-profile-system-parameter-permutation-in-strategyquant-build-robust-trading-strategies/)
- [Edgewonk — estadísticas](https://edgewonk.com/blog/a-deep-dive-into-edgewonk-performance-statistics) · [Edgewonk vs TradeZella](https://daytradingz.com/edgewonk-vs-tradezella/) · [Tradervue](https://www.tradervue.com/blog/best-trading-journal)
- SMC sin evidencia independiente: [guía Backtrex (vendedor)](https://backtrex.com/en/blog/smc-order-blocks-fair-value-gaps-guide)
- MT5 Python: [ejecución de órdenes (ayuda MT5)](https://www.metatrader5.com/en/terminal/help/trading/performing_deals) · [error 10030](https://www.mql5.com/en/forum/515406)
