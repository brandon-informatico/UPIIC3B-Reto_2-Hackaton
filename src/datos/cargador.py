"""Lee capturas.json y el catálogo de productos (contrato de CONTEXT.md, sección 4)."""
from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any

from src.datos.limpieza import limpiar_captura, limpiar_codigo, limpiar_numero, limpiar_precio, limpiar_texto

log = logging.getLogger(__name__)


def cargar_capturas(ruta: Path, incluir_etiquetas: bool = False) -> list[dict[str, Any]]:
    """Capturas limpias con sus campos oficiales y ``banderas_datos``.

    - ``decision_esperada`` y ``motivo_rechazo`` se quitan salvo ``incluir_etiquetas=True``
      (solo para evaluación; el motor nunca debe verlas).
    - Si un ``capture_id`` se repite se conserva la primera aparición y se registra una advertencia,
      para que la salida tenga exactamente un resultado por captura.
    """
    ruta = Path(ruta)
    datos = json.loads(ruta.read_text(encoding="utf-8-sig"))
    if isinstance(datos, dict):  # tolera {"capturas": [...]}
        datos = datos.get("capturas", list(datos.values()))
    capturas: list[dict[str, Any]] = []
    vistos: set[str] = set()
    for i, cruda in enumerate(datos):
        if not isinstance(cruda, dict):
            log.warning("Registro %d de %s no es un objeto; se omite", i, ruta.name)
            continue
        captura = limpiar_captura(cruda, incluir_etiquetas=incluir_etiquetas)
        cid = captura.get("capture_id")
        if cid is None:
            log.warning("Registro %d sin capture_id; se omite", i)
            continue
        if cid in vistos:
            log.warning("capture_id duplicado %s; se conserva la primera aparición", cid)
            continue
        vistos.add(cid)
        capturas.append(captura)
    log.info("Capturas cargadas: %d de %d registros", len(capturas), len(datos))
    return capturas


def cargar_catalogo(ruta: Path) -> dict[int, dict[str, Any]]:
    """Catálogo de referencia indexado por ``id_product``."""
    catalogo: dict[int, dict[str, Any]] = {}
    with Path(ruta).open(encoding="utf-8-sig", newline="") as archivo:
        for fila in csv.DictReader(archivo):
            id_producto = limpiar_numero(fila.get("id_product"))
            if id_producto is None:
                continue
            registro: dict[str, Any] = {}
            for campo, valor in fila.items():
                if campo is None:
                    continue
                if campo == "product_barcode":
                    registro[campo] = limpiar_codigo(valor)
                elif campo in ("product_price", "min_product_price", "max_product_price"):
                    registro[campo] = limpiar_precio(valor)
                elif campo == "unit_quantity_product":
                    registro[campo] = limpiar_numero(valor)
                else:
                    registro[campo] = limpiar_texto(valor)
            registro["id_product"] = int(id_producto)
            catalogo[int(id_producto)] = registro
    log.info("Catálogo cargado: %d productos", len(catalogo))
    return catalogo
