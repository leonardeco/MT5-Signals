# Riesgo y seguridad

## La cuenta

| Capa | Regla | Dónde |
|---|---|---|
| Riesgo por operación | 1 % del balance hasta el SL, spread incluido. Si hasta el lote mínimo arriesga más, la orden se rechaza | `signal_engine.py`, `main.py · risk_capped_volume` |
| Lote del cliente | El servidor recalcula el máximo con el precio actual y **nunca sube** el volumen pedido | `main.py · cap_volume` |
| Kill switch | −3 % diario sobre el balance de inicio. Bloquea entradas, apaga el auto-trading y persiste tras reinicios | `risk_guardian.py` |
| Noticias | Bloquea 15 min antes y después de un evento de alto impacto de las divisas del símbolo. **Sin calendario de menos de 12 h, bloquea** | `news_filter.py` |
| Sesión | Entradas solo de 02:00 a 15:00 hora de Colombia, de lunes a viernes | `news_filter.py` |
| Exposición | Máximo 2 símbolos abiertos por divisa, oro o índice | `news_filter.py · exposure_check` |
| Auto-trading | Solo en símbolos que pasan `history_allows_auto` (ambos tramos ≥ +0,05R, n ≥ 30 por tramo, t ≥ 2) | `main.py` |
| Cierre de emergencia | Solo posiciones con `MAGIC_NUMBER = 202605`. Las manuales y las de otros EAs no se tocan | `risk_guardian.py` |
| Parcial en el broker | El plan va en dos órdenes (TP1 y TP2); el broker cierra la mitad aunque la app esté apagada | `execution.py` |

**Límite conocido.** Mover la pata TP2 a breakeven sí necesita la app abierta.

## El motor

El motor escucha solo en `127.0.0.1`: nada fuera de este PC puede conectarse. El riesgo real está en el navegador, porque cualquier página abierta podría intentar llamar a `127.0.0.1:8765`.

| Defensa | Efecto |
|---|---|
| Lista de orígenes | CORS solo responde a orígenes conocidos; un WebSocket de otro origen se cierra con `1008` |
| Middleware de escritura | Un `POST` de un origen sin permiso de operar recibe 403 **antes** de llegar al endpoint. Esto cubre los POST «simples», que el navegador envía sin preflight |
| Dos niveles | `operar`: el panel local (5180/4180) y los orígenes marcados así. `lectura`: los demás orígenes de `allowed_origins.local` |
| Red privada | El preflight de Chrome desde una página https se acepta solo para orígenes permitidos |
| Encabezados en Vercel | CSP estricta (`script-src 'self'`, `frame-ancestors 'none'`), `nosniff`, `no-referrer` y `Permissions-Policy` cerrada |

### Por qué el panel publicado es de solo lectura

El código de `mt5-signals.vercel.app` sale del repositorio de GitHub y de la cuenta de Vercel. Si alguna de las dos se viera comprometida, ese código correría en tu navegador con el origen autorizado. Con permiso de solo lectura podría ver la cuenta, pero no operar. El panel local se sirve desde tu disco y no tiene ese riesgo.

### Lo que no hay que hacer

- **No expongas el motor a internet** con un túnel público (ngrok, Cloudflare Tunnel abierto, port forwarding). El control de origen protege del navegador, no de un cliente que llama directamente sin `Origin`. Si algún día quieres verlo desde el móvil, usa una red privada (Tailscale) y añade antes autenticación por token.
- No subas `allowed_origins.local`, `quant_terminal.db` ni `news_cache.json`; `.gitignore` ya los excluye.
