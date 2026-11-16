# Auditoría y propuesta de mejora de las señales (16-nov-2026)

## Veredicto

La app ya hace bien lo difícil: el backtest usa el mismo código que el escáner, cobra costes reales, y el
auto-trading no se activa sin evidencia. **El motor intradía sigue sin ventaja demostrada** (−0,04R neto en 441
operaciones) y ningún cambio de interfaz o de filtros lo vuelve rentable sin evidencia nueva. Esta revisión hace dos
cosas:

1. Corrige defectos que hacían que **lo que se ejecuta no fuera lo que se planificó**, o que la prueba a futuro
   pareciera inválida sin serlo. Ninguno toca los archivos de reglas congeladas.
2. Convierte cada señal en una **ficha de decisión**: lista de verificación, tendencia de fondo, dinero en juego y
   coste en R. Así la señal se depura a mano con la información correcta delante.

Lo que exige tocar las reglas congeladas queda abajo como **decisión pendiente**: hacerlo reinicia el reloj de la
prueba a futuro, que lleva un mes acumulando datos.

> No pude ejecutar backtests en esta revisión: el historial de MT5 (`research/cache/`) solo existe en tu PC.
> Todo lo que dice este documento sobre resultados viene de los informes anteriores, no de cálculos nuevos.

## 1. Hecho en esta revisión

| # | Gravedad | Defecto | Arreglo |
|---|---|---|---|
| A1 | **Alta** | Las huellas de la prueba a futuro se calcularon con 4 archivos en CRLF (Windows) y el repositorio guarda LF. En cualquier clon nuevo, el panel marcaba «reglas modificadas: la prueba deja de valer» con el contenido intacto. | `forward.content_hashes` compara ignorando fines de línea. Verifiqué que los 5 archivos coinciden con lo congelado. Un test lo vigila desde ahora (`test_repository_rules_match_the_frozen_fingerprints`). |
| A2 | **Alta** | Un doble clic en «Ejecutar» abría dos planes completos: el doble del riesgo. | `/execute` rechaza (409) si ya hay una posición del bot en ese símbolo. Las manuales no cuentan. |
| A3 | **Alta** | El panel puede mostrar una señal de hace 1,5 s. Se podía ejecutar un plan cuya ventana ya había expirado o que había cambiado de dirección. | `/execute` comprueba contra la última señal del escáner: tiene que seguir `ACTIVADA` y con la misma dirección. |
| A4 | Media | Con lote mínimo no se puede cerrar la mitad. La operación quedaba sin parcial **y sin breakeven**, todo o nada hasta TP2/SL, algo que el backtest nunca simuló. | Al tocar TP1 sin parcial posible, el stop pasa a breakeven. |
| A5 | Media | Si fallaba la descarga de velas M15, el copilot no gestionaba el parcial ni el breakeven, que no necesitan esas velas. | Las velas solo se usan para el ATR del trailing. |
| A6 | Media | Redondeo en coma flotante: 0,06 L × 0,5 / 0,01 = 2,999… quedaba en un parcial de 0,02 en vez de 0,03. | Margen de 1e-9 en el redondeo (`can_split`). |
| A7 | Media | Con dos señales aprobadas a la vez, la bitácora del copilot alternaba A, B, A, B cada 1,5 s y en medio minuto expulsaba las ejecuciones y alertas reales. | Un aviso por símbolo solo cuando cambia la dirección, el estado o la vela de origen. |
| A8 | Media | Si MT5 tardaba en cargar el historial de una posición recién cerrada, quedaba registrada como cerrada con $0 y sin R para siempre. El diario y la comparación vivo/backtest perdían esa operación. | Se reintenta durante 10 minutos, contados desde que la posición desaparece. |
| A9 | Baja | `costes.json` se leía del disco en cada escaneo y símbolo. | Se carga una vez al arrancar. |

## 2. Interfaz: la señal como ficha de decisión

- **Lista de verificación** de 12 condiciones, completa en la tarjeta seleccionada y resumida en las demás:
  tendencia H1, retroceso a la EMA 21, impulso, espacio hasta la liquidez, gatillo M5, coste, lote, sesión,
  noticias, exposición, tendencia de 12 meses y ventaja en el backtest. Separa los **bloqueos** (plan sin espacio,
  sin gatillo, lote excesivo, noticia, exposición) de lo informativo. No es una probabilidad: en el backtest, más
  confluencias no dieron mejores resultados, y la ficha lo dice.
- **Tendencia de 12 meses** («12m a favor / en contra»), con la misma medida que H-B, la única hipótesis con
  resultado positivo tras costes (+0,067R, t 2,22), aunque sin demostrar.
- **Dinero en juego**: riesgo, ganancia en TP1 (mitad del lote) y en TP2, calculados por MT5 con
  `order_calc_profit`, así que la conversión de divisa es correcta en USDJPY.
- **Coste en R**: spread actual más deslizamiento y comisión de `costs.py`, dividido por el riesgo. En ámbar si
  pasa de 0,10R, que es la mitad de cualquier ventaja realista.
- **Orden del radar por lo que se puede hacer**: activadas, en zona, preparando, descartadas. Antes se ordenaba por
  score, que no predice nada.
- **Confirmación con el resumen completo** de la orden antes de enviarla: lote, niveles, dinero, coste y bloqueos.
- **Móvil**: a 390 px el panel desbordaba 634 px en horizontal (cabecera, rejilla, gráfico y diario). Ahora no
  desborda.

## 3. Decisiones pendientes (tocan reglas congeladas)

Cada una cambia `setups.py`, `signal_engine.py` o `backtest.py`, así que **la prueba a futuro del MOTOR volvería a
empezar** desde la fecha del cambio. La de H-B no se ve afectada. Recomiendo agruparlas en un único cambio si se
aprueban.

| # | Prioridad | Hallazgo | Propuesta |
|---|---|---|---|
| P1 | **Alta** | **Paridad vivo/backtest.** En vivo, el plan se recalcula con cada vela M15 nueva (`signal_engine.py:278` y `:320`): la EMA 21, el ATR, los mínimos y el FVG pasan a ser los de la última vela. El backtest congela el plan en la vela de señal durante toda su vida, hasta 4 velas (`backtest.py:238`). Durante 3 de cada 4 velas, la zona y el SL que ves no son los que se probaron. | Guardar en `SetupTracker` los insumos del plan (EMA 21, ATR, mínimos/máximos, FVG, niveles) al crear el setup y reutilizarlos en vivo. Es un arreglo de fidelidad, no un intento: no suma al contador de hipótesis. |
| P2 | Media | TP1 se coloca **exactamente** en el máximo o mínimo de liquidez (`setups.py:164`). Las ventas se cierran por el ask, así que el bid tiene que pasar el nivel en un spread entero. Cuando el precio solo toca el nivel, el TP no se llena. | Pre-registrar **H-D**: TP adelantado `max(spread, 0.1R)` antes del nivel. Es un intento nuevo y cuenta en el DSR. |
| P3 | Baja | Después de TP1, el backtest cuenta el breakeven como 0R, pero en el broker el stop en el precio de entrada se ejecuta por el precio contrario y pierde el spread. Optimismo de unos 0,01-0,03R en las operaciones que llegan a TP1. | Cobrar el spread en la salida a breakeven en `simulate_trade`, o poner el stop en entrada ± spread. |
| P4 | Baja | La penalización por spread usa en vivo el tick actual y en el backtest el mínimo de la vela (`signal_engine.py:118`). En vivo se descartan más señales que en el backtest. | Usar en ambos el spread típico medido (`research/cache/spreads.json`). |
| P5 | Cosmética | El pilar ADX + volumen se llama `execution_cost` (`signal_engine.py:109`). | Renombrarlo a `trend_strength`. Toca el contrato con el panel. |

## 4. Investigación recomendada (pre-registrar antes de mirar)

1. **No tocar el motor por resultados.** La prueba a futuro sigue siendo la única evidencia limpia. Primera lectura
   seria a mediados de enero de 2027 (unas 15 operaciones de H-B).
2. **H-E: H-B como filtro del motor.** Solo señales intradía a favor de la tendencia de 12 meses. Es la pregunta
   natural ahora que la ficha muestra ese dato, y por eso mismo **hay que registrarla antes de mirar**: si se elige
   tras ver la ficha, el resultado no vale. Criterio igual que el vigente (t ≥ 2, DSR ≥ 0,95 con todos los intentos,
   ambos tramos positivos, n ≥ 100).
3. **Spreads de ticks reales en el backtest** (`copy_ticks_range`) en lugar del mínimo de cada vela. Hoy el coste del
   oro se suma como constante.
4. **Riesgo de cartera:** límite semanal (por ejemplo −6 %) y pausa tras 4 pérdidas seguidas, además del −3 % diario.
   Ventana de noticias de 30 min antes y 15 después para NFP/FOMC (hoy ±15).
5. **EA MQL5 mínimo** que mueva a breakeven la pata TP2 cuando se cierra la pata TP1. Es lo único de la gestión que
   aún depende de que la app esté abierta.

## 5. Cómo se verificó

- `python -m pytest tests -q`: 161 en verde y 2 omitidos (136 anteriores y 25 nuevos), en Linux con un sustituto
  del paquete MetaTrader5. El CI los corre en Windows con el paquete real.
- `npm run lint` y `npm run build` sin errores.
- Capturas del radar a 1500 px y 390 px con un motor simulado (datos de ejemplo, no de mercado), y medición del
  desbordamiento horizontal: 0 px.
