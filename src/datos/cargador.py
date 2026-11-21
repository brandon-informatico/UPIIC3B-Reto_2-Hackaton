"""E1 · Lee data/capturas.json → list[CapturaPreparada] (sin decision_esperada ni motivo_rechazo)."""
from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from contratos import CapturaPreparada, IndiceFotos
from src.datos.imagenes import TIPOS_FOTO, ruta_portatil
from src.datos.limpieza import limpiar_captura, limpiar_codigo, limpiar_numero, limpiar_precio, limpiar_texto

log = logging.getLogger(__name__)

CAMPOS_PREPARADA = set(CapturaPreparada.model_fields) - {"rutas", "banderas_datos"}


def resolver_rutas(captura: dict[str, Any], base_imagenes: Path,
                   indice: IndiceFotos | None = None) -> tuple[dict[str, str | None], list[str]]:
    """Ubica las 3 fotos: primero ``<tipo>_file`` relativo a ``base_imagenes``; si no existe, por nombre en
    ``indice``. Regresa (rutas, banderas) con ``imagen_faltante:<tipo>`` para lo que no se encontró."""
    rutas: dict[str, str | None] = {}
    banderas: list[str] = []
    por_nombre = (indice.capturas if indice else {}).get(str(captura.get("capture_id") or "").upper(), {})
    for tipo in TIPOS_FOTO:
        ruta = None
        relativa = captura.get(f"{tipo}_file")
        if relativa and (Path(base_imagenes) / relativa).is_file():
            ruta = Path(base_imagenes) / relativa
        elif por_nombre.get(tipo):
            ruta = Path(por_nombre[tipo])
        rutas[tipo] = ruta_portatil(ruta) if ruta else None
        if ruta is None:
            banderas.append(f"imagen_faltante:{tipo}")
    return rutas, banderas


def cargar_capturas(ruta_capturas: Path, base_imagenes: Path | None = None,
                    indice: IndiceFotos | None = None) -> list[CapturaPreparada]:
    """Contrato E1: capturas limpias y validadas, en el orden de capturas.json.

    - ``base_imagenes``: carpeta desde la que se resuelven las rutas ``imagenes/...`` (por defecto, la carpeta de
      capturas.json). ``indice`` (de ``separar_fotos``) es el respaldo para fotos que no están donde dicen.
    - Un ``capture_id`` repetido se conserva una sola vez (la primera aparición) y se registra.
    - Un registro que no cumple el contrato (p. ej. sin ``capture_id`` válido) se registra como error y se omite.
    """
    ruta_capturas = Path(ruta_capturas)
    base_imagenes = Path(base_imagenes) if base_imagenes else ruta_capturas.parent
    datos = json.loads(ruta_capturas.read_text(encoding="utf-8-sig"))
    if isinstance(datos, dict):  # tolera {"capturas": [...]}
        datos = datos.get("capturas", list(datos.values()))
    capturas: list[CapturaPreparada] = []
    vistos: set[str] = set()
    for i, cruda in enumerate(datos):
        if not isinstance(cruda, dict):
            log.error("Registro %d de %s no es un objeto; se omite", i, ruta_capturas.name)
            continue
        limpia = limpiar_captura(cruda)
        cid = limpia.get("capture_id")
        if cid in vistos:
            log.warning("capture_id duplicado %s; se conserva la primera aparición", cid)
            continue
        rutas, banderas_fotos = resolver_rutas(limpia, base_imagenes, indice)
        try:
            captura = CapturaPreparada(**{k: limpia.get(k) for k in CAMPOS_PREPARADA}, rutas=rutas,
                                       banderas_datos=limpia["banderas_datos"] + banderas_fotos)
        except ValidationError as error:
            log.error("Registro %d (%s) no cumple CapturaPreparada; se omite: %s", i, cid,
                      "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in error.errors()))
            continue
        vistos.add(captura.capture_id)
        capturas.append(captura)
    log.info("Capturas cargadas: %d de %d registros", len(capturas), len(datos))
    return capturas


def cargar_catalogo(ruta: Path) -> dict[int, dict[str, Any]]:
    """Catálogo de referencia por ``id_product`` (códigos como texto, precios a 2 decimales)."""
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
