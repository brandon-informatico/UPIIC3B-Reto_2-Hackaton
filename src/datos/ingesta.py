"""Ingesta local completa: capturas + catálogo + fotos → un archivo listo para el análisis con IA.

    python -m src.datos                       # usa las rutas de config.yaml
    python -m src.datos --capturas data/capturas.json --imagenes data/ --salida cache/ingesta.json

Escribe ``cache/ingesta.json`` (lista, un objeto por captura, en el mismo orden que capturas.json)::

    {
      "capture_id": "CAP-...",
      "captura": {...campos oficiales limpios..., "banderas_datos": [...]},   # sin decision_esperada
      "producto_catalogo": {...} | null,                                    # fila del catálogo por id_product
      "imagenes": {"facade": ruta|null, "product": ruta|null, "shelf": ruta|null},           # originales
      "imagenes_normalizadas": {"facade": ruta|null, "product": ruta|null, "shelf": ruta|null},  # para la IA
      "estado_imagenes": {"facade": "ok"|"faltante"|"corrupta", ...},
      "senales": {...},       # ver src/datos/imagenes.py::normalizar_imagenes
      "lista_para_ia": bool,  # producto y etiqueta legibles (la fachada puede faltar)
      "errores": [str]
    }

Garantías: una entrada por cada ``capture_id`` (aunque no tenga fotos), nunca se cae por una captura mala,
y las rutas se guardan relativas a la raíz del repo.
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from src.datos.cargador import cargar_capturas, cargar_catalogo
from src.datos.imagenes import (ESTADO_OK, TIPOS_IMAGEN, CacheFachadas, indexar_carpeta, normalizar_imagenes,
                                rutas_imagenes)

log = logging.getLogger(__name__)
RAIZ = Path(__file__).resolve().parents[2]


def _relativa(ruta: Path | None) -> str | None:
    if ruta is None:
        return None
    ruta = Path(ruta).resolve()
    try:
        return ruta.relative_to(RAIZ).as_posix()
    except ValueError:
        return ruta.as_posix()


def preparar_captura(captura: dict[str, Any], base_imagenes: Path, ruta_cache: Path,
                     catalogo: dict[int, dict[str, Any]] | None = None,
                     indice: dict[str, dict[str, Path]] | None = None,
                     cache_fachadas: CacheFachadas | None = None,
                     parametros: dict[str, Any] | None = None) -> dict[str, Any]:
    """Prepara una captura (para usarla dentro del pipeline, una por una). Nunca lanza excepción."""
    capture_id = captura.get("capture_id")
    try:
        imagenes = rutas_imagenes(captura, base_imagenes, indice)
        normal = normalizar_imagenes(captura, imagenes, ruta_cache, cache_fachadas, parametros)
        errores = list(normal["errores"])
    except Exception as error:  # cualquier sorpresa queda registrada y la captura sigue
        log.exception("%s: error inesperado en la ingesta", capture_id)
        imagenes = {tipo: None for tipo in TIPOS_IMAGEN}
        normal = {"estado_imagenes": {tipo: "corrupta" for tipo in TIPOS_IMAGEN},
                  "imagenes_normalizadas": {tipo: None for tipo in TIPOS_IMAGEN},
                  "senales": {}, "errores": []}
        errores = [f"ingesta: {error}"]
    producto = (catalogo or {}).get(captura.get("id_product"))
    if catalogo is not None and producto is None:
        errores.append("producto_fuera_de_catalogo")
    estado = normal["estado_imagenes"]
    return {
        "capture_id": capture_id,
        "captura": captura,
        "producto_catalogo": producto,
        "imagenes": {t: _relativa(r) for t, r in imagenes.items()},
        "imagenes_normalizadas": {t: _relativa(r) for t, r in normal["imagenes_normalizadas"].items()},
        "estado_imagenes": estado,
        "senales": normal["senales"],
        "lista_para_ia": estado.get("product") == ESTADO_OK and estado.get("shelf") == ESTADO_OK,
        "errores": errores,
    }


def ingerir(ruta_capturas: Path, base_imagenes: Path, ruta_cache: Path,
            ruta_catalogo: Path | None = None, parametros: dict[str, Any] | None = None,
            hilos: int = 4) -> list[dict[str, Any]]:
    """Ingiere todas las capturas. Regresa la lista en el orden de capturas.json."""
    capturas = cargar_capturas(ruta_capturas)
    catalogo = cargar_catalogo(ruta_catalogo) if ruta_catalogo and Path(ruta_catalogo).exists() else None
    indice = indexar_carpeta(Path(base_imagenes))
    cache_fachadas = CacheFachadas()

    def una(captura: dict[str, Any]) -> dict[str, Any]:
        return preparar_captura(captura, base_imagenes, ruta_cache, catalogo, indice, cache_fachadas, parametros)

    with ThreadPoolExecutor(max_workers=max(1, hilos)) as ejecutor:
        preparadas = list(ejecutor.map(una, capturas))
    log.info("Fachadas distintas normalizadas: %d", len(cache_fachadas))
    return preparadas


def resumen(preparadas: list[dict[str, Any]]) -> dict[str, Any]:
    """Conteos agregados para el reporte (sin datos de capturas individuales salvo sus IDs con problema)."""
    estados = Counter((tipo, p["estado_imagenes"].get(tipo)) for p in preparadas for tipo in TIPOS_IMAGEN)
    banderas = Counter(b for p in preparadas for b in p["captura"].get("banderas_datos", []))
    senales = [p["senales"] for p in preparadas if p["senales"]]
    return {
        "capturas": len(preparadas),
        "listas_para_ia": sum(p["lista_para_ia"] for p in preparadas),
        "con_errores": sorted(p["capture_id"] for p in preparadas if p["errores"]),
        "estado_imagenes": {f"{t}:{e}": n for (t, e), n in sorted(estados.items())},
        "banderas_datos": dict(banderas.most_common()),
        "codigo_empaque": dict(Counter(s.get("codigo_empaque") for s in senales)),
        "codigo_etiqueta": dict(Counter(s.get("codigo_etiqueta") for s in senales)),
        "fachadas_distintas": len({(s.get("facade") or {}).get("hash") for s in senales} - {None}),
        "tokens_imagen_aprox_total": sum(s.get("tokens_imagen_aprox", 0) for s in senales),
    }


def guardar_ingesta(preparadas: list[dict[str, Any]], ruta_salida: Path) -> None:
    ruta_salida = Path(ruta_salida)
    ruta_salida.parent.mkdir(parents=True, exist_ok=True)
    ruta_salida.write_text(json.dumps(preparadas, ensure_ascii=False, indent=1), encoding="utf-8")
