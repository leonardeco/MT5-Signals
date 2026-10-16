# Laboratorio de investigación

Este es el flujo para probar una idea sin engañarse. Sigue la constitución (`docs/constitution.md`): principios 2, 3 y 4.

## Piezas

| Archivo | Para qué sirve |
|---|---|
| `costs.py` + `costes.json` | Coste extra por operación y símbolo: spread real menos el de las velas, deslizamiento y comisión. Lo usan `backtest.py` (y por tanto el filtro del auto-trading) y el laboratorio |
| `research/data.py` | Historial largo desde MT5 con caché (`research/cache/rates_<símbolo>_<marco>.pkl`) y medición del spread real de los ticks (`research/cache/spreads.json`) |
| `research/registry.py` + `registro_hipotesis.json` | Registro de hipótesis con su criterio, **antes** de mirar resultados. Cuenta los intentos: los 20 de `INFORME_VARIANTES.md` ya están dentro |
| `research/robustness.py` | t, IC95 bootstrap, Sharpe por operación, Sharpe deflactado (DSR) con el nº de intentos, Monte Carlo del drawdown, tramos 60/40 y 5 bloques |
| `research/lab.py` | Ejecuta una hipótesis registrada, descuenta costes, evalúa el criterio y guarda `research/resultados/<id>.json` |
| `research/hipotesis/*.py` | El código de cada hipótesis: `run() -> [{"symbol", "t", "r", "risk_px", "price"?}]` |

## Criterio por defecto (tras costes)

- t ≥ 2,
- Sharpe deflactado ≥ 0.95 con todos los intentos registrados,
- media positiva en el tramo antiguo (60 %) **y** en el reciente (40 %),
- n ≥ 100.

## Cómo probar una idea nueva

```python
from research import registry
registry.register("H-A", "Momentum intradía US100",
                  "El signo de los primeros 30 min tras la apertura de contado predice los últimos 30 min",
                  criterio=None)  # None = criterio por defecto
```

1. Registrarla, como arriba, **antes** de escribir el código que la mide.
2. Escribir `research/hipotesis/h_a.py` con `run()`.
3. Ejecutar `python -m research.lab H-A`. Solo se puede evaluar una vez. Si se retoca, la versión retocada es otra idea con otro id y suma un intento más.

## Datos

```
python -m research.data spreads 2      # spread real de los ticks (MT5 abierto)
python -m research.data rates D1 H1    # historial largo; D1 llega a 2000 (FX) / 2004 (oro) en MetaQuotes-Demo
python research/cache_frames.py 340    # frames M5/M15/H1/D1/W1 del backtest del motor
```

## Prueba a futuro (fase 4)

`forward.py` mide el motor y H-B solo con datos posteriores a la congelación (`forward_config.json`), netos de costes
y sin enviar órdenes. `python forward.py run` o el panel de la app actualizan `forward_results.json`. Si cambia un
archivo de reglas, el informe lo marca: congelar de nuevo sería empezar la prueba desde cero.
