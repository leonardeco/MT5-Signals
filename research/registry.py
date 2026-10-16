"""Registro de hipótesis: cada idea se apunta con su criterio de éxito ANTES de mirar resultados.

Reglas (constitución, principio 3):
- Una hipótesis se registra una sola vez y se evalúa una sola vez. Reajustarla y volver a correrla es un intento
  nuevo con otro id, y suma al contador.
- `n_trials()` cuenta todos los intentos de tipo "hipotesis" (incluidos los 20 de INFORME_VARIANTES.md). Es el número
  que usa el Sharpe deflactado: cuantos más intentos, más alto el listón.
- Los controles (tipo "control", p. ej. volver a medir el motor actual con costes) no suman y pueden repetirse.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

REGISTRY_PATH = Path(__file__).with_name("registro_hipotesis.json")
KINDS = ("hipotesis", "control")

# Criterio por defecto (INFORME / hoja de ruta, fase 2): tras costes
DEFAULT_CRITERIO = {"t_min": 2.0, "dsr_min": 0.95, "tramos_positivos": True, "n_min": 100}


class RegistryError(Exception):
    pass


def load(path: Path = REGISTRY_PATH) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"entradas": []}


def save(data: dict, path: Path = REGISTRY_PATH) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get(hid: str, path: Path = REGISTRY_PATH) -> dict | None:
    return next((e for e in load(path)["entradas"] if e["id"] == hid), None)


def n_trials(path: Path = REGISTRY_PATH) -> int:
    return sum(1 for e in load(path)["entradas"] if e["tipo"] == "hipotesis")


def register(hid: str, titulo: str, hipotesis: str, criterio: dict | None = None, tipo: str = "hipotesis",
             path: Path = REGISTRY_PATH) -> dict:
    if tipo not in KINDS:
        raise RegistryError(f"Tipo desconocido: {tipo}")
    data = load(path)
    if any(e["id"] == hid for e in data["entradas"]):
        raise RegistryError(f"'{hid}' ya está registrada: una idea modificada necesita un id nuevo")
    entry = {
        "id": hid,
        "tipo": tipo,
        "titulo": titulo,
        "hipotesis": hipotesis,
        "criterio": criterio or dict(DEFAULT_CRITERIO),
        "registrada": datetime.now().isoformat(timespec="seconds"),
        "estado": "registrada",
        "resultado": None,
    }
    data["entradas"].append(entry)
    save(data, path)
    return entry


def record_result(hid: str, resultado: dict, paso: bool, path: Path = REGISTRY_PATH) -> dict:
    data = load(path)
    entry = next((e for e in data["entradas"] if e["id"] == hid), None)
    if entry is None:
        raise RegistryError(f"'{hid}' no está registrada: regístrala con su criterio antes de evaluarla")
    if entry["tipo"] == "hipotesis" and entry["estado"] != "registrada":
        raise RegistryError(f"'{hid}' ya se evaluó ({entry['estado']}): no se re-evalúa una hipótesis")
    entry["estado"] = "pasa" if paso else "no pasa"
    entry["evaluada"] = datetime.now().isoformat(timespec="seconds")
    entry["resultado"] = resultado
    save(data, path)
    return entry
