"""Adaptadores del pipeline hacia los contratos (responsable: Pat).

Traducen lo que hoy entregan los modulos de Copka (src/datos) y Brandon (src/ia) a los modelos de
contratos/contratos.py, sin modificar su codigo:

- normalizar_con_ingesta(capturas) -> list[FeaturesCaptura]: usa la ingesta local de Copka
  (src.datos.ingesta.preparar_captura). El pipeline la usa solo si no existe src.datos.normalizar.normalizar.
- como_captura_preparada(captura) -> CapturaPreparada: lo que espera src.ia.analizar.analizar_captura;
  src.datos.cargador entrega diccionarios.

Los imports de src.datos son perezosos: el motor y sus pruebas funcionan aunque esa rama no este integrada.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import yaml

from contratos.contratos import CapturaPreparada, FeaturesCaptura

LOG = logging.getLogger(__name__)
RAIZ = Path(__file__).resolve().parents[2]
TIPOS_FOTO = ("facade", "product", "shelf")
CAMPOS_FOTO = {"original_wh", "final_wh", "ruta_normalizada", "tokens_aprox", "brillo", "nitidez",
               "nitidez_norm", "nitidez_zona_max", "codigos_leidos"}
CAMPOS_FACHADA = CAMPOS_FOTO | {"hash", "repetida"}
CAMPOS_CAPTURA = [c for c in CapturaPreparada.model_fields if c not in ("rutas", "banderas_datos")]


def como_captura_preparada(captura: Any) -> CapturaPreparada:
    """dict limpio de src.datos.cargador (o el propio modelo) -> CapturaPreparada."""
    if isinstance(captura, CapturaPreparada):
        return captura
    rutas = captura.get("rutas") or {t: captura.get(f"{t}_file") for t in TIPOS_FOTO}
    return CapturaPreparada(**{c: captura.get(c) for c in CAMPOS_CAPTURA}, rutas=rutas,
                            banderas_datos=captura.get("banderas_datos") or [])


def features_desde_ingesta(entrada: dict[str, Any]) -> FeaturesCaptura:
    """Una entrada de la ingesta de Copka -> FeaturesCaptura (solo los campos del contrato)."""
    senales = entrada.get("senales") or {}
    estados = entrada.get("estado_imagenes") or {}
    fotos: dict[str, dict[str, Any] | None] = {}
    for tipo in TIPOS_FOTO:
        senal = senales.get(tipo)
        permitidos = CAMPOS_FACHADA if tipo == "facade" else CAMPOS_FOTO
        fotos[tipo] = ({k: v for k, v in senal.items() if k in permitidos}
                       if senal and estados.get(tipo) == "ok" else None)
    presentes = sum(foto is not None for foto in fotos.values())
    estado = "completa" if presentes == 3 else "sin_fotos" if presentes == 0 else "incompleta"
    errores = list(entrada.get("errores") or [])
    if estado != "completa" and not errores:
        errores = [f"{tipo}: {estados.get(tipo, 'faltante')}" for tipo in TIPOS_FOTO if fotos[tipo] is None]
    parecido = senales.get("parecido_producto_etiqueta")
    return FeaturesCaptura(
        capture_id=entrada["capture_id"],
        estado=estado,
        **fotos,
        parecido_producto_etiqueta=max(-1.0, min(1.0, parecido)) if parecido is not None else None,
        codigo_empaque=senales.get("codigo_empaque") or "no_leido",
        codigo_etiqueta=senales.get("codigo_etiqueta") or "no_leido",
        errores=errores,
    )


def normalizar_con_ingesta(capturas: list[dict[str, Any]], hilos: int = 4) -> list[FeaturesCaptura]:
    """E2 con la ingesta de Copka, en el mismo orden que `capturas`."""
    from src.datos.cargador import cargar_catalogo
    from src.datos.imagenes import CacheFachadas, indexar_carpeta
    from src.datos.ingesta import preparar_captura

    ruta_config = RAIZ / "config.yaml"
    config = (yaml.safe_load(ruta_config.read_text(encoding="utf-8")) or {}) if ruta_config.exists() else {}
    rutas, datos = config.get("rutas", {}), config.get("datos", {})
    base_imagenes = RAIZ / rutas.get("imagenes", "data/")
    ruta_cache = RAIZ / rutas.get("cache", "cache/")
    ruta_catalogo = RAIZ / rutas.get("catalogo", "data/catalogo_productos.csv")
    catalogo = cargar_catalogo(ruta_catalogo) if ruta_catalogo.exists() else None
    indice = indexar_carpeta(base_imagenes)
    cache_fachadas = CacheFachadas()

    def una(captura: dict[str, Any]) -> FeaturesCaptura:
        entrada = preparar_captura(captura, base_imagenes, ruta_cache, catalogo, indice, cache_fachadas,
                                   datos.get("normalizacion"))
        return features_desde_ingesta(entrada)

    with ThreadPoolExecutor(max_workers=max(1, hilos)) as ejecutor:
        features = list(ejecutor.map(una, capturas))
    LOG.info("E2 (ingesta de Copka): %d capturas, %d fachadas distintas", len(features), len(cache_fachadas))
    return features
