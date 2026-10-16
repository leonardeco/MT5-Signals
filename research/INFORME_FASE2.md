# Fase 2: hipótesis con respaldo publicado (15-oct-2026)

Las dos se registraron, con reglas exactas y criterio, **antes** de escribir su código
(`research/registro_hipotesis.json`, 03:00:59). Se evaluaron una sola vez con `python -m research.lab`, con costes
(`costs.py`) y con 22 intentos acumulados en el Sharpe deflactado.
Criterio: t ≥ 2, DSR ≥ 0.95, los dos tramos (60/40) positivos y n ≥ 100.

## Resultado

| | n | Media bruta | Coste | **Media neta** | t | IC95 media | DSR | Tramo antiguo / reciente | ¿Pasa? |
|---|---|---|---|---|---|---|---|---|---|
| **H-A** momentum intradía US100 (M15, 2024-2026) | 617 | +0.001R | 0.061R | **−0.060R** | −1.70 | −0.13 … +0.01 | 0.001 | −0.107 / +0.006 | **No** |
| **H-B** momentum 12 meses D1, rebalanceo cada 21 sesiones (2000-2026) | 1 256 | +0.070R | 0.003R (+swap) | **+0.067R** | 2.22 | +0.01 … +0.13 | 0.61 | +0.087 / +0.040 | **No** (solo falla el DSR) |

### H-A — descartada
- La primera media hora no predice la última en el US100 de este broker: la media bruta es 0. El coste (spread + 1 punto)
  lo deja en negativo.
- 3 de los 5 bloques temporales son negativos. Es el resultado más claro posible: no hay nada que filtrar.

### H-B — la mejor encontrada hasta ahora, pero no demostrada
- Es positiva tras costes, con t = 2.22, los dos tramos positivos y 4 de 5 bloques positivos
  (+0.125, +0.070, +0.075, −0.027, +0.098).
- Lo que falla es el **Sharpe deflactado (0.61)**. Con 22 ideas probadas sobre datos de estos mismos mercados, el
  mejor Sharpe esperable por azar es 0.055 por operación y el de H-B es 0.063. Supera ese listón, pero por poco: hay un
  39 % de probabilidad de que sea suerte de selección. Por eso no cumple el criterio fijado de antemano y **no se
  automatiza**.
- Por símbolo (R neta por operación mensual, t):

  | Símbolo | Media neta | t |
  |---|---|---|
  | XAUUSD | +0.109 | 1.62 |
  | USDJPY | +0.098 | 1.57 |
  | US100 | +0.308 | 1.75 (solo 38 operaciones) |
  | GBPUSD | +0.039 | 0.67 |
  | EURUSD | −0.001 | −0.02 |

  EURUSD lleva 10 años sin aportar nada, en línea con la literatura (la tendencia en divisas se debilitó tras 2009).
- El swap se cuenta con las tasas actuales del broker y solo cuando cuesta (0.018R de media), así que es conservador
  para las posiciones con swap positivo. Las tasas del pasado eran distintas: es una aproximación.
- Magnitud: 1R = la volatilidad esperada del mes. +0.067R por mes y símbolo equivale a un Sharpe anual aproximado de
  0.2 por símbolo. Es una ventaja pequeña, como la que documenta la literatura reciente, no una máquina de dinero.
- **No se retoca.** Cambiar el periodo de 12 meses, quitar EURUSD o añadir filtros sería un intento nuevo (23, 24…)
  con un listón aún más alto, y sesgado por haber visto este resultado.

## Qué sigue

- **H-C** (usar el motor actual como filtro de entrada de H-A/H-B) no se ejecuta: estaba condicionada a que alguna pasara.
- La vía honesta para H-B es la **prueba a futuro sin operar** (fase 4). Los datos que aún no existen no sufren el
  problema de los 22 intentos. La app la registra en sombra con las reglas congeladas y compara contra lo esperado:
  +0.067R por operación, con 1 operación al mes por símbolo.
- El motor de señales intradía queda como **herramienta de lectura de contexto**. El auto-trading sigue bloqueado.
