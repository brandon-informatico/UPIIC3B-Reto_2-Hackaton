"""E6. Convierte decisiones a registros oficiales con contratos Pydantic v2.

No replica el esquema oficial: utiliza las funciones y modelos de contratos.
"""
from __future__ import annotations

from contratos.contratos import RegistroSalida, a_oficial, respaldo_revision


def convertir_a_registro(decision: object, explicacion: str) -> RegistroSalida:
    """E6: aplica la conversiÃ³n oficial y valida el resultado."""
    registro = a_oficial(decision, explicacion)
    return RegistroSalida.model_validate(registro)


def crear_respaldo(capture_id: str, motivo: str, explicacion: str) -> RegistroSalida:
    """Construye una revisiÃ³n manual oficial cuando alguna etapa falla."""
    registro = respaldo_revision(capture_id, motivo, explicacion)
    return RegistroSalida.model_validate(registro)

