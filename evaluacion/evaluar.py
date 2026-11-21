"""E8 · Evaluación del motor.

Compara resultados/resultados.json contra las etiquetas y escribe resultados/metricas.json.

Uso (desde la raíz del repo, después de python -m src.pipeline):
    python -m evaluacion.evaluar
    python -m evaluacion.evaluar --resultados resultados/resultados_ciego.json --capturas <ciego>/capturas.json

Lee lo que ya producen los demás módulos (no recalcula nada de ellos):
    resultados/resultados.json   Pat (E6): una respuesta oficial por captura
    data/capturas.json           datos del reto: decision_esperada y motivo_rechazo (si el conjunto tiene etiquetas)
    logs/corrida_*.jsonl         Pat: si llamó a la IA y cuántos tokens usó por captura (la corrida más reciente)
    cache/ia/<id>.json           Brandon: uso de tokens por captura (respaldo si no hay log)
    cache/reporte_ia.json        Brandon: tiempo de la corrida de IA
    cache/ingesta.json           Copka: fachadas repetidas (imágenes que podrían evitarse)

Escribe resultados/metricas.json con el formato que lee el dashboard de Armando, más `acierto` (la métrica
confirmada por los jueces). Sin etiquetas (set ciego) solo reporta formato, decisiones y tokens.
"""
from __future__ import annotations

import argparse
import json
import logging
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from contratos.contratos import RegistroSalida
from evaluacion import costo
from evaluacion.reporte import imprimir
from src.archivos import nombre_archivo

LOG = logging.getLogger("evaluacion")
RAIZ = Path(__file__).resolve().parents[1]
MOTIVO_A_REASON = {  # PENDIENTE: lista oficial de reason_code
    "Capturas borrosas": "IMAGEN_BORROSA",
    "Capturas lejanas": "CAPTURA_LEJANA",
    "Descripción de producto incompleta": "DESCRIPCION_INCOMPLETA",
}


def _leer_json(ruta: Path | None, defecto: Any = None) -> Any:
    try:
        return json.loads(ruta.read_text(encoding="utf-8")) if ruta and ruta.exists() else defecto
    except ValueError:
        LOG.warning("No se pudo leer %s", ruta)
        return defecto


def _log_mas_reciente() -> Path | None:
    corridas = sorted((RAIZ / "logs").glob("corrida_*.jsonl"))
    return corridas[-1] if corridas else None


def _leer_log(ruta: Path | None) -> dict[str, dict]:
    if not ruta or not ruta.exists():
        return {}
    filas = {}
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        try:
            fila = json.loads(linea)
            filas[fila["capture_id"]] = fila
        except (ValueError, KeyError):
            continue
    return filas


def _formato(resultados: list[dict], ids_esperados: list[str]) -> dict[str, Any]:
    """JSON válido con el formato oficial (RegistroSalida), duplicados y faltantes."""
    validos, invalidos = 0, []
    for registro in resultados:
        try:
            RegistroSalida.model_validate(registro)
            validos += 1
        except ValidationError as error:
            invalidos.append({"capture_id": registro.get("capture_id"), "error": str(error.errors()[0]["msg"])})
    ids = [r.get("capture_id") for r in resultados]
    repetidos = sorted(i for i, n in Counter(ids).items() if n > 1)
    faltantes = sorted(set(ids_esperados) - set(ids))
    total = len(ids_esperados) or len(resultados)
    return {"validos": validos, "total": total, "pct": round(validos / total, 4) if total else None,
            "invalidos": invalidos, "duplicados": repetidos, "faltantes": faltantes}


def _tokens(resultados: list[dict], log: dict[str, dict]) -> tuple[dict, dict]:
    entrada = salida = llamadas = 0
    for registro in resultados:
        cid = registro.get("capture_id")
        fila = log.get(cid, {})
        uso = fila.get("uso_ia") or (_leer_json(RAIZ / "cache" / "ia" / f"{nombre_archivo(cid)}.json", {}) or {}).get("uso_ia") or {}
        llamo = fila.get("llamo_ia", bool(uso)) if fila else bool(uso)
        if llamo:
            llamadas += 1
            entrada += int(uso.get("input_tokens") or fila.get("tokens_entrada") or 0)
            salida += int(uso.get("output_tokens") or fila.get("tokens_salida") or 0)
    tokens = {"entrada": entrada, "salida": salida, "total": entrada + salida,
              "por_captura": round((entrada + salida) / llamadas) if llamadas else 0}
    ingesta = _leer_json(RAIZ / "cache" / "ingesta.json", []) or []
    repetidas = sum(1 for e in ingesta if ((e.get("senales") or {}).get("facade") or {}).get("repetida"))
    nota = (f"{repetidas} fachadas repetidas (podrían analizarse una sola vez); hoy se envían 3 fotos por llamada"
            if ingesta else "sin cache/ingesta.json")
    llamadas_info = {"ia": llamadas, "evitadas": len(resultados) - llamadas, "imagenes_enviadas": llamadas * 3,
                     "imagenes_evitadas": (len(resultados) - llamadas) * 3, "nota": nota}
    return tokens, llamadas_info


def evaluar(ruta_resultados: Path, ruta_capturas: Path, ruta_log: Path | None, conjunto: str) -> dict[str, Any]:
    resultados = _leer_json(ruta_resultados, [])
    capturas = _leer_json(ruta_capturas, []) or []
    log = _leer_log(ruta_log)
    etiquetas = {c["capture_id"]: c for c in capturas if c.get("decision_esperada")}
    formato = _formato(resultados, [c["capture_id"] for c in capturas])
    tokens, llamadas = _tokens(resultados, log)
    reporte_ia = _leer_json(RAIZ / "cache" / "reporte_ia.json", {}) or {}
    metricas: dict[str, Any] = {
        "ficticio": False,
        "generado": datetime.now().isoformat(timespec="seconds"),
        "conjunto": conjunto,
        "total": len(resultados),
        "umbrales": {"precision_aprobaciones_min": 0.97, "json_valido_min": 0.99},
        "json_validos_pct": formato["pct"],
        "formato": {k: formato[k] for k in ("validos", "total", "duplicados", "faltantes", "invalidos")},
        "decisiones": dict(Counter(r.get("decision") for r in resultados)),
        "tokens": tokens,
        "llamadas": llamadas,
        "tiempo_total_s": reporte_ia.get("segundos"),
        "con_etiquetas": bool(etiquetas),
    }
    if not etiquetas:  # set ciego: sin decision_esperada no hay acierto ni costo
        metricas.update(acierto=None, precision_aprobaciones=None, costo_total=None, costo_por_captura=None,
                        costo_desglose=None, matriz_confusion=None, calidad_dato=None, por_tanda=[], errores=[])
        return metricas

    pares = [(etiquetas[r["capture_id"]]["decision_esperada"], r.get("decision"))
             for r in resultados if r.get("capture_id") in etiquetas]
    matriz = costo.matriz_confusion(pares)
    desglose = costo.desglose(pares)
    total_costo = costo.costo_total(desglose)

    def oficial(r: dict) -> str | None:
        return etiquetas.get(r.get("capture_id"), {}).get("decision_esperada")

    rechazadas = [r for r in resultados if oficial(r) == "rechazada"]
    motivo_ok = sum(r.get("decision") == "rechazada" and r.get("reason_code") ==
                    MOTIVO_A_REASON.get(etiquetas[r["capture_id"]].get("motivo_rechazo")) for r in rechazadas)
    aprobadas = [r for r in resultados if oficial(r) == "aprobada"]
    precio_ok = sum(r.get("precio_detectado") is not None and abs(r["precio_detectado"] -
                    float(etiquetas[r["capture_id"]].get("capture_price") or -1)) < 0.01 for r in aprobadas)

    def grupo(cid: str) -> str:
        etiqueta = etiquetas[cid]
        motivo = etiqueta.get("motivo_rechazo")
        return f"rechazada · {motivo}" if motivo else etiqueta["decision_esperada"]

    por_grupo = []
    for nombre in sorted({grupo(c) for c in etiquetas}):
        sub = [(etiquetas[r["capture_id"]]["decision_esperada"], r.get("decision")) for r in resultados
               if r.get("capture_id") in etiquetas and grupo(r["capture_id"]) == nombre]
        m = costo.matriz_confusion(sub)
        por_grupo.append({"tanda": nombre, "total": len(sub), "costo": costo.costo_total(costo.desglose(sub)),
                          "acierto": costo.acierto(m), "precision_aprobaciones": costo.precision_aprobaciones(m)})

    metricas.update(
        acierto=costo.acierto(matriz),
        precision_aprobaciones=costo.precision_aprobaciones(matriz),
        costo_total=total_costo,
        costo_por_captura=round(total_costo / len(pares), 3) if pares else None,
        costo_desglose=desglose,
        supuesto_costo=f"rechazar una captura con etiqueta revision_manual cuenta como "
                       f"{costo.RECHAZAR_REVISION_CUENTA_COMO} (pendiente del script oficial)",
        matriz_confusion=matriz,
        calidad_dato={
            "reason_code_acierto": round(motivo_ok / len(rechazadas), 4) if rechazadas else None,
            "precio_acierto": round(precio_ok / len(aprobadas), 4) if aprobadas else None,
            "tipo_precio_acierto": None,  # PENDIENTE: el conjunto de desarrollo no trae el tipo de precio real
        },
        por_tanda=por_grupo,
        errores=[{"capture_id": r["capture_id"], "oficial": etiquetas[r["capture_id"]]["decision_esperada"],
                  "motor": r.get("decision"), "reason_code": r.get("reason_code")}
                 for r in resultados if r.get("capture_id") in etiquetas
                 and r.get("decision") != etiquetas[r["capture_id"]]["decision_esperada"]],
    )
    return metricas


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--resultados", type=Path, default=RAIZ / "resultados" / "resultados.json")
    parser.add_argument("--capturas", type=Path, default=RAIZ / "data" / "capturas.json")
    parser.add_argument("--log", type=Path, default=None, help="logs/corrida_*.jsonl (por defecto, el más reciente)")
    parser.add_argument("--salida", type=Path, default=RAIZ / "resultados" / "metricas.json")
    parser.add_argument("--conjunto", default="desarrollo")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if not args.resultados.exists():
        LOG.error("✗ No existe %s: corre primero python -m src.pipeline", args.resultados)
        return 1
    metricas = evaluar(args.resultados, args.capturas, args.log or _log_mas_reciente(), args.conjunto)
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_text(json.dumps(metricas, ensure_ascii=False, indent=1), encoding="utf-8")
    imprimir(metricas)
    LOG.info("\nMétricas guardadas en %s (las lee el dashboard)", args.salida)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
