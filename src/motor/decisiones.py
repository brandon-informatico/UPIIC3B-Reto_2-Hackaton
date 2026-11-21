"""E3/E5: decisiones con prioridad identidad > calidad > precio.

Reglas provisionales basadas en contratos/ejemplos. PENDIENTE COMITE:
confirmar contratipos, precio unitario y calibrar p_valida.
"""
from __future__ import annotations

from typing import Any

from contratos.contratos import DecisionInterna, FeaturesCaptura, HallazgosIA


# Orden de prioridad oficial del plan: A -> B -> C.
REGLAS_RECHAZO = (
    ("es_contratipo_permitido", "no", "CONTRATIPO_INVALIDO", "A_identidad"),
    ("producto_coincide", "no", "PRODUCTO_NO_COINCIDE", "A_identidad"),
    ("descripcion_completa", "no", "DESCRIPCION_INCOMPLETA", "A_identidad"),
    ("producto_aislado", "no", "CAPTURA_LEJANA", "B_calidad"),
    ("foto_de_pantalla", "si", "FOTO_DE_PANTALLA", "B_calidad"),
    ("fachada_coincide", "no", "FACHADA_INCORRECTA", "B_calidad"),
    ("foto_borrosa", "si", "IMAGEN_BORROSA", "B_calidad"),
    ("etiqueta_visible", "no", "SIN_ETIQUETA_PRECIO", "C_precio"),
    # PENDIENTE COMITE: Brandon propuso revisar esta regla.
    ("precio_unitario_presente", "no", "SIN_PRECIO_UNITARIO", "C_precio"),
)


def _dato(objeto: Any, campo: str, predeterminado: Any = None) -> Any:
    """Lee tanto campos Pydantic como diccionarios, sin perder valores falsos."""
    if isinstance(objeto, dict):
        return objeto.get(campo, predeterminado)
    return getattr(objeto, campo, predeterminado)


def _precio(hallazgos: HallazgosIA | None) -> tuple[float | None, str | None, int]:
    precios = _dato(hallazgos, "precios_en_etiqueta") or []
    if not precios:
        return None, None, 0
    precio = _dato(precios[0], "valor")
    tipo = _dato(precios[0], "tipo")
    # Los tipos vienen del contrato: regular, oferta o volumen.
    return (float(precio) if precio is not None else None, tipo, len(precios))


def _validaciones(
    features: FeaturesCaptura,
    hallazgos: HallazgosIA | None,
    numero_precios: int,
) -> dict[str, str]:
    """Resumen informativo; no decide ni sustituye las reglas de rechazo."""
    resultado = {
        "tienda_fachada": "no_determinable",
        "producto": "no_determinable",
        "codigo_barras": "ok",  # no_leido no es no_coincide
        "evidencia_precio": "no_determinable",
    }
    if _dato(features, "codigo_empaque") == "no_coincide":
        resultado["codigo_barras"] = "falla"
    if hallazgos is None:
        return resultado

    fachada = _dato(hallazgos, "fachada_coincide")
    if fachada == "si":
        resultado["tienda_fachada"] = "ok"
    elif fachada == "no":
        resultado["tienda_fachada"] = "falla"

    if any(_dato(hallazgos, campo) == "no" for campo in (
        "es_contratipo_permitido", "producto_coincide", "descripcion_completa",
    )) or _dato(hallazgos, "foto_borrosa") == "si":
        resultado["producto"] = "falla"
    elif all(_dato(hallazgos, campo) == "si" for campo in (
        "producto_visible", "producto_coincide", "contenido_coincide",
        "descripcion_completa", "descripcion_coincide",
    )):
        resultado["producto"] = "ok"

    if _dato(hallazgos, "foto_borrosa") == "si" or any(
        _dato(hallazgos, campo) == "no"
        for campo in ("etiqueta_visible", "precio_unitario_presente")
    ):
        resultado["evidencia_precio"] = "falla"
    elif (numero_precios == 1 and
          _dato(hallazgos, "etiqueta_visible") == "si" and
          _dato(hallazgos, "etiqueta_legible") == "si"):
        resultado["evidencia_precio"] = "ok"
    return resultado


def decidir(features: FeaturesCaptura, hallazgos: HallazgosIA | None) -> DecisionInterna:
    """E3 (local, sin IA) y E5 (IA). Nunca aprueba solo con E3."""
    capture_id = features.capture_id
    estado = features.estado
    precio, tipo_precio, numero_precios = _precio(hallazgos)
    validaciones = _validaciones(features, hallazgos, numero_precios)
    campos = dict(
        capture_id=capture_id,
        p_valida=0.5,  # PENDIENTE: calibrar con Ale; no es probabilidad medida.
        fallas=[],
        reason_code=None,
        motivo_revision=None,
        validaciones=validaciones,
        precio_detectado=precio,
        tipo_precio=tipo_precio,
        codigo_barras_detectado=None,
        ruta_decision="ia" if hallazgos is not None else "error",
    )

    def revision(motivo: str, ruta: str) -> DecisionInterna:
        return DecisionInterna(**{**campos,
            "decision": "revision_manual", "motivo_revision": motivo,
            "ruta_decision": ruta,
        })

    # E3: causas comprobables sin gastar tokens, sin aprobar localmente.
    if estado == "sin_fotos":
        return revision("sin_fotos", "local")
    if estado == "incompleta":
        errores = " ".join(map(str, _dato(features, "errores", []) or [])).lower()
        corrupta = any(texto in errores for texto in (
            "no se pudo abrir", "corrupt", "no se puede abrir", "no se pudo leer",
        ))
        return revision("imagen_corrupta" if corrupta else "imagen_faltante", "local")
    if hallazgos is None:
        return revision("ia_error", "error")

    # Rechazos demostrables, primero identidad, despues calidad y precio.
    for campo, valor, codigo, frente in REGLAS_RECHAZO:
        if _dato(hallazgos, campo) == valor:
            return DecisionInterna(**{**campos,
                "decision": "rechazada", "reason_code": codigo,
                "fallas": [{
                    "reason_code": codigo, "frente": frente, "fuente": "ia",
                    "detalle": f"{campo}={valor}",
                }],
            })

    # Incertidumbre: no convertir promociones ambiguas en rechazo.
    if numero_precios > 1:
        return revision("dos_precios", "ia")
    if (_dato(hallazgos, "producto_coincide") == "no_determinable" or
        _dato(hallazgos, "contenido_coincide") == "no_determinable" or
        _dato(hallazgos, "descripcion_coincide") == "no_determinable" or
        _dato(features, "codigo_empaque") == "no_coincide"):
        return revision("duda_identidad", "ia")
    if _dato(hallazgos, "etiqueta_legible") in ("no_determinable", "parcial"):
        return revision("duda_precio", "ia")

    # Aprobacion conservadora: solo cuando los campos decisivos son explicitamente 'si'.
    # El ejemplo 01 admite es_contratipo_permitido='sin_informacion';
    # PENDIENTE COMITE: confirmar la politica de contratipos en producción.
    campos_si = (
        "producto_visible", "producto_coincide", "contenido_coincide",
        "producto_aislado", "fachada_coincide", "etiqueta_visible",
        "etiqueta_legible", "descripcion_completa", "descripcion_coincide",
        "precio_unitario_presente",
    )
    aprobable = (
        numero_precios == 1 and precio is not None and
        all(_dato(hallazgos, campo) == "si" for campo in campos_si) and
        _dato(hallazgos, "foto_borrosa") == "no" and
        _dato(hallazgos, "foto_de_pantalla") == "no" and
        _dato(hallazgos, "es_contratipo_permitido") in ("si", "sin_informacion") and
        _dato(features, "codigo_empaque") != "no_coincide"
    )
    if aprobable:
        return DecisionInterna(**{**campos,
            "decision": "aprobada", "p_valida": 0.985,  # ejemplo; sin calibrar
        })
    return revision("confianza_insuficiente", "ia")
