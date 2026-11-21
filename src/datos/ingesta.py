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
      "ocr": {"disponible": bool, "etiqueta": {...} | null},                  # ver src/datos/ocr.py
      "imagenes_para_ia": {"facade": ruta|null, "product": ruta|null, "shelf": ruta|null},  # ← mandar ESTAS
      "fuente_etiqueta_ia": "completa" | "recorte" | "no_disponible",
      "tokens_imagen_ia_aprox": int,          # tokens de imagen estimados de lo que se mandará
      "recorte_etiqueta": ruta | null, "recorte_confiable": bool, "tokens_recorte_aprox": int | null,  # solo si
                                              # datos.recorte_para_ia = true (apagado por defecto)
      "lista_para_ia": bool,  # producto y etiqueta legibles (la fachada puede faltar)
      "errores": [str]
    }

Cómo leer las pistas del OCR (medido en las 100 capturas de desarrollo):
- ``precio_coincide_captura = True`` confirma el precio (72/100). ``False`` NO es evidencia de falla: en los 24 casos
  el precio capturado ni siquiera aparece entre lo leído (errores de lectura o precio realmente distinto).
- ``descripcion_similitud``: mediana 0.80 en aprobadas vs 0.33 en el resto; buena pista de identidad/legibilidad.
- ``precio_unitario_visible`` solo es ``True`` o ``None``: el OCR casi nunca lee la letra pequeña del precio unitario.
- Etiqueta para la IA: foto completa a 768 px (~590 tokens). Se probó el recorte del precio verificado con OCR:
  se usaba en 42/100, ahorraba solo ~13 % de tokens totales, duplicaba el tiempo y quitaba el producto que acompaña a
  la etiqueta (evidencia de "la etiqueta corresponde al producto"). Bajar la foto completa de 960 a 768 px ahorra
  ~36 % de esos tokens sin perder lectura (precio 96/100 en ambos). El recorte queda apagado
  (``datos.recorte_para_ia``) para compararlo con la IA si se quiere.
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from src.contratos import TIPOS_IMAGEN
from src.datos.cargador import cargar_capturas, cargar_catalogo
from src.datos.imagenes import (ESTADO_OK, CacheFachadas, indexar_carpeta, normalizar_imagenes,
                                rutas_imagenes)
from src.datos.ocr import analizar_ocr

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
                     parametros: dict[str, Any] | None = None, usar_ocr: bool = True,
                     usar_recorte: bool = True) -> dict[str, Any]:
    """Prepara una captura (para usarla dentro del pipeline, una por una). Nunca lanza excepción."""
    capture_id = captura.get("capture_id")
    texto: dict[str, Any] = {"disponible": False, "etiqueta": None, "recorte_etiqueta": None,
                             "recorte_confiable": False, "tokens_recorte_aprox": None}
    try:
        imagenes = rutas_imagenes(captura, base_imagenes, indice)
        normal = normalizar_imagenes(captura, imagenes, ruta_cache, cache_fachadas, parametros)
        errores = list(normal["errores"])
        if usar_ocr:
            texto = analizar_ocr(captura, normal["imagenes_normalizadas"], ruta_cache, originales=imagenes,
                                 hacer_recorte=usar_recorte)
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
    # Qué mandar a la IA: el recorte solo si se verificó que conserva precio y descripción; si no, la foto completa.
    para_ia = dict(normal["imagenes_normalizadas"])
    fuente_etiqueta = "completa" if para_ia.get("shelf") else "no_disponible"
    if usar_recorte and texto["recorte_confiable"] and texto["recorte_etiqueta"]:
        para_ia["shelf"], fuente_etiqueta = texto["recorte_etiqueta"], "recorte"
    tokens_ia = sum((normal["senales"].get(t) or {}).get("tokens_aprox", 0) for t in ("facade", "product")
                    if not (t == "facade" and (normal["senales"].get(t) or {}).get("repetida")))
    tokens_ia += (texto["tokens_recorte_aprox"] if fuente_etiqueta == "recorte"
                  else (normal["senales"].get("shelf") or {}).get("tokens_aprox", 0))
    return {
        "capture_id": capture_id,
        "captura": captura,
        "producto_catalogo": producto,
        "imagenes": {t: _relativa(r) for t, r in imagenes.items()},
        "imagenes_normalizadas": {t: _relativa(r) for t, r in normal["imagenes_normalizadas"].items()},
        "estado_imagenes": estado,
        "senales": normal["senales"],
        "ocr": {"disponible": texto["disponible"], "etiqueta": texto["etiqueta"]},
        "recorte_etiqueta": _relativa(texto["recorte_etiqueta"]),
        "recorte_confiable": texto["recorte_confiable"],
        "tokens_recorte_aprox": texto["tokens_recorte_aprox"],
        "imagenes_para_ia": {t: _relativa(r) for t, r in para_ia.items()},
        "fuente_etiqueta_ia": fuente_etiqueta,
        "tokens_imagen_ia_aprox": tokens_ia,
        "lista_para_ia": estado.get("product") == ESTADO_OK and estado.get("shelf") == ESTADO_OK,
        "errores": errores,
    }


def ingerir(ruta_capturas: Path, base_imagenes: Path, ruta_cache: Path,
            ruta_catalogo: Path | None = None, parametros: dict[str, Any] | None = None,
            hilos: int = 4, usar_ocr: bool = True, usar_recorte: bool = True) -> list[dict[str, Any]]:
    """Ingiere todas las capturas. Regresa la lista en el orden de capturas.json."""
    capturas = cargar_capturas(ruta_capturas)
    catalogo = cargar_catalogo(ruta_catalogo) if ruta_catalogo and Path(ruta_catalogo).exists() else None
    indice = indexar_carpeta(Path(base_imagenes))
    cache_fachadas = CacheFachadas()

    def una(captura: dict[str, Any]) -> dict[str, Any]:
        return preparar_captura(captura, base_imagenes, ruta_cache, catalogo, indice, cache_fachadas, parametros,
                                usar_ocr, usar_recorte)

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
        "fuente_etiqueta_ia": dict(Counter(p.get("fuente_etiqueta_ia") for p in preparadas)),
        "tokens_imagen_ia_aprox_total": sum(p.get("tokens_imagen_ia_aprox") or 0 for p in preparadas),
        "ocr": _resumen_ocr(preparadas),
    }


def _resumen_ocr(preparadas: list[dict[str, Any]]) -> dict[str, Any]:
    etiquetas = [p["ocr"]["etiqueta"] for p in preparadas if (p.get("ocr") or {}).get("etiqueta")]
    if not etiquetas:
        return {"disponible": any((p.get("ocr") or {}).get("disponible") for p in preparadas), "etiquetas_leidas": 0}
    return {
        "disponible": True,
        "etiquetas_leidas": len(etiquetas),
        "con_precio": sum(e["precio_etiqueta"] is not None for e in etiquetas),
        "precio_coincide_captura": sum(bool(e["precio_coincide_captura"]) for e in etiquetas),
        "tipo_precio": dict(Counter(e["tipo_precio"] for e in etiquetas)),
        "precio_unitario_visible": dict(Counter(e["precio_unitario_visible"] for e in etiquetas)),
        "contenido_coincide": dict(Counter(e["contenido_coincide"] for e in etiquetas)),
        "con_recorte": sum(p.get("recorte_etiqueta") is not None for p in preparadas),
        "recorte_confiable": sum(bool(p.get("recorte_confiable")) for p in preparadas),
        "tokens_recorte_aprox_total": sum(p.get("tokens_recorte_aprox") or 0 for p in preparadas),
    }


def guardar_ingesta(preparadas: list[dict[str, Any]], ruta_salida: Path) -> None:
    ruta_salida = Path(ruta_salida)
    ruta_salida.parent.mkdir(parents=True, exist_ok=True)
    ruta_salida.write_text(json.dumps(preparadas, ensure_ascii=False, indent=1), encoding="utf-8")
