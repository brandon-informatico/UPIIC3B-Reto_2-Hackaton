"""CLI de la ingesta local: ``python -m src.datos`` (ver src/datos/ingesta.py)."""
from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

import yaml

from src.datos.ingesta import RAIZ, guardar_ingesta, ingerir, resumen

log = logging.getLogger("src.datos")


def _config() -> dict:
    ruta = RAIZ / "config.yaml"
    if not ruta.exists():
        return {}
    return yaml.safe_load(ruta.read_text(encoding="utf-8")) or {}


def main() -> None:
    config = _config()
    rutas = config.get("rutas", {})
    datos = config.get("datos", {})
    parser = argparse.ArgumentParser(description="Ingesta local de capturas y fotos (sin tokens).")
    parser.add_argument("--capturas", type=Path, default=RAIZ / rutas.get("capturas", "data/capturas.json"))
    parser.add_argument("--catalogo", type=Path, default=RAIZ / rutas.get("catalogo", "data/catalogo_productos.csv"))
    parser.add_argument("--imagenes", type=Path, default=RAIZ / rutas.get("imagenes", "data/"),
                        help="carpeta base de las rutas imagenes/... de cada captura")
    parser.add_argument("--cache", type=Path, default=RAIZ / rutas.get("cache", "cache/"))
    parser.add_argument("--salida", type=Path, default=RAIZ / datos.get("salida_ingesta", "cache/ingesta.json"))
    parser.add_argument("--hilos", type=int, default=datos.get("hilos", 4))
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")

    inicio = time.perf_counter()
    preparadas = ingerir(args.capturas, args.imagenes, args.cache, args.catalogo,
                         parametros=datos.get("normalizacion"), hilos=args.hilos)
    guardar_ingesta(preparadas, args.salida)
    reporte = resumen(preparadas)
    reporte["segundos"] = round(time.perf_counter() - inicio, 1)
    ruta_reporte = args.salida.with_name("reporte_ingesta.json")
    ruta_reporte.write_text(json.dumps(reporte, ensure_ascii=False, indent=1), encoding="utf-8")
    log.info("Ingesta: %d capturas, %d listas para IA, %d con errores, %.1f s → %s",
             reporte["capturas"], reporte["listas_para_ia"], len(reporte["con_errores"]),
             reporte["segundos"], args.salida)


if __name__ == "__main__":
    main()
