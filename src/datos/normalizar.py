"""E2 · Visión local sin tokens → FeaturesCaptura, una por capture_id (contratos.py). Responsable: Copa.

Por captura: verifica cada foto, guarda una copia reducida con luz emparejada para la IA (``ruta_normalizada``),
mide nitidez comparable entre capturas, lee códigos de barras y compara producto contra etiqueta. Nunca se
detiene por una foto mala: la anota en ``errores`` y sigue con las demás.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np

from contratos import CapturaPreparada, FeaturesCaptura
from src.datos.imagenes import (PARAMETROS_DEFECTO, RAIZ, TIPOS_FOTO, CacheFachadas, mismo_codigo, parecido,
                                procesar_foto, ruta_absoluta)

log = logging.getLogger(__name__)


def _estado_codigo(leidos: list[str], esperado: str | None, si_distinto: str) -> str:
    if not leidos:
        return "no_leido"
    return "coincide" if any(mismo_codigo(c, esperado) for c in leidos) else si_distinto


def normalizar_captura(captura: CapturaPreparada, ruta_cache: Path, cache_fachadas: CacheFachadas,
                       parametros: dict[str, Any]) -> FeaturesCaptura:
    """Una captura → FeaturesCaptura. Nunca lanza excepción."""
    partes: dict[str, dict[str, Any] | None] = {tipo: None for tipo in TIPOS_FOTO}
    reducidas: dict[str, np.ndarray] = {}
    errores: list[str] = []
    for tipo in TIPOS_FOTO:
        ruta = ruta_absoluta(captura.rutas.get(tipo))
        if ruta is None or not ruta.is_file():
            errores.append(f"{tipo}: faltante")
            continue
        try:
            partes[tipo], reducidas[tipo] = procesar_foto(ruta, tipo, captura.capture_id, ruta_cache,
                                                         parametros, cache_fachadas)
        except Exception as error:  # una foto mala no detiene la captura
            errores.append(f"{tipo}: corrupta ({error})")
            log.warning("%s %s: %s", captura.capture_id, tipo, error)

    presentes = sum(p is not None for p in partes.values())
    empaque = [c["texto"] for c in (partes["product"] or {}).get("codigos_leidos") or []]
    etiqueta = [c["texto"] for c in (partes["shelf"] or {}).get("codigos_leidos") or []]
    try:
        return FeaturesCaptura(
            capture_id=captura.capture_id,
            estado="completa" if presentes == 3 else "sin_fotos" if presentes == 0 else "incompleta",
            **partes,
            parecido_producto_etiqueta=(parecido(reducidas["product"], reducidas["shelf"])
                                        if "product" in reducidas and "shelf" in reducidas else None),
            codigo_empaque=_estado_codigo(empaque, captura.product_barcode, "no_coincide"),
            codigo_etiqueta=_estado_codigo(etiqueta, captura.product_barcode, "distinto"),
            errores=errores,
        )
    except Exception as error:  # no debería pasar; si pasa, la captura sigue presente y válida
        log.exception("%s: no se pudo armar FeaturesCaptura", captura.capture_id)
        return FeaturesCaptura(capture_id=captura.capture_id, estado="sin_fotos", codigo_empaque="no_leido",
                               codigo_etiqueta="no_leido", errores=errores + [f"features: {error}"])


def normalizar(capturas: list[CapturaPreparada], ruta_cache: Path = RAIZ / "cache",
               parametros: dict[str, Any] | None = None, hilos: int = 6) -> list[FeaturesCaptura]:
    """Contrato E2: una FeaturesCaptura por captura (aunque no tenga fotos), en el mismo orden."""
    parametros = {**PARAMETROS_DEFECTO, **(parametros or {})}
    cache_fachadas = CacheFachadas()
    with ThreadPoolExecutor(max_workers=max(1, hilos)) as ejecutor:
        features = list(ejecutor.map(
            lambda c: normalizar_captura(c, Path(ruta_cache), cache_fachadas, parametros), capturas))
    log.info("Fotos normalizadas: %d capturas, %d fachadas distintas", len(features), len(cache_fachadas))
    return features
