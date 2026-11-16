"""Claves de acceso del motor para usarlo fuera de este PC (VPS).

Sin claves configuradas, el motor se comporta como siempre: escucha solo en 127.0.0.1 y los permisos dependen
del origen (panel local = operar, orígenes de allowed_origins.local = lectura u operar).

Con claves (variables MT5_TOKEN_OPERAR y/o MT5_TOKEN_LECTURA, o el archivo motor.env), TODA petición salvo
/status necesita una clave válida:
- HTTP: cabecera  Authorization: Bearer <clave>
- WebSocket: el navegador no deja poner cabeceras, así que va como subprotocolo  ["bearer", "<clave>"]
  (no en la URL, que acabaría en registros de proxies).
La clave de lectura ve precios, señales y posiciones; solo la de operar envía órdenes, cierra o toca el kill switch.
"""
from __future__ import annotations

import hmac
import os
from pathlib import Path
from typing import MutableMapping, Optional

ENV_FILE = Path(__file__).with_name("motor.env")
OPERAR, LECTURA = "operar", "lectura"
MIN_TOKEN_LENGTH = 24  # python -c "import secrets; print(secrets.token_urlsafe(32))" da 43 caracteres


def load_env_file(path: Path = ENV_FILE, environ: MutableMapping[str, str] = os.environ) -> list[str]:
    """Carga CLAVE=valor por línea (# comenta). No pisa variables ya definidas. Devuelve los nombres cargados."""
    if not path.is_file():
        return []
    loaded = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in environ:
            environ[key] = value
            loaded.append(key)
    return loaded


class AccessKeys:
    def __init__(self, trade: str = "", read: str = ""):
        trade, read = (trade or "").strip(), (read or "").strip()
        for name, value in (("MT5_TOKEN_OPERAR", trade), ("MT5_TOKEN_LECTURA", read)):
            if value and len(value) < MIN_TOKEN_LENGTH:
                raise ValueError(f"{name} es demasiado corta (mínimo {MIN_TOKEN_LENGTH} caracteres)")
        if trade and trade == read:
            raise ValueError("MT5_TOKEN_OPERAR y MT5_TOKEN_LECTURA deben ser distintas")
        self._trade, self._read = trade, read

    @property
    def enabled(self) -> bool:
        return bool(self._trade or self._read)

    def level(self, token: Optional[str]) -> Optional[str]:
        """'operar', 'lectura' o None. Comparación en tiempo constante."""
        if not token:
            return None
        token = token.strip()
        if self._trade and hmac.compare_digest(token.encode(), self._trade.encode()):
            return OPERAR
        if self._read and hmac.compare_digest(token.encode(), self._read.encode()):
            return LECTURA
        return None


def keys_from_env(environ: MutableMapping[str, str] = os.environ) -> AccessKeys:
    return AccessKeys(environ.get("MT5_TOKEN_OPERAR", ""), environ.get("MT5_TOKEN_LECTURA", ""))


def bearer_from_header(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    scheme, _, token = value.strip().partition(" ")
    return token.strip() or None if scheme.lower() == "bearer" else None


def bearer_from_subprotocols(value: Optional[str]) -> Optional[str]:
    """Cabecera Sec-WebSocket-Protocol: 'bearer, <clave>'."""
    if not value:
        return None
    parts = [p.strip() for p in value.split(",")]
    if len(parts) >= 2 and parts[0].lower() == "bearer" and parts[1]:
        return parts[1]
    return None
