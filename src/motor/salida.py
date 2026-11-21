"""E6. Convierte decisiones a registros oficiales con contratos Pydantic v2.

No replica el esquema oficial: utiliza las funciones y modelos de contratos.
"""
from __future__ import annotations

from typing import Any

from contratos.contratos import RegistroSalida, a_oficial, respaldo_revision

LARGO_MAXIMO = 300  # RegistroSalida.explicacion

TEXTO_RECHAZO = {
    "PRODUCTO_NO_COINCIDE": "El producto de la foto no corresponde al producto esperado.",
    "CONTRATIPO_INVALIDO": "El producto fotografiado es un sustituto no permitido.",
    "DESCRIPCION_INCOMPLETA": "La descripcion del producto en la evidencia esta incompleta.",
    "PRODUCTO_NO_VISIBLE": "El producto no se ve en la foto.",
    "FACHADA_INCORRECTA": "La fachada no corresponde a la tienda seleccionada.",
    "CAPTURA_LEJANA": "La foto del producto se tomo demasiado lejos para validarlo.",
    "IMAGEN_BORROSA": "La evidencia esta borrosa y no permite validar la captura.",
    "FOTO_DE_PANTALLA": "La foto parece tomada a la pantalla de otro dispositivo.",
    "SIN_ETIQUETA_PRECIO": "No hay etiqueta de precio visible.",
    "SIN_PRECIO_UNITARIO": "La etiqueta no muestra el precio unitario.",
}
TEXTO_REVISION = {
    "duda_identidad": "No se pudo confirmar con certeza la identidad o el contenido del producto.",
    "duda_calidad": "La calidad de la evidencia no permite decidir con seguridad.",
    "duda_precio": "No se pudo leer con claridad el precio de la etiqueta.",
    "dos_precios": "La etiqueta muestra mas de un precio; hay que confirmar cual aplica.",
    "precio_distinto_al_capturado": "El precio de la etiqueta no coincide con el capturado.",
    "contratipo_sin_informacion": "No hay informacion suficiente para validar el contratipo.",
    "confianza_insuficiente": "La evidencia no alcanza la confianza necesaria para aprobar automaticamente.",
    "imagen_faltante": "Falta al menos una de las tres fotos de la captura.",
    "imagen_corrupta": "Al menos una foto no se pudo abrir.",
    "sin_fotos": "La captura no tiene fotos.",
    "ia_error": "No fue posible analizar la evidencia con IA.",
    "salida_invalida": "Error interno al procesar la captura.",
}


def _dato(objeto: Any, campo: str) -> Any:
    return objeto.get(campo) if isinstance(objeto, dict) else getattr(objeto, campo, None)


def explicar(decision: Any, hallazgos: Any = None) -> str:
    """Texto breve en espanol para `explicacion`; agrega la duda de la IA cuando ayuda a revisar."""
    estado = _dato(decision, "decision")
    if estado == "aprobada":
        precio = _dato(decision, "precio_detectado")
        texto = "Fachada, producto y etiqueta coinciden con lo esperado" + (
            f"; precio leido en etiqueta: ${precio:.2f}." if precio is not None else ".")
    elif estado == "rechazada":
        codigo = _dato(decision, "reason_code")
        texto = TEXTO_RECHAZO.get(codigo, f"Rechazada por {codigo}.")
    else:
        motivo = _dato(decision, "motivo_revision")
        texto = TEXTO_REVISION.get(motivo, "Requiere revision manual.")
    duda = _dato(hallazgos, "duda_principal") if hallazgos is not None else None
    if duda and estado == "revision_manual":
        texto = f"{texto} Detalle: {duda}"
    return texto if len(texto) <= LARGO_MAXIMO else texto[: LARGO_MAXIMO - 3].rstrip() + "..."


def convertir_a_registro(decision: object, explicacion: str) -> RegistroSalida:
    """E6: aplica la conversion oficial y valida el resultado."""
    registro = a_oficial(decision, explicacion)
    return RegistroSalida.model_validate(registro)


def crear_respaldo(capture_id: str, motivo: str, explicacion: str) -> RegistroSalida:
    """Construye una revision manual oficial cuando alguna etapa falla."""
    registro = respaldo_revision(capture_id, motivo, explicacion)
    return RegistroSalida.model_validate(registro)
