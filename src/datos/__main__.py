"""E1 + E2 en un comando: ``python -m src.datos`` (sin tokens).

Escribe en ``cache/`` (nombres en config.yaml → datos.salidas):
    indice_fotos.json          IndiceFotos                      fotos encontradas por nombre (respaldo)
    capturas_preparadas.json   list[CapturaPreparada]           E1
    features.json              {capture_id: FeaturesCaptura}    E2, una por captura aunque no tenga fotos
    reporte_datos.json         resumen agregado para revisar rápido

Validar contra el contrato:
    python contratos/validar.py features cache/features.json --capturas data/capturas.json
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from contratos import CapturaPreparada, FeaturesCaptura
from src.datos.cargador import cargar_capturas
from src.datos.imagenes import RAIZ
from src.datos.normalizar import normalizar
from src.datos.separar_fotos import separar_fotos

log = logging.getLogger("src.datos")


def _config() -> dict[str, Any]:
    ruta = RAIZ / "config.yaml"
    if not ruta.exists():
        return {}
    return yaml.safe_load(ruta.read_text(encoding="utf-8")) or {}


def _escribir(ruta: Path, datos: Any) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")


def resumen(capturas: list[CapturaPreparada], features: list[FeaturesCaptura]) -> dict[str, Any]:
    """Solo conteos agregados (sin contenido de capturas, salvo los IDs con problema)."""
    return {
        "capturas": len(capturas),
        "estado": dict(Counter(f.estado for f in features)),
        "con_errores": sorted(f.capture_id for f in features if f.errores),
        "banderas_datos": dict(Counter(b for c in capturas for b in c.banderas_datos)),
        "codigo_empaque": dict(Counter(f.codigo_empaque for f in features)),
        "codigo_etiqueta": dict(Counter(f.codigo_etiqueta for f in features)),
        "fachadas_distintas": len({f.facade.hash for f in features if f.facade}),
        "tokens_imagen_aprox_total": sum(p.tokens_aprox for f in features for p in (f.facade, f.product, f.shelf)
                                         if p and not getattr(p, "repetida", False)),
    }


def main() -> None:
    config = _config()
    rutas = config.get("rutas", {})
    datos = config.get("datos", {})
    salidas = datos.get("salidas", {})
    parser = argparse.ArgumentParser(description="Carga (E1) y visión local (E2) de las capturas, sin tokens.")
    parser.add_argument("--capturas", type=Path, default=RAIZ / rutas.get("capturas", "data/capturas.json"))
    parser.add_argument("--imagenes", type=Path, default=RAIZ / rutas.get("imagenes", "data/"),
                        help="carpeta base de las rutas imagenes/... de cada captura")
    parser.add_argument("--cache", type=Path, default=RAIZ / rutas.get("cache", "cache/"))
    parser.add_argument("--hilos", type=int, default=datos.get("hilos", 6))
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")

    def salida(clave: str, defecto: str) -> Path:
        return args.cache / salidas.get(clave, defecto)

    inicio = time.perf_counter()
    indice = separar_fotos(args.imagenes)
    capturas = cargar_capturas(args.capturas, args.imagenes, indice)
    features = normalizar(capturas, args.cache, datos.get("normalizacion"), args.hilos)

    _escribir(salida("indice_fotos", "indice_fotos.json"), indice.model_dump())
    _escribir(salida("capturas_preparadas", "capturas_preparadas.json"), [c.model_dump() for c in capturas])
    _escribir(salida("features", "features.json"), {f.capture_id: f.model_dump() for f in features})
    reporte = resumen(capturas, features)
    reporte["segundos"] = round(time.perf_counter() - inicio, 1)
    _escribir(salida("reporte", "reporte_datos.json"), reporte)
    log.info("Datos: %d capturas %s, %d con errores, %.1f s → %s", reporte["capturas"], reporte["estado"],
             len(reporte["con_errores"]), reporte["segundos"], args.cache)


if __name__ == "__main__":
    main()
