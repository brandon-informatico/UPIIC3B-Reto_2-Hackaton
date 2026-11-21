"""Normaliza y valida los campos de cada captura (CONTEXT.md, sección 3).

Reglas:
- Códigos de barras siempre como texto (``str``), sin espacios.
- Precios como ``float`` redondeado a 2 decimales; ``None`` si no es un número positivo.
- Textos sin espacios repetidos ni tabuladores; el significado no se cambia.
- Nunca se inventan valores: lo que falta queda en ``None`` y se anota en ``banderas_datos``.
"""
from __future__ import annotations

import logging
import math
import re
from typing import Any

log = logging.getLogger(__name__)

# Campos que el motor no debe leer (solo existen en desarrollo).
CAMPOS_ETIQUETA = ("decision_esperada", "motivo_rechazo")

CAMPOS_TEXTO = (
    "capture_id", "capture_store_name", "capture_date", "capture_brand", "product_name",
    "unit_product", "product_group", "product_line", "facade_file", "product_file", "shelf_file",
    "facade_url", "product_url", "shelf_url",
)
CAMPOS_CODIGO = ("capture_barcode", "product_barcode")
CAMPOS_PRECIO = ("capture_price", "product_price", "min_product_price", "max_product_price")
CAMPOS_OBLIGATORIOS = (
    "capture_id", "capture_store_name", "capture_price", "product_name",
    "facade_file", "product_file", "shelf_file",
)

_ESPACIOS = re.compile(r"\s+")
_PATRON_ID = re.compile(r"^CAP-\d+$")


def limpiar_texto(valor: Any) -> str | None:
    """Quita espacios repetidos, tabuladores y saltos; '' se vuelve None."""
    if valor is None:
        return None
    texto = _ESPACIOS.sub(" ", str(valor)).strip()
    return texto or None


def limpiar_codigo(valor: Any) -> str | None:
    """Código de barras como texto. Acepta int, float sin decimales o str."""
    if valor is None or (isinstance(valor, float) and math.isnan(valor)):
        return None
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    codigo = re.sub(r"\s+", "", str(valor))
    return codigo or None


def limpiar_precio(valor: Any) -> float | None:
    """Precio en pesos MXN con 2 decimales; None si no es un número positivo."""
    if valor is None or isinstance(valor, bool):
        return None
    try:
        precio = float(str(valor).replace("$", "").replace(",", "").strip())
    except ValueError:
        return None
    if math.isnan(precio) or precio < 0:
        return None
    return round(precio, 2)


def limpiar_numero(valor: Any) -> float | None:
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(numero) else numero


def limpiar_captura(captura: dict[str, Any], incluir_etiquetas: bool = False) -> dict[str, Any]:
    """Regresa una copia limpia de la captura con la lista ``banderas_datos``.

    Las banderas describen problemas de datos (no de imagen) para que el motor decida qué hacer:
    ``campo_vacio:<campo>``, ``precio_invalido:<campo>``, ``id_invalido``, ``precio_fuera_de_rango``,
    ``codigo_capturado_distinto``.
    """
    limpia: dict[str, Any] = {}
    banderas: list[str] = []

    for campo in CAMPOS_TEXTO:
        if campo in captura:
            limpia[campo] = limpiar_texto(captura[campo])
    for campo in CAMPOS_CODIGO:
        if campo in captura:
            limpia[campo] = limpiar_codigo(captura[campo])
    for campo in CAMPOS_PRECIO:
        if campo in captura:
            original = captura[campo]
            limpia[campo] = limpiar_precio(original)
            if original not in (None, "") and limpia[campo] is None:
                banderas.append(f"precio_invalido:{campo}")
    limpia["unit_quantity_product"] = limpiar_numero(captura.get("unit_quantity_product"))
    id_producto = limpiar_numero(captura.get("id_product"))
    limpia["id_product"] = int(id_producto) if id_producto is not None else None

    if incluir_etiquetas:
        for campo in CAMPOS_ETIQUETA:
            limpia[campo] = limpiar_texto(captura.get(campo)) or ""

    for campo in CAMPOS_OBLIGATORIOS:
        if limpia.get(campo) is None:
            banderas.append(f"campo_vacio:{campo}")
    if limpia.get("capture_id") and not _PATRON_ID.match(limpia["capture_id"]):
        banderas.append("id_invalido")

    precio, minimo, maximo = (limpia.get(c) for c in ("capture_price", "min_product_price", "max_product_price"))
    if precio is not None and minimo is not None and maximo is not None and maximo > 0:
        if not minimo <= precio <= maximo:
            banderas.append("precio_fuera_de_rango")
    capturado, esperado = limpia.get("capture_barcode"), limpia.get("product_barcode")
    if capturado and esperado and capturado.lstrip("0") != esperado.lstrip("0"):
        banderas.append("codigo_capturado_distinto")

    limpia["banderas_datos"] = banderas
    return limpia
