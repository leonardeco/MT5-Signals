# Informe: búsqueda de variantes con ventaja (15-oct-2026)

## Conclusión corta

**No hay ventaja.** Ninguna de las 20 variantes probadas da una expectativa positiva y robusta.
La única que pasó el criterio fijado de antemano (G2 "solo pin bar": +0.061R fuera de muestra) no es
estadísticamente distinguible de cero (t = 0.66, IC95 OOS −0.16…+0.28R) y queda en ≈ 0R al sumar costes
realistas. Con 20 variantes probadas, que una pase por azar es lo esperable.

**Lo único robusto es negativo:** el gatillo *ruptura de estructura M5 (BOS)* pierde −0.37R por operación
(n = 112, t = −4.3), en los **5 pares** y en los **5 bloques temporales**. Se retiró de `setups.m5_trigger`
(lo usan el escáner en vivo y el backtest). Esto quita pérdidas, no crea ventaja: el sistema pasa de −0.04R
a ≈ 0R por operación antes de costes extra (−0.02R / −0.07R después).

**Recomendación:** mantener el auto-trading apagado. No usar las señales como sistema rentable; como mucho,
como herramienta de lectura de contexto con gestión discrecional.

> ⚠️ **No re-ejecutar el backtest de 180 días sin endurecer antes el filtro del auto-trading.**
> Con el gatillo BOS retirado, `python backtest.py 180` daría XAUUSD +0.096R (n = 48) y USDJPY +0.099R (n = 44),
> y el filtro actual (`main.py`: n ≥ 30 y media ≥ +0.05R) **habilitaría el auto-trading en esos dos pares**.
> Es ruido: XAUUSD da −0.02R en el periodo fuera de muestra de 340 días, y USDJPY −0.15R en el periodo in-sample.
> Por eso `backtest_results.json` **no se ha regenerado** (sigue con los números del motor anterior).

## Método

- **Datos:** historial real de MT5 (MetaQuotes-Demo), máximo que da el terminal: 97 920 velas M5 ≈ 340 días
  de mercado (FX desde 23-jun-2025, XAUUSD desde 20-may-2025, US100/USTEC desde 28-mar-2025, hasta 15-oct-2026).
  Caché en `research/cache/frames_340d.pkl` (y `frames_180d.pkl`), generada con `research/cache_frames.py`.
- **Motor:** exactamente `score_bar`, `build_plan`, `m5_trigger`, `SetupTracker` y `simulate_trade` del backtest.
  `backtest_frames` recibió tres ganchos opcionales (`setup_filter`, `trigger_filter`, `exit_fn`) que por defecto
  no cambian nada (hay un test que lo comprueba sobre historial real); el bucle no se duplicó.
- **Hipótesis fijadas antes de mirar resultados**, una a una sobre el plan base, con 1–4 valores cada una
  (sin optimizar parámetros). Hora del servidor = UTC+2/+3 (verificado: la apertura de contado de US100 aparece a las 16:30).
- **Validación:** corte temporal común al 60 % (IS hasta 06-abr-2026, OOS después).
  Criterio para pasar (también fijado antes): media R OOS mejor que la base en ≥ 3 de 5 pares, media R OOS
  agregada ≥ +0.05R con n ≥ 30, e IS agregado > 0.
- **Segunda fase** para las supervivientes: tablas por par, 5 bloques temporales consecutivos (cortes 27-sep-2025,
  31-dic-2025, 06-abr-2026, 11-jul-2026), walk-forward (en cada bloque se elige el tipo de gatillo con mejor media en los
  bloques anteriores y se mide en el siguiente), bootstrap de la media y estrés de costes extra por operación
  (XAUUSD 0.20 · EURUSD 0.5 pip · GBPUSD 0.8 pip · USDJPY 0.8 pip · US100 1.0 punto), porque el spread de las velas
  del demo es casi cero en EURUSD (mediana 0) y subestima el coste real.

Hipótesis:

| Grupo | Variantes |
|---|---|
| H1 sesión | S1 Londres+NY 10:00–19:00 servidor · S2 por instrumento (US100 16:30–23:00) |
| H2 sesgo HTF | B1 H4 (cierre vs EMA50 H4) a favor · B2 D1 (cierre vs EMA20 D1) · B3 ambos |
| H3 régimen | R1 ADX M15 ≥ 25 · R2 ADX H1 ≥ 25 · R3 percentil ATR ≥ 50 · R4 percentil 20–80 |
| H4 score | C1 ≥ 65 · C2 ≥ 75 |
| H5 gatillo | G1 solo envolvente · G2 solo pin bar · G3 solo ruptura · G4 sin ruptura |
| H6 salida | X1 todo en TP1 · X2 objetivo fijo 1.5R · X3 fijo 2R · X4 parcial sin breakeven · X5 sin niveles de liquidez (1.5R/3R) |

## Resultados (agregado de los 5 pares; media R por operación)

Los números de esta tabla son del motor **antes** del cambio (la BASE incluye el gatillo BOS).
Tras integrar el cambio, la BASE es igual a G4.

| Variante | IS n | IS % | IS media R | IS PF | IS racha | OOS n | OOS % | OOS media R | OOS PF | OOS racha | Pares OOS mejor que base | ¿Pasa? |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BASE | 314 | 46% | -0.042 | 0.92 | 11 | 202 | 44% | -0.036 | 0.93 | 8 | 0/5 | no |
| S1 Londres+NY | 137 | 52% | -0.003 | 0.99 | 5 | 87 | 42% | -0.049 | 0.91 | 7 | 2/5 | no |
| S2 sesión por instrumento | 124 | 49% | -0.017 | 0.97 | 7 | 79 | 44% | -0.023 | 0.95 | 7 | 2/5 | no |
| B1 sesgo H4 | 301 | 46% | -0.057 | 0.89 | 10 | 185 | 43% | -0.031 | 0.94 | 8 | 3/5 | no |
| B2 sesgo D1 | 228 | 45% | -0.085 | 0.84 | 8 | 163 | 43% | -0.043 | 0.92 | 8 | 2/5 | no |
| B3 sesgo H4+D1 | 222 | 45% | -0.094 | 0.83 | 8 | 160 | 42% | -0.048 | 0.91 | 8 | 2/5 | no |
| R1 ADX M15>=25 | 209 | 48% | -0.059 | 0.88 | 9 | 127 | 41% | -0.108 | 0.81 | 6 | 2/5 | no |
| R2 ADX H1>=25 | 231 | 46% | -0.048 | 0.91 | 7 | 148 | 39% | -0.109 | 0.81 | 7 | 0/5 | no |
| R3 ATR pct>=50 | 178 | 50% | +0.053 | 1.11 | 8 | 114 | 40% | -0.102 | 0.82 | 8 | 2/5 | no |
| R4 ATR pct 20-80 | 195 | 46% | -0.033 | 0.94 | 12 | 110 | 44% | +0.001 | 1.0 | 6 | 2/5 | no |
| C1 score>=65 | 270 | 44% | -0.125 | 0.77 | 10 | 167 | 42% | -0.064 | 0.88 | 8 | 3/5 | no |
| C2 score>=75 | 89 | 47% | -0.094 | 0.81 | 7 | 68 | 44% | -0.036 | 0.93 | 9 | 3/5 | no |
| G1 solo envolvente | 155 | 48% | +0.014 | 1.03 | 6 | 99 | 42% | -0.092 | 0.83 | 7 | 3/5 | no |
| G2 solo pin bar | 163 | 47% | +0.036 | 1.07 | 11 | 120 | 47% | +0.061 | 1.12 | 6 | 5/5 | **SÍ** |
| G3 solo ruptura | 114 | 39% | -0.257 | 0.55 | 10 | 63 | 38% | -0.213 | 0.63 | 5 | 1/5 | no |
| G4 sin ruptura | 263 | 49% | +0.038 | 1.08 | 9 | 178 | 45% | +0.005 | 1.01 | 8 | 5/5 | no |
| X1 todo en TP1 | 320 | 45% | -0.046 | 0.91 | 11 | 204 | 44% | -0.037 | 0.93 | 8 | 2/5 | no |
| X2 fijo 1.5R | 312 | 40% | -0.031 | 0.95 | 17 | 199 | 39% | -0.022 | 0.96 | 8 | 3/5 | no |
| X3 fijo 2R | 308 | 35% | -0.022 | 0.97 | 17 | 195 | 36% | +0.033 | 1.05 | 8 | 4/5 | no |
| X4 parcial sin BE | 306 | 41% | -0.064 | 0.88 | 17 | 192 | 40% | -0.020 | 0.96 | 8 | 3/5 | no |
| X5 sin niveles (1.5R/3R) | 2744 | 43% | -0.050 | 0.91 | 16 | 1891 | 46% | -0.039 | 0.92 | 13 | 4/5 | no |

### Lectura por hipótesis

- **Sesión (H1):** mejora el IS pero empeora o iguala el OOS. Sin efecto estable.
- **Sesgo H4/D1 (H2):** no ayuda; el D1 empeora en IS y OOS.
- **Régimen (H3):** R3 (ATR alto) es el típico espejismo: +0.053R IS → −0.102R OOS. ADX ≥ 25 empeora.
- **Score (H4):** subir el umbral **empeora** (C1 −0.125R IS). El score no ordena la calidad de las señales,
  igual que ya mostraban los buckets del backtest anterior.
- **Gatillo (H5):** el único efecto consistente. BOS pierde en IS y OOS; pin bar es lo menos malo.
  Walk-forward eligiendo el tipo de gatillo con los datos previos: **+0.009R** (n = 243) → sin ventaja.
- **Salida (H6):** cambiar TP/SL mueve la media ±0.03R, dentro del ruido. X5 (quitar la exigencia de
  "espacio hasta la liquidez") multiplica las operaciones por 9 (4 635) con −0.05R / −0.04R: la señal de
  entrada en sí está alrededor de cero menos costes; ningún esquema de salida la arregla.

### Segunda fase (supervivientes y candidatas)

| Variante | t (todo) | IC95 media OOS | Media IS / OOS con costes extra | Media por bloque (5 bloques) |
|---|---|---|---|---|
| BASE | −0.79 | −0.19 … +0.12 | −0.095 / −0.101 | −0.08, +0.09, −0.12, +0.06, −0.14 |
| G2 solo pin bar | 0.66 | −0.16 … +0.28 | −0.018 / −0.004 | +0.03, +0.05, +0.04, +0.13, −0.03 |
| G4 sin ruptura (integrada) | 0.44 | −0.16 … +0.18 | −0.017 / −0.065 | +0.03, +0.11, −0.02, +0.05, −0.04 |
| X3 fijo 2R | −0.01 | −0.16 … +0.23 | −0.074 / −0.031 | −0.07, +0.20, −0.16, +0.10, −0.05 |
| G2+X3 (combinación a posteriori) | 0.94 | −0.13 … +0.39 | −0.009 / +0.061 | +0.01, +0.15, −0.04, +0.11, +0.14 |

- **G2 solo pin bar:** pasa el criterio, pero EURUSD y GBPUSD pierden en IS **y** OOS; el resultado lo hacen
  XAUUSD en IS (+0.53R) y US100/USDJPY en OOS. No es significativo y con costes queda en ≈ 0R.
  No se integró: elegir "el mejor de tres tipos de gatillo" es más propenso a sobreajuste que retirar
  el que pierde de forma consistente.
- **G2+X3:** la mejor cifra OOS (+0.125R), pero es la combinación de las dos mejores de 20 pruebas
  (sesgo de selección), no es significativa (t = 0.94) y en IS con costes es negativa. No se integró.

### Gatillos de la base por par (media R, n total = 516)

| Par | Envolvente | Pin bar | Ruptura (BOS) |
|---|---|---|---|
| XAUUSD | +0.056 (31) | +0.361 (51) | −0.275 (30) |
| EURUSD | +0.100 (46) | −0.106 (46) | −0.577 (21) |
| GBPUSD | +0.040 (33) | −0.068 (42) | −0.630 (13) |
| US100 | −0.274 (33) | +0.273 (46) | −0.111 (26) |
| USDJPY | −0.134 (30) | +0.063 (46) | −0.442 (22) |
| **Total** | −0.031 (173) | +0.113 (231) | **−0.367 (112)** |

## Cambio integrado

- `setups.py` → `m5_trigger`: solo envolvente y pin bar (se quitó la ruptura de estructura). Efecto en vivo y en backtest a la vez.
- `backtest.py` → ganchos opcionales en `backtest_frames`, `i` y `risk_px` en cada operación, lista
  `trades_nuevo` (se excluye de `backtest_results.json`).
- `tests/test_setups_backtest.py` → 5 tests nuevos (BOS alcista/bajista ya no dispara, pin bar sí, los ganchos
  son neutros sobre historial real, `setup_filter` puede rechazar todo). `python -m pytest tests -q`: 40 passed.
- Verificado: con el cambio, el motor reproduce exactamente G4 (IS 263 ops +0.038R, OOS 178 ops +0.005R).

## Pendiente / decisiones para el usuario

1. **Endurecer el filtro del auto-trading antes de volver a correr el backtest** (ver aviso arriba). Opciones:
   exigir media ≥ +0.05R tanto en IS como en OOS por par, o t ≥ 2, o mínimo de 100 operaciones.
2. Si se quiere seguir buscando ventaja, el siguiente paso no es filtrar este motor sino cambiar la idea de entrada:
   la entrada base vale ≈ 0R antes de costes con cualquier salida probada.

## Reproducir

```
python research/cache_frames.py 340          # necesita MT5 abierto
python research/explore_variants.py 340      # hipótesis una a una → research/variants_340d.json
python -m research.stage2 340                # 2ª fase → research/stage2_340d.json
```

Nota: los JSON guardados son del motor anterior. Si se re-ejecutan ahora, la BASE ya es "sin ruptura"
y G3 dará 0 operaciones.

## Anexo A — detalle por par (n, % acierto, media R, PF, racha máxima de pérdidas)


**BASE**

| Par | IS n | IS % | IS R | IS PF | IS racha | OOS n | OOS % | OOS R | OOS PF | OOS racha |
|---|---|---|---|---|---|---|---|---|---|---|
| XAUUSD | 70 | 63% | +0.198 | 1.53 | 4 | 42 | 40% | -0.047 | 0.92 | 7 |
| EURUSD | 70 | 41% | -0.097 | 0.83 | 8 | 43 | 40% | -0.131 | 0.77 | 5 |
| GBPUSD | 47 | 45% | -0.094 | 0.82 | 4 | 41 | 42% | -0.128 | 0.77 | 8 |
| US100 | 65 | 43% | -0.010 | 0.98 | 4 | 40 | 42% | +0.033 | 1.06 | 5 |
| USDJPY | 62 | 36% | -0.246 | 0.62 | 9 | 36 | 56% | +0.122 | 1.27 | 4 |
| TOTAL | 314 | 46% | -0.042 | 0.92 | 11 | 202 | 44% | -0.036 | 0.93 | 8 |

**S1 Londres+NY**

| Par | IS n | IS % | IS R | IS PF | IS racha | OOS n | OOS % | OOS R | OOS PF | OOS racha |
|---|---|---|---|---|---|---|---|---|---|---|
| XAUUSD | 37 | 70% | +0.264 | 1.89 | 3 | 21 | 43% | -0.051 | 0.91 | 3 |
| EURUSD | 32 | 41% | -0.196 | 0.67 | 5 | 17 | 24% | -0.409 | 0.41 | 7 |
| GBPUSD | 22 | 59% | +0.111 | 1.29 | 3 | 18 | 33% | -0.248 | 0.61 | 6 |
| US100 | 27 | 48% | -0.030 | 0.94 | 3 | 19 | 47% | +0.063 | 1.12 | 3 |
| USDJPY | 19 | 32% | -0.288 | 0.58 | 4 | 12 | 75% | +0.582 | 3.33 | 1 |
| TOTAL | 137 | 52% | -0.003 | 0.99 | 5 | 87 | 42% | -0.049 | 0.91 | 7 |

**S2 sesión por instrumento**

| Par | IS n | IS % | IS R | IS PF | IS racha | OOS n | OOS % | OOS R | OOS PF | OOS racha |
|---|---|---|---|---|---|---|---|---|---|---|
| XAUUSD | 37 | 70% | +0.264 | 1.89 | 3 | 21 | 43% | -0.051 | 0.91 | 3 |
| EURUSD | 32 | 41% | -0.196 | 0.67 | 5 | 17 | 24% | -0.409 | 0.41 | 7 |
| GBPUSD | 22 | 59% | +0.111 | 1.29 | 3 | 18 | 33% | -0.248 | 0.61 | 6 |
| US100 | 14 | 21% | -0.181 | 0.75 | 4 | 11 | 64% | +0.333 | 2.2 | 2 |
| USDJPY | 19 | 32% | -0.288 | 0.58 | 4 | 12 | 75% | +0.582 | 3.33 | 1 |
| TOTAL | 124 | 49% | -0.017 | 0.97 | 7 | 79 | 44% | -0.023 | 0.95 | 7 |

**B1 sesgo H4**

| Par | IS n | IS % | IS R | IS PF | IS racha | OOS n | OOS % | OOS R | OOS PF | OOS racha |
|---|---|---|---|---|---|---|---|---|---|---|
| XAUUSD | 69 | 64% | +0.216 | 1.6 | 4 | 42 | 38% | -0.076 | 0.87 | 7 |
| EURUSD | 66 | 41% | -0.105 | 0.82 | 9 | 39 | 41% | -0.090 | 0.83 | 5 |
| GBPUSD | 45 | 42% | -0.143 | 0.73 | 5 | 36 | 42% | -0.088 | 0.84 | 8 |
| US100 | 61 | 43% | -0.075 | 0.86 | 4 | 36 | 42% | +0.047 | 1.08 | 6 |
| USDJPY | 60 | 37% | -0.237 | 0.63 | 9 | 32 | 56% | +0.076 | 1.17 | 4 |
| TOTAL | 301 | 46% | -0.057 | 0.89 | 10 | 185 | 43% | -0.031 | 0.94 | 8 |

**B2 sesgo D1**

| Par | IS n | IS % | IS R | IS PF | IS racha | OOS n | OOS % | OOS R | OOS PF | OOS racha |
|---|---|---|---|---|---|---|---|---|---|---|
| XAUUSD | 50 | 58% | +0.114 | 1.27 | 4 | 37 | 35% | -0.127 | 0.79 | 7 |
| EURUSD | 52 | 40% | -0.140 | 0.77 | 8 | 35 | 43% | -0.014 | 0.97 | 3 |
| GBPUSD | 40 | 45% | -0.095 | 0.82 | 5 | 28 | 39% | -0.172 | 0.71 | 8 |
| US100 | 41 | 44% | -0.063 | 0.88 | 5 | 35 | 37% | -0.066 | 0.89 | 6 |
| USDJPY | 45 | 38% | -0.255 | 0.59 | 6 | 28 | 64% | +0.191 | 1.53 | 3 |
| TOTAL | 228 | 45% | -0.085 | 0.84 | 8 | 163 | 43% | -0.043 | 0.92 | 8 |

**B3 sesgo H4+D1**

| Par | IS n | IS % | IS R | IS PF | IS racha | OOS n | OOS % | OOS R | OOS PF | OOS racha |
|---|---|---|---|---|---|---|---|---|---|---|
| XAUUSD | 50 | 58% | +0.114 | 1.27 | 4 | 37 | 35% | -0.127 | 0.79 | 7 |
| EURUSD | 50 | 38% | -0.203 | 0.67 | 8 | 34 | 41% | -0.049 | 0.91 | 3 |
| GBPUSD | 39 | 46% | -0.071 | 0.86 | 5 | 28 | 39% | -0.172 | 0.71 | 8 |
| US100 | 40 | 45% | -0.039 | 0.93 | 5 | 35 | 37% | -0.066 | 0.89 | 6 |
| USDJPY | 43 | 37% | -0.280 | 0.55 | 6 | 26 | 65% | +0.223 | 1.64 | 3 |
| TOTAL | 222 | 45% | -0.094 | 0.83 | 8 | 160 | 42% | -0.048 | 0.91 | 8 |

**R1 ADX M15>=25**

| Par | IS n | IS % | IS R | IS PF | IS racha | OOS n | OOS % | OOS R | OOS PF | OOS racha |
|---|---|---|---|---|---|---|---|---|---|---|
| XAUUSD | 45 | 60% | +0.072 | 1.18 | 5 | 27 | 37% | -0.107 | 0.81 | 5 |
| EURUSD | 53 | 47% | +0.004 | 1.01 | 5 | 36 | 31% | -0.347 | 0.46 | 6 |
| GBPUSD | 33 | 48% | -0.124 | 0.74 | 6 | 21 | 38% | -0.215 | 0.63 | 4 |
| US100 | 40 | 45% | -0.052 | 0.9 | 4 | 24 | 42% | +0.065 | 1.12 | 3 |
| USDJPY | 38 | 37% | -0.256 | 0.6 | 8 | 19 | 68% | +0.247 | 1.78 | 2 |
| TOTAL | 209 | 48% | -0.059 | 0.88 | 9 | 127 | 41% | -0.108 | 0.81 | 6 |

**R2 ADX H1>=25**

| Par | IS n | IS % | IS R | IS PF | IS racha | OOS n | OOS % | OOS R | OOS PF | OOS racha |
|---|---|---|---|---|---|---|---|---|---|---|
| XAUUSD | 53 | 64% | +0.265 | 1.74 | 3 | 35 | 37% | -0.145 | 0.75 | 6 |
| EURUSD | 52 | 40% | -0.174 | 0.71 | 7 | 30 | 30% | -0.261 | 0.59 | 5 |
| GBPUSD | 41 | 44% | -0.125 | 0.76 | 4 | 26 | 38% | -0.172 | 0.71 | 6 |
| US100 | 44 | 41% | -0.123 | 0.78 | 5 | 36 | 39% | -0.013 | 0.98 | 7 |
| USDJPY | 41 | 39% | -0.137 | 0.77 | 6 | 21 | 57% | +0.081 | 1.19 | 3 |
| TOTAL | 231 | 46% | -0.048 | 0.91 | 7 | 148 | 39% | -0.109 | 0.81 | 7 |

**R3 ATR pct>=50**

| Par | IS n | IS % | IS R | IS PF | IS racha | OOS n | OOS % | OOS R | OOS PF | OOS racha |
|---|---|---|---|---|---|---|---|---|---|---|
| XAUUSD | 42 | 64% | +0.178 | 1.5 | 4 | 19 | 37% | +0.012 | 1.02 | 5 |
| EURUSD | 41 | 46% | +0.005 | 1.01 | 4 | 31 | 29% | -0.352 | 0.46 | 5 |
| GBPUSD | 30 | 47% | -0.068 | 0.86 | 4 | 26 | 38% | -0.169 | 0.71 | 5 |
| US100 | 33 | 46% | +0.084 | 1.17 | 4 | 15 | 47% | +0.156 | 1.31 | 4 |
| USDJPY | 32 | 44% | +0.029 | 1.05 | 6 | 23 | 56% | +0.046 | 1.11 | 4 |
| TOTAL | 178 | 50% | +0.053 | 1.11 | 8 | 114 | 40% | -0.102 | 0.82 | 8 |

**R4 ATR pct 20-80**

| Par | IS n | IS % | IS R | IS PF | IS racha | OOS n | OOS % | OOS R | OOS PF | OOS racha |
|---|---|---|---|---|---|---|---|---|---|---|
| XAUUSD | 34 | 56% | +0.081 | 1.18 | 4 | 20 | 30% | -0.313 | 0.54 | 4 |
| EURUSD | 47 | 43% | -0.114 | 0.8 | 7 | 25 | 40% | -0.172 | 0.7 | 4 |
| GBPUSD | 30 | 50% | +0.024 | 1.05 | 3 | 23 | 39% | -0.144 | 0.76 | 6 |
| US100 | 39 | 49% | +0.158 | 1.36 | 5 | 25 | 56% | +0.360 | 1.82 | 2 |
| USDJPY | 45 | 36% | -0.238 | 0.63 | 12 | 17 | 59% | +0.291 | 1.71 | 3 |
| TOTAL | 195 | 46% | -0.033 | 0.94 | 12 | 110 | 44% | +0.001 | 1.0 | 6 |

**C1 score>=65**

| Par | IS n | IS % | IS R | IS PF | IS racha | OOS n | OOS % | OOS R | OOS PF | OOS racha |
|---|---|---|---|---|---|---|---|---|---|---|
| XAUUSD | 64 | 62% | +0.155 | 1.41 | 4 | 37 | 38% | -0.046 | 0.92 | 6 |
| EURUSD | 58 | 36% | -0.206 | 0.68 | 10 | 34 | 32% | -0.255 | 0.6 | 7 |
| GBPUSD | 41 | 42% | -0.224 | 0.59 | 6 | 33 | 39% | -0.211 | 0.64 | 8 |
| US100 | 55 | 44% | -0.056 | 0.89 | 3 | 33 | 42% | +0.066 | 1.12 | 5 |
| USDJPY | 52 | 33% | -0.375 | 0.44 | 8 | 30 | 60% | +0.146 | 1.36 | 3 |
| TOTAL | 270 | 44% | -0.125 | 0.77 | 10 | 167 | 42% | -0.064 | 0.88 | 8 |

**C2 score>=75**

| Par | IS n | IS % | IS R | IS PF | IS racha | OOS n | OOS % | OOS R | OOS PF | OOS racha |
|---|---|---|---|---|---|---|---|---|---|---|
| XAUUSD | 20 | 70% | +0.402 | 2.34 | 3 | 13 | 46% | -0.090 | 0.82 | 2 |
| EURUSD | 14 | 50% | -0.137 | 0.73 | 3 | 17 | 24% | -0.547 | 0.26 | 9 |
| GBPUSD | 17 | 35% | -0.231 | 0.59 | 4 | 16 | 44% | -0.013 | 0.97 | 6 |
| US100 | 23 | 39% | -0.255 | 0.55 | 4 | 10 | 60% | +0.662 | 2.87 | 2 |
| USDJPY | 15 | 40% | -0.309 | 0.49 | 3 | 12 | 58% | +0.135 | 1.32 | 2 |
| TOTAL | 89 | 47% | -0.094 | 0.81 | 7 | 68 | 44% | -0.036 | 0.93 | 9 |

**G1 solo envolvente**

| Par | IS n | IS % | IS R | IS PF | IS racha | OOS n | OOS % | OOS R | OOS PF | OOS racha |
|---|---|---|---|---|---|---|---|---|---|---|
| XAUUSD | 27 | 63% | +0.182 | 1.52 | 3 | 18 | 33% | -0.375 | 0.41 | 6 |
| EURUSD | 45 | 49% | +0.027 | 1.05 | 4 | 25 | 48% | -0.033 | 0.93 | 3 |
| GBPUSD | 25 | 52% | +0.117 | 1.28 | 3 | 24 | 42% | -0.092 | 0.84 | 7 |
| US100 | 30 | 47% | +0.138 | 1.28 | 3 | 14 | 29% | -0.210 | 0.67 | 3 |
| USDJPY | 28 | 32% | -0.395 | 0.42 | 5 | 18 | 56% | +0.199 | 1.45 | 3 |
| TOTAL | 155 | 48% | +0.014 | 1.03 | 6 | 99 | 42% | -0.092 | 0.83 | 7 |

**G2 solo pin bar**

| Par | IS n | IS % | IS R | IS PF | IS racha | OOS n | OOS % | OOS R | OOS PF | OOS racha |
|---|---|---|---|---|---|---|---|---|---|---|
| XAUUSD | 40 | 75% | +0.529 | 3.12 | 3 | 25 | 40% | +0.019 | 1.03 | 6 |
| EURUSD | 35 | 31% | -0.318 | 0.54 | 11 | 25 | 40% | -0.070 | 0.88 | 4 |
| GBPUSD | 27 | 37% | -0.219 | 0.62 | 5 | 23 | 44% | -0.045 | 0.92 | 5 |
| US100 | 30 | 43% | +0.067 | 1.12 | 3 | 26 | 50% | +0.183 | 1.38 | 3 |
| USDJPY | 31 | 42% | -0.010 | 0.98 | 5 | 21 | 62% | +0.235 | 1.62 | 3 |
| TOTAL | 163 | 47% | +0.036 | 1.07 | 11 | 120 | 47% | +0.061 | 1.12 | 6 |

**G3 solo ruptura**

| Par | IS n | IS % | IS R | IS PF | IS racha | OOS n | OOS % | OOS R | OOS PF | OOS racha |
|---|---|---|---|---|---|---|---|---|---|---|
| XAUUSD | 29 | 55% | +0.015 | 1.03 | 5 | 18 | 33% | -0.144 | 0.77 | 3 |
| EURUSD | 23 | 26% | -0.573 | 0.22 | 7 | 16 | 38% | -0.395 | 0.28 | 4 |
| GBPUSD | 15 | 33% | -0.178 | 0.65 | 3 | 12 | 25% | -0.442 | 0.36 | 5 |
| US100 | 21 | 38% | -0.157 | 0.71 | 3 | 11 | 54% | +0.164 | 1.36 | 3 |
| USDJPY | 26 | 35% | -0.409 | 0.38 | 7 | 6 | 50% | -0.172 | 0.66 | 2 |
| TOTAL | 114 | 39% | -0.257 | 0.55 | 10 | 63 | 38% | -0.213 | 0.63 | 5 |

**G4 sin ruptura**

| Par | IS n | IS % | IS R | IS PF | IS racha | OOS n | OOS % | OOS R | OOS PF | OOS racha |
|---|---|---|---|---|---|---|---|---|---|---|
| XAUUSD | 58 | 67% | +0.316 | 1.96 | 4 | 35 | 43% | -0.019 | 0.97 | 7 |
| EURUSD | 63 | 44% | -0.020 | 0.96 | 7 | 37 | 43% | -0.023 | 0.96 | 5 |
| GBPUSD | 44 | 48% | -0.046 | 0.91 | 4 | 38 | 42% | -0.123 | 0.78 | 8 |
| US100 | 50 | 44% | +0.044 | 1.08 | 3 | 36 | 42% | +0.044 | 1.08 | 4 |
| USDJPY | 48 | 40% | -0.151 | 0.75 | 8 | 32 | 56% | +0.169 | 1.39 | 4 |
| TOTAL | 263 | 49% | +0.038 | 1.08 | 9 | 178 | 45% | +0.005 | 1.01 | 8 |

**X1 todo en TP1**

| Par | IS n | IS % | IS R | IS PF | IS racha | OOS n | OOS % | OOS R | OOS PF | OOS racha |
|---|---|---|---|---|---|---|---|---|---|---|
| XAUUSD | 71 | 61% | +0.261 | 1.68 | 4 | 42 | 40% | -0.102 | 0.82 | 7 |
| EURUSD | 73 | 40% | -0.154 | 0.74 | 8 | 43 | 40% | -0.103 | 0.82 | 5 |
| GBPUSD | 48 | 46% | -0.043 | 0.92 | 4 | 41 | 44% | -0.037 | 0.93 | 8 |
| US100 | 66 | 44% | -0.022 | 0.96 | 3 | 42 | 43% | -0.014 | 0.98 | 5 |
| USDJPY | 62 | 36% | -0.299 | 0.54 | 9 | 36 | 53% | +0.092 | 1.21 | 4 |
| TOTAL | 320 | 45% | -0.046 | 0.91 | 11 | 204 | 44% | -0.037 | 0.93 | 8 |

**X2 fijo 1.5R**

| Par | IS n | IS % | IS R | IS PF | IS racha | OOS n | OOS % | OOS R | OOS PF | OOS racha |
|---|---|---|---|---|---|---|---|---|---|---|
| XAUUSD | 69 | 52% | +0.244 | 1.51 | 5 | 43 | 42% | +0.044 | 1.08 | 7 |
| EURUSD | 73 | 36% | -0.138 | 0.78 | 9 | 41 | 34% | -0.150 | 0.76 | 5 |
| GBPUSD | 45 | 42% | -0.054 | 0.9 | 4 | 40 | 35% | -0.108 | 0.83 | 8 |
| US100 | 64 | 41% | +0.043 | 1.08 | 5 | 41 | 39% | -0.017 | 0.97 | 5 |
| USDJPY | 61 | 30% | -0.276 | 0.61 | 15 | 34 | 47% | +0.145 | 1.27 | 4 |
| TOTAL | 312 | 40% | -0.031 | 0.95 | 17 | 199 | 39% | -0.022 | 0.96 | 8 |

**X3 fijo 2R**

| Par | IS n | IS % | IS R | IS PF | IS racha | OOS n | OOS % | OOS R | OOS PF | OOS racha |
|---|---|---|---|---|---|---|---|---|---|---|
| XAUUSD | 67 | 46% | +0.290 | 1.54 | 6 | 42 | 38% | +0.128 | 1.22 | 7 |
| EURUSD | 71 | 32% | -0.092 | 0.86 | 9 | 41 | 32% | -0.114 | 0.82 | 5 |
| GBPUSD | 44 | 36% | -0.114 | 0.81 | 4 | 38 | 29% | -0.140 | 0.8 | 8 |
| US100 | 64 | 33% | +0.011 | 1.02 | 8 | 40 | 38% | +0.081 | 1.13 | 5 |
| USDJPY | 62 | 26% | -0.247 | 0.67 | 15 | 34 | 44% | +0.229 | 1.41 | 4 |
| TOTAL | 308 | 35% | -0.022 | 0.97 | 17 | 195 | 36% | +0.033 | 1.05 | 8 |

**X4 parcial sin BE**

| Par | IS n | IS % | IS R | IS PF | IS racha | OOS n | OOS % | OOS R | OOS PF | OOS racha |
|---|---|---|---|---|---|---|---|---|---|---|
| XAUUSD | 67 | 57% | +0.140 | 1.35 | 4 | 41 | 39% | -0.018 | 0.97 | 7 |
| EURUSD | 70 | 40% | -0.092 | 0.84 | 8 | 39 | 36% | -0.159 | 0.71 | 7 |
| GBPUSD | 44 | 43% | -0.095 | 0.81 | 4 | 39 | 38% | -0.096 | 0.83 | 8 |
| US100 | 64 | 38% | -0.019 | 0.96 | 6 | 39 | 38% | +0.011 | 1.02 | 5 |
| USDJPY | 61 | 28% | -0.278 | 0.57 | 15 | 34 | 47% | +0.187 | 1.4 | 4 |
| TOTAL | 306 | 41% | -0.064 | 0.88 | 17 | 192 | 40% | -0.020 | 0.96 | 8 |

**X5 sin niveles (1.5R/3R)**

| Par | IS n | IS % | IS R | IS PF | IS racha | OOS n | OOS % | OOS R | OOS PF | OOS racha |
|---|---|---|---|---|---|---|---|---|---|---|
| XAUUSD | 554 | 48% | +0.088 | 1.17 | 9 | 346 | 45% | -0.010 | 0.98 | 7 |
| EURUSD | 611 | 45% | -0.021 | 0.96 | 9 | 430 | 43% | -0.092 | 0.83 | 8 |
| GBPUSD | 495 | 40% | -0.152 | 0.73 | 16 | 413 | 45% | -0.068 | 0.87 | 9 |
| US100 | 541 | 44% | -0.017 | 0.97 | 12 | 336 | 48% | +0.056 | 1.11 | 13 |
| USDJPY | 543 | 39% | -0.165 | 0.71 | 10 | 366 | 47% | -0.059 | 0.88 | 7 |
| TOTAL | 2744 | 43% | -0.050 | 0.91 | 16 | 1891 | 46% | -0.039 | 0.92 | 13 |

