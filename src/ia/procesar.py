"""E4 en lote · cache/ingesta.json (Copka) → IA → cache/hallazgos.json (para el motor de Pat).

Uso (desde la raíz del repo):
    .venv/bin/python -m src.ia.procesar                    # todas las capturas listas para IA
    .venv/bin/python -m src.ia.procesar --limite 5 --hilos 1

Salida: lista JSON, un objeto por capture_id (en el orden de la ingesta, aunque la IA falle):
    {"capture_id": "...", "ia_ok": true,  <campos de HallazgosIA>, "uso_ia": {...}, "error": null}
    {"capture_id": "...", "ia_ok": false, "uso_ia": {...} | null, "error": "ia_error" | "no_lista_para_ia"}
Si ia_ok es false el motor debe mandar la captura a revision_manual (motivo ia_error / imagen_faltante).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from contratos import CapturaPreparada
from src.ia.analizar import ESFUERZO, PENSAMIENTO, analizar_captura, version_completa
from src.ia.cliente import RAIZ, ConfiguracionFaltante, leer_config

log = logging.getLogger("src.ia.procesar")
CAMPOS_CAPTURA = [campo for campo in CapturaPreparada.model_fields if campo not in ("rutas", "banderas_datos")]


def a_captura_preparada(entrada: dict[str, Any]) -> CapturaPreparada:
    """Entrada de la ingesta de Copka → CapturaPreparada, con las fotos normalizadas como rutas."""
    datos = entrada["captura"]
    normalizadas = entrada.get("imagenes_normalizadas") or {}
    originales = entrada.get("imagenes") or {}
    rutas = {tipo: normalizadas.get(tipo) or originales.get(tipo) for tipo in ("facade", "product", "shelf")}
    return CapturaPreparada(
        **{campo: datos.get(campo) for campo in CAMPOS_CAPTURA},
        rutas=rutas,
        banderas_datos=datos.get("banderas_datos") or [],
    )


def procesar_entrada(entrada: dict[str, Any], usar_cache: bool) -> dict[str, Any]:
    """Nunca lanza excepción: una captura mala se reporta y la corrida sigue."""
    capture_id = entrada.get("capture_id")
    if not entrada.get("lista_para_ia"):
        return {"capture_id": capture_id, "ia_ok": False, "uso_ia": None, "error": "no_lista_para_ia"}
    try:
        hallazgos, uso_ia = analizar_captura(a_captura_preparada(entrada), usar_cache=usar_cache)
    except Exception as error:  # noqa: BLE001
        log.exception("%s · error inesperado", capture_id)
        return {"capture_id": capture_id, "ia_ok": False, "uso_ia": None, "error": f"ia_error: {type(error).__name__}"}
    if hallazgos is None:
        return {"capture_id": capture_id, "ia_ok": False,
                "uso_ia": uso_ia.model_dump() if uso_ia else None, "error": "ia_error"}
    return {"capture_id": capture_id, "ia_ok": True, **hallazgos.model_dump(), "uso_ia": uso_ia.model_dump(), "error": None}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ingesta", type=Path, default=RAIZ / "cache" / "ingesta.json")
    parser.add_argument("--salida", type=Path, default=RAIZ / "cache" / "hallazgos.json")
    parser.add_argument("--hilos", type=int, default=2, help="llamadas en paralelo (cuida el límite por minuto)")
    parser.add_argument("--limite", type=int, default=None, help="procesa solo las primeras N capturas")
    parser.add_argument("--sin-cache", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for nombre_logger in ("httpx", "httpx2"):
        logging.getLogger(nombre_logger).setLevel(logging.WARNING)

    try:
        leer_config()
    except ConfiguracionFaltante as error:
        log.error("✗ %s", error)
        return 1
    if not args.ingesta.exists():
        log.error("✗ No existe %s: corre primero la ingesta de Copka (python -m src.datos)", args.ingesta)
        return 1
    entradas = json.loads(args.ingesta.read_text(encoding="utf-8"))[: args.limite]

    inicio = time.perf_counter()
    with ThreadPoolExecutor(max_workers=max(1, args.hilos)) as ejecutor:
        registros = list(ejecutor.map(lambda e: procesar_entrada(e, not args.sin_cache), entradas))
    segundos = round(time.perf_counter() - inicio, 1)

    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_text(json.dumps(registros, ensure_ascii=False, indent=1), encoding="utf-8")

    usos = [r["uso_ia"] for r in registros if r["uso_ia"]]
    tokens = [u["input_tokens"] + u["output_tokens"] for u in usos]
    reporte = {
        "modo": version_completa(PENSAMIENTO, ESFUERZO),
        "capturas": len(registros),
        "ia_ok": sum(r["ia_ok"] for r in registros),
        "fallas": {r["capture_id"]: r["error"] for r in registros if not r["ia_ok"]},
        "tokens_total": sum(tokens),
        "tokens_por_captura": round(sum(tokens) / len(tokens)) if tokens else 0,
        "entrada_por_captura": round(sum(u["input_tokens"] for u in usos) / len(usos)) if usos else 0,
        "salida_por_captura": round(sum(u["output_tokens"] for u in usos) / len(usos)) if usos else 0,
        "reintentos": sum(u["intentos"] - 1 for u in usos),
        "segundos": segundos,
    }
    args.salida.with_name("reporte_ia.json").write_text(json.dumps(reporte, ensure_ascii=False, indent=1), encoding="utf-8")
    log.info("IA: %s/%s capturas ok · %s tokens/captura · %s s → %s",
             reporte["ia_ok"], reporte["capturas"], reporte["tokens_por_captura"], segundos, args.salida)
    return 0 if reporte["ia_ok"] == reporte["capturas"] else 1


if __name__ == "__main__":
    sys.exit(main())
