"""Reporte de evaluación en la terminal (lo mismo que guarda resultados/metricas.json). Responsable: Ale (E8)."""
from __future__ import annotations

import logging
from typing import Any

from evaluacion.costo import DECISIONES

LOG = logging.getLogger("evaluacion")
CORTO = {"aprobada": "aprobada", "revision_manual": "revisión", "rechazada": "rechazada"}


def _pct(valor: float | None) -> str:
    return "—" if valor is None else f"{valor:.1%}"


def imprimir(m: dict[str, Any]) -> None:
    formato = m["formato"]
    LOG.info("Evaluación · conjunto: %s · %d capturas", m["conjunto"], m["total"])
    LOG.info("JSON válido: %s (%d/%d) · duplicados: %d · faltantes: %d", _pct(m["json_validos_pct"]),
             formato["validos"], formato["total"], len(formato["duplicados"]), len(formato["faltantes"]))
    LOG.info("Decisiones del motor: %s", m["decisiones"])
    LOG.info("Tokens: %s total · %s por captura · %s llamadas a la IA", m["tokens"]["total"],
             m["tokens"]["por_captura"], m["llamadas"]["ia"])
    if not m["con_etiquetas"]:
        LOG.info("Sin etiquetas (set ciego): no se calcula acierto ni costo.")
        return
    LOG.info("\nACIERTO en las 3 categorías: %s  (métrica confirmada por los jueces)", _pct(m["acierto"]))
    LOG.info("Precisión de aprobaciones: %s · costo operativo: %s (%s por captura)",
             _pct(m["precision_aprobaciones"]), m["costo_total"], m["costo_por_captura"])
    LOG.info("Supuesto de costo: %s", m["supuesto_costo"])
    LOG.info("\n  oficial \\ motor   %s", "".join(f"{CORTO[d]:>11}" for d in DECISIONES))
    for oficial in DECISIONES:
        fila = m["matriz_confusion"][oficial]
        LOG.info("  %-17s %s", CORTO[oficial], "".join(f"{fila[d]:>11}" for d in DECISIONES))
    cd = m["calidad_dato"]
    LOG.info("\nCalidad del dato: reason_code correcto %s · precio correcto %s · tipo de precio %s",
             _pct(cd["reason_code_acierto"]), _pct(cd["precio_acierto"]), _pct(cd["tipo_precio_acierto"]))
    LOG.info("\nPor grupo oficial:")
    for g in m["por_tanda"]:
        LOG.info("  %-45s %3d capturas · acierto %s · costo %d",
                 g["tanda"], g["total"], _pct(g["acierto"]), g["costo"])
