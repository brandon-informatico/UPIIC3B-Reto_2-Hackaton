"""Constantes y validación compartidas por todos los módulos (ver CONTEXT.md, secciones 4 y 5).

Responsable: Pat. Cualquier cambio aquí se acuerda con el equipo y se refleja en CONTEXT.md.
"""
from __future__ import annotations

from typing import Any

# --- Decisiones ---
APROBADA = "aprobada"
RECHAZADA = "rechazada"
REVISION_MANUAL = "revision_manual"
DECISIONES = (APROBADA, RECHAZADA, REVISION_MANUAL)

# --- Imágenes de cada captura ---
TIPOS_IMAGEN = ("facade", "product", "shelf")
CALIDADES_IMAGEN = ("ok", "borrosa", "lejana", "pantalla", "no_disponible")

# --- Validaciones del JSON de salida ---
VALIDACIONES = ("tienda_fachada", "producto", "codigo_barras", "evidencia_precio")
VALORES_VALIDACION = ("ok", "falla", "duda")

# --- reason_code provisionales (PENDIENTE: reemplazar por la lista oficial) ---
REASON_CODES = {
    "PRODUCTO_NO_COINCIDE": "A",
    "CONTRATIPO_INVALIDO": "A",
    "DESCRIPCION_INCOMPLETA": "A",
    "PRODUCTO_NO_VISIBLE": "A",
    "FACHADA_INCORRECTA": "B",
    "CAPTURA_LEJANA": "B",
    "IMAGEN_BORROSA": "B",
    "FOTO_DE_PANTALLA": "B",
    "SIN_ETIQUETA_PRECIO": "C",
    "SIN_PRECIO_UNITARIO": "C",
}

# --- Costo operativo por resultado (tabla oficial) ---
COSTO = {"correcta": 0, REVISION_MANUAL: 1, "rechazada_siendo_valida": 3, "aprobada_siendo_invalida": 10}

CAMPOS_SALIDA = (
    "capture_id",
    "decision",
    "confidence_score",
    "reason_code",
    "validaciones",
    "precio_detectado",
    "codigo_barras_detectado",
    "explicacion",
)


def validar_resultado(resultado: dict[str, Any]) -> list[str]:
    """Regresa la lista de errores de formato de un resultado; lista vacía = válido."""
    errores = [f"falta {campo}" for campo in CAMPOS_SALIDA if campo not in resultado]
    if errores:
        return errores
    if resultado["decision"] not in DECISIONES:
        errores.append(f"decision inválida: {resultado['decision']!r}")
    score = resultado["confidence_score"]
    if not isinstance(score, (int, float)) or not 0 <= score <= 1:
        errores.append("confidence_score debe ser número entre 0 y 1")
    codigo = resultado["reason_code"]
    if resultado["decision"] == APROBADA and codigo is not None:
        errores.append("reason_code debe ser null cuando la decisión es aprobada")
    if codigo is not None and codigo not in REASON_CODES:
        errores.append(f"reason_code desconocido: {codigo!r}")
    validaciones = resultado["validaciones"]
    if not isinstance(validaciones, dict):
        errores.append("validaciones debe ser un objeto")
    else:
        for clave in VALIDACIONES:
            if validaciones.get(clave) not in VALORES_VALIDACION:
                errores.append(f"validaciones.{clave} inválida: {validaciones.get(clave)!r}")
    return errores
