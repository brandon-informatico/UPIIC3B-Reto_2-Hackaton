"""Paso 2 · Analiza capturas reales de contratos/ejemplos/ y compara contra su E4_hallazgos_ia.

Uso (desde la raíz del repo):
    .venv/bin/python -m src.ia.prueba_captura                      # ejemplo 01, detalle completo
    .venv/bin/python -m src.ia.prueba_captura --ejemplo 03 --sin-cache
    .venv/bin/python -m src.ia.prueba_captura --todos --pensamiento desactivado
    .venv/bin/python -m src.ia.prueba_captura --todos --esfuerzo low

Ejemplos con fotos reales: 01, 02, 03, 04, 12. Los CAP-9xxxxx son sintéticos (no tienen fotos).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from contratos import CapturaPreparada
from src.ia.analizar import ESFUERZO, MODOS_PENSAMIENTO, PENSAMIENTO, analizar_captura, version_completa
from src.ia.cliente import RAIZ, ConfiguracionFaltante
from src.ia.imagenes import rutas_fotos

logging.basicConfig(level=logging.INFO, format="%(message)s")
for nombre_logger in ("httpx", "httpx2"):
    logging.getLogger(nombre_logger).setLevel(logging.WARNING)
log = logging.getLogger(__name__)

EJEMPLOS_REALES = ("01", "02", "03", "04", "12")


def _cargar_ejemplo(prefijo: str) -> tuple[Path, dict] | None:
    archivos = sorted((RAIZ / "contratos" / "ejemplos").glob(f"{prefijo}_*.json"))
    return (archivos[0], json.loads(archivos[0].read_text(encoding="utf-8"))) if archivos else None


def _comparar(esperado: dict, obtenido: dict) -> tuple[int, int, list[str]]:
    campos = [c for c in esperado if c != "duda_principal"]
    diferencias = [c for c in campos if obtenido.get(c) != esperado[c]]
    return len(campos) - len(diferencias), len(campos), diferencias


def probar(prefijo: str, args: argparse.Namespace, detalle: bool) -> dict | None:
    cargado = _cargar_ejemplo(prefijo)
    if cargado is None:
        log.error("✗ No existe contratos/ejemplos/%s_*.json", prefijo)
        return None
    ruta_ejemplo, ejemplo = cargado
    captura = CapturaPreparada(**ejemplo["E1_captura_preparada"])
    if all(ruta is None for ruta in rutas_fotos(captura).values()):
        log.error("✗ %s no tiene fotos en data/ (¿ejemplo sintético o faltó descargar datos?)", captura.capture_id)
        return None

    hallazgos, uso_ia = analizar_captura(
        captura, usar_cache=not args.sin_cache, pensamiento=args.pensamiento, esfuerzo=args.esfuerzo
    )
    fila = {"ejemplo": ruta_ejemplo.stem, "ok": hallazgos is not None, "uso": uso_ia}
    if hallazgos is None:
        log.error("✗ %s · la IA no devolvió hallazgos válidos (uso: %s)", ruta_ejemplo.stem, uso_ia)
        return fila

    if detalle:
        log.info("▶ %s · %s · %s", ruta_ejemplo.stem, captura.capture_id, captura.product_name)
        log.info("\nHallazgos:\n%s", json.dumps(hallazgos.model_dump(), ensure_ascii=False, indent=2))
    if ejemplo.get("E4_hallazgos_ia"):
        aciertos, total, diferencias = _comparar(ejemplo["E4_hallazgos_ia"], hallazgos.model_dump())
        fila.update(aciertos=aciertos, total=total, diferencias=diferencias)
        if detalle:
            log.info("\nCoincide con el ejemplo en %s/%s campos (sin contar duda_principal).", aciertos, total)
            for campo in diferencias:
                log.info("  ≠ %s: esperado=%r obtenido=%r", campo, ejemplo["E4_hallazgos_ia"][campo], getattr(hallazgos, campo))
    return fila


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ejemplo", default="01", help="prefijo del archivo en contratos/ejemplos (01..17)")
    parser.add_argument("--todos", action="store_true", help=f"corre los ejemplos reales {', '.join(EJEMPLOS_REALES)}")
    parser.add_argument("--sin-cache", action="store_true", help="vuelve a consultar al modelo")
    parser.add_argument("--pensamiento", choices=list(MODOS_PENSAMIENTO), default=PENSAMIENTO)
    parser.add_argument("--esfuerzo", choices=["low", "medium", "high"], default=ESFUERZO)
    args = parser.parse_args()

    try:
        filas = [probar(p, args, detalle=not args.todos) for p in (EJEMPLOS_REALES if args.todos else [args.ejemplo])]
    except ConfiguracionFaltante as error:
        log.error("✗ %s", error)
        return 1
    filas = [f for f in filas if f]

    log.info("\nModo: %s", version_completa(args.pensamiento, args.esfuerzo))
    log.info("%-38s %8s %8s %8s %8s %4s", "ejemplo", "aciertos", "entrada", "salida", "ms", "int")
    for f in filas:
        uso = f["uso"]
        aciertos = f"{f['aciertos']}/{f['total']}" if "aciertos" in f else ("falló" if not f["ok"] else "-")
        log.info(
            "%-38s %8s %8s %8s %8s %4s", f["ejemplo"], aciertos,
            uso.input_tokens if uso else "-", uso.output_tokens if uso else "-",
            uso.latencia_ms if uso else "-", uso.intentos if uso else "-",
        )
        if args.todos and f.get("diferencias"):
            log.info("%-38s ≠ %s", "", ", ".join(f["diferencias"]))
    usos = [f["uso"] for f in filas if f["uso"]]
    if usos:
        total_aciertos = sum(f.get("aciertos", 0) for f in filas)
        total_campos = sum(f.get("total", 0) for f in filas)
        log.info(
            "TOTAL aciertos=%s/%s · tokens/captura=%s · fallas=%s",
            total_aciertos, total_campos,
            round(sum(u.input_tokens + u.output_tokens for u in usos) / len(usos)),
            sum(1 for f in filas if not f["ok"]),
        )
    return 0 if all(f["ok"] for f in filas) else 1


if __name__ == "__main__":
    sys.exit(main())
