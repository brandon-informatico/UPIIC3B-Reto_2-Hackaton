"""Nombres de archivo seguros a partir de datos externos.

El capture_id viene de capturas.json: si se usara tal cual en una ruta, un ID como "../../x" escribiría o
leería fuera de cache/. Los IDs normales (CAP-123456) no cambian, así que la caché existente sigue sirviendo.
"""
from __future__ import annotations

import hashlib
import re

_SEGURO = re.compile(r"^[A-Za-z0-9_-]{1,64}$")  # mismo criterio que ID_VALIDO del dashboard


def nombre_archivo(capture_id: object) -> str:
    """capture_id tal cual si es seguro; si no, un nombre estable derivado de su hash."""
    texto = str(capture_id)
    if _SEGURO.match(texto):
        return texto
    return "id-" + hashlib.sha256(texto.encode("utf-8")).hexdigest()[:16]
