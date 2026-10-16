# Constitución del proyecto MT5 Señales

Reglas permanentes que toda spec, plan y tarea debe cumplir. Aprobada el 15-oct-2026.

1. EL SISTEMA no ejecuta auto-trading en un par salvo que `history_allows_auto` lo apruebe con el criterio vigente (ambos tramos ≥ +0.05R, n ≥ 30 por tramo, t ≥ 2).
2. Todo backtest que alimente decisiones incluye spread, comisión y deslizamiento por símbolo.
3. Toda hipótesis nueva se registra con su criterio de éxito antes de ejecutarse y suma al contador global de intentos.
4. Ningún cambio de lógica de señales, riesgo u órdenes se integra sin tests en `tests/` y `python -m pytest tests -q` en verde.
5. Sin MT5 conectado, la app no genera, registra ni ejecuta señales; los datos simulados solo sirven para la vista.
6. Las acciones que tocan la cuenta (órdenes, cierres, kill switch) solo afectan a las posiciones del bot (`MAGIC_NUMBER`) salvo confirmación explícita.
7. Stack: Python (FastAPI, MetaTrader5, pandas) + React/Vite; código, textos de UI y documentación en español.
