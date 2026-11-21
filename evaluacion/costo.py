"""Costo operativo (tabla oficial del reto) y acierto en las tres categorías. Responsable: Ale (E8).

Tabla oficial: correcta 0 · enviada a revisión manual 1 · rechazada siendo válida 3 · aprobada siendo inválida 10.
"""
from __future__ import annotations

from collections import Counter
from typing import Iterable

DECISIONES = ("aprobada", "revision_manual", "rechazada")
COSTO_UNITARIO = {"correctas": 0, "revision_manual": 1, "rechazo_valida": 3, "aprobacion_invalida": 10}

# PENDIENTE (script oficial de costo): como cuenta rechazar una captura cuya etiqueta es revision_manual.
# Supuesto conservador: el analista no la rechazo, asi que puede ser valida -> "rechazo_valida" (3 puntos).
RECHAZAR_REVISION_CUENTA_COMO = "rechazo_valida"


def clasificar(oficial: str, motor: str) -> str:
    """Categoria de costo de una captura segun la decision oficial y la del motor."""
    if motor == "revision_manual":
        return "revision_manual"
    if motor == oficial:
        return "correctas"
    if motor == "aprobada":
        return "aprobacion_invalida"  # el oficial la rechazo o la mando a revision
    if oficial == "aprobada":
        return "rechazo_valida"
    return RECHAZAR_REVISION_CUENTA_COMO


def desglose(pares: Iterable[tuple[str, str]]) -> dict[str, dict[str, int]]:
    """{categoria: {"n": capturas, "costo_unitario": puntos}} con el formato que lee el dashboard."""
    conteo = Counter(clasificar(oficial, motor) for oficial, motor in pares)
    return {k: {"n": conteo.get(k, 0), "costo_unitario": v} for k, v in COSTO_UNITARIO.items()}


def costo_total(desglose_costo: dict[str, dict[str, int]]) -> int:
    return sum(d["n"] * d["costo_unitario"] for d in desglose_costo.values())


def matriz_confusion(pares: Iterable[tuple[str, str]]) -> dict[str, dict[str, int]]:
    """{oficial: {motor: n}} (filas = decision real, columnas = decision del motor)."""
    matriz = {o: {m: 0 for m in DECISIONES} for o in DECISIONES}
    for oficial, motor in pares:
        if oficial in matriz and motor in matriz[oficial]:
            matriz[oficial][motor] += 1
    return matriz


def acierto(matriz: dict[str, dict[str, int]]) -> float | None:
    """Metrica confirmada por los jueces: capturas en la categoria correcta / total."""
    total = sum(sum(fila.values()) for fila in matriz.values())
    return round(sum(matriz[d][d] for d in DECISIONES) / total, 4) if total else None


def precision_aprobaciones(matriz: dict[str, dict[str, int]]) -> float | None:
    """Criterio publicado: de lo aprobado, cuanto es realmente valido."""
    aprobadas = sum(matriz[o]["aprobada"] for o in DECISIONES)
    return round(matriz["aprobada"]["aprobada"] / aprobadas, 4) if aprobadas else None
