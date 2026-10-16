# Investigación

## Conclusión actual

| Estrategia | Datos | Neto por operación | t | DSR | Veredicto |
|---|---|---|---|---|---|
| Motor intradía (control C-MOTOR-ACTUAL) | 340 días, 441 ops | −0,04R | −0,72 | 0,005 | No pasa |
| H-A · momentum intradía US100 | M15 2024-2026, 617 ops | −0,060R | −1,70 | 0,001 | Descartada |
| H-B · tendencia 12 meses en D1 | 2000-2026, 1 256 ops | +0,067R | 2,22 | 0,61 | No pasa (falla solo el DSR) |

Con 22 intentos sobre los mismos mercados, el Sharpe deflactado exige más de lo que H-B ofrece: hay un 39 % de probabilidad de que su resultado sea suerte de selección. La vía honesta es la **prueba a futuro**: los datos posteriores a la congelación (15-oct-2026 08:10 UTC) no sufren ese sesgo.

H-B genera una operación al mes por símbolo, así que hacen falta al menos 3 meses (≈ 15 operaciones) para empezar a leer algo.

## Criterios

| Para | Regla |
|---|---|
| Activar auto-trading en un par | Ambos tramos del backtest ≥ +0,05R con ≥ 30 operaciones cada uno y t ≥ 2, tras costes |
| Aceptar una hipótesis nueva | t ≥ 2, DSR ≥ 0,95 con todos los intentos registrados, ambos tramos (60/40) positivos y n ≥ 100 |

## Cómo probar una idea

1. Regístrala con su criterio **antes** de escribir el código (`research/registry.py`). Cuenta como un intento más.
2. Escribe `research/hipotesis/<id>.py` con `run()`.
3. Ejecuta `python -m research.lab <ID>`. Solo se evalúa una vez; un retoque es otra hipótesis.

Detalle de las herramientas en [LABORATORIO.md](../research/LABORATORIO.md).

## Prueba a futuro

```powershell
python forward.py run      # o el panel «Prueba a futuro»
```

Las reglas congeladas son `setups.py`, `signal_engine.py`, `backtest.py`, `costs.py` y `research/hipotesis/h_b.py`. Si cambia una sola línea de ellas, el panel lo marca y la prueba deja de valer. `.gitattributes` fija los fines de línea para que un clon en Windows no altere las huellas.

## Informes

- [Variantes del motor](../research/INFORME_VARIANTES.md): los 20 intentos iniciales.
- [Diagnóstico y hoja de ruta](../research/DIAGNOSTICO_Y_HOJA_DE_RUTA.md): auditoría, fuentes y fases.
- [Fase 2](../research/INFORME_FASE2.md): H-A y H-B en detalle.
