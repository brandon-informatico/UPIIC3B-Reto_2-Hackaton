"""E1/E2 · Separa las fotos de cada captura → IndiceFotos (contratos.py). Responsable: Copa.

Agrupa fotos sueltas por nombre de archivo: ``CAP-123456_facade.jpg``, ``_product``, ``_shelf`` y sinónimos
(fachada, producto, etiqueta, anaquel, label). Es el respaldo cuando las rutas de los metadatos no existen
(p. ej. el set ciego llega con otra estructura de carpetas).
"""
from __future__ import annotations

import re
from pathlib import Path

from contratos import IndiceFotos

EXTENSIONES = {".jpg", ".jpeg", ".png", ".webp"}
SINONIMOS_TIPO = {
    "facade": "facade", "fachada": "facade",
    "product": "product", "producto": "product",
    "shelf": "shelf", "etiqueta": "shelf", "anaquel": "shelf", "label": "shelf",
}
_PATRON_NOMBRE = re.compile(r"^(?P<id>CAP-\d+)[_\-](?P<tipo>[a-zA-Z]+)$", re.IGNORECASE)


def separar_fotos(carpeta: Path) -> IndiceFotos:
    """Recorre ``carpeta`` (con subcarpetas) → {capture_id: {"facade"|"product"|"shelf": ruta}}.

    Si hay dos fotos del mismo tipo para una captura, se queda la primera en orden alfabético.
    """
    capturas: dict[str, dict[str, str]] = {}
    carpeta = Path(carpeta)
    if carpeta.exists():
        for foto in sorted(carpeta.rglob("*")):
            if foto.suffix.lower() not in EXTENSIONES:
                continue
            coincidencia = _PATRON_NOMBRE.match(foto.stem)
            tipo = SINONIMOS_TIPO.get(coincidencia.group("tipo").lower()) if coincidencia else None
            if tipo:
                capturas.setdefault(coincidencia.group("id").upper(), {}).setdefault(tipo, str(foto))
    return IndiceFotos(capturas=capturas)
