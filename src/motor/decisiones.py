"""E3/E5: decisiones con prioridad identidad > calidad > precio.

Reglas provisionales basadas en contratos/ejemplos. PENDIENTE COMITE:
confirmar contratipos, precio unitario y calibrar p_valida.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from contratos.contratos import DecisionInterna, FeaturesCaptura, HallazgosIA


# Orden de prioridad oficial del plan: A -> B -> C.
REGLAS_RECHAZO = (
    ("es_contratipo_permitido", "no", "CONTRATIPO_INVALIDO", "A_identidad"),
    ("producto_coincide", "no", "PRODUCTO_NO_COINCIDE", "A_identidad"),
    ("descripcion_completa", "no", "DESCRIPCION_INCOMPLETA", "A_identidad"),
    # Borrosa primero dentro de B: en desarrollo da +2 rechazos correctos y 0 rechazos falsos.
    ("foto_borrosa", ("si", "parcial"), "IMAGEN_BORROSA", "B_calidad"),
    ("producto_aislado", "no", "CAPTURA_LEJANA", "B_calidad"),
    ("foto_de_pantalla", "si", "FOTO_DE_PANTALLA", "B_calidad"),
    ("fachada_coincide", "no", "FACHADA_INCORRECTA", "B_calidad"),
    ("etiqueta_visible", "no", "SIN_ETIQUETA_PRECIO", "C_precio"),
)

# PENDIENTE COMITE: SIN_PRECIO_UNITARIO. La IA marca precio_unitario_presente="no" en las 33 aprobadas
# de desarrollo: como regla de rechazo tumbaria todas las validas (33 x 3 puntos) y como requisito para
# aprobar no aprobaria nada. Encender cuando la IA lo detecte bien.
# DESACTIVADA PROVISIONALMENTE: con la regla apagada NO se cumple el ejemplo
# contratos/ejemplos/08_rechazo_sin_precio_unitario.json (espera rechazo SIN_PRECIO_UNITARIO).
RECHAZAR_SIN_PRECIO_UNITARIO = False
if RECHAZAR_SIN_PRECIO_UNITARIO:
    REGLAS_RECHAZO += (("precio_unitario_presente", "no", "SIN_PRECIO_UNITARIO", "C_precio"),)

# Evidencia insuficiente: validaciones generales que impiden APROBAR (mandan a revision; nunca rechazan).
#
# Metrica confirmada por los jueces: acierto en aprobada / revision / rechazo.
# El motor decide SOLO con la evidencia de las fotos (IA + vision local). No usa fecha, hora ni tienda.
#
# NO_APROBAR_CON_DUDA_IA: "desactivada" (por defecto) | "relevante" | "cualquiera".
# Con la metrica de acierto en tres categorias, mandar buenas a revision por la duda de la IA resta aciertos;
# por defecto queda desactivada. "relevante" solo impide aprobar si alguna frase de la duda es relevante.
NO_APROBAR_CON_DUDA_IA = "desactivada"
#
# Criterio por frase (separadas por ";" o por un "." que no este entre digitos), sin acentos y en
# minusculas. Primero gana RELEVANTE:
#   RELEVANTE   identidad/contenido (contenido, peso, neto, masa drenada, equivalencia, "85 g", marca, sabor,
#               presentacion, otro producto) o calidad de la foto (borrosa, desenfocada, cortada, lejos, reflejo).
#   IRRELEVANTE precio por unidad de medida y la letra pequena de la etiqueta, mientras
#               RECHAZAR_SIN_PRECIO_UNITARIO este apagada (ese aspecto no decide), y la mencion del precio de venta.
#   Sin categoria: RELEVANTE (conservador).
_FRASE_RELEVANTE = re.compile(
    r"contenido|peso|neto|drenad|equivalen|\b\d+([.,]\d+)?\s?(g|gr|grs|kg|ml|l|lt)\b|marca|sabor|presentacion"
    r"|otro producto|no coincide|borros|desenfoc|cortad|lejos|lejan|reflej")
_FRASE_IRRELEVANTE = re.compile(
    r"precio (por|x) (unidad|kilo|kg|litro|lt|l|ml|gramo|g|100)|precio unitario|unidad de medida"
    r"|(texto|letra)s? pequen|precio de venta")

# Probabilidad de que la captura SEA VALIDA ante una falla explicita (no es la confianza del rechazo):
# a_oficial la convierte en confidence_score = 1 - p_valida = 0.9. Los ejemplos de contratos usan 0.03-0.10.
# PENDIENTE: calibrar con datos etiquetados.
P_VALIDA_RECHAZO = 0.1

# CAPTURA_LEJANA solo con evidencia. La IA marca producto_aislado="no" tambien cuando el producto "no destaca"
# entre otros del anaquel aunque se vea bien (en desarrollo, 4 de 12 rechazos CAPTURA_LEJANA eran capturas
# aprobadas o de revision). Si la IA leyo todo lo que una foto lejana impediria leer, "lejana" se contradice:
# no se rechaza, va a revision (duda_calidad). Nunca se aprueba con producto_aislado distinto de "si".
_LEIDO_COMPLETO = ("producto_visible", "producto_coincide", "contenido_coincide",
                   "descripcion_completa", "descripcion_coincide")


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


def _lejana_contradicha(hallazgos: HallazgosIA) -> bool:
    """True si la IA dice 'lejana' pero leyo marca, contenido y descripcion sin borrosidad."""
    return (_dato(hallazgos, "producto_aislado") == "no"
            and all(_dato(hallazgos, campo) == "si" for campo in _LEIDO_COMPLETO)
            and _dato(hallazgos, "foto_borrosa") == "no"
            and bool(_dato(hallazgos, "marca_detectada"))
            and bool(_dato(hallazgos, "contenido_detectado")))


def _codigo_leido(features: FeaturesCaptura) -> str | None:
    """Primer codigo de producto leido localmente en la foto del producto (los QR no cuentan)."""
    for codigo in _dato(_dato(features, "product"), "codigos_leidos") or []:
        if "QR" not in str(_dato(codigo, "formato", "")).upper():
            return _dato(codigo, "texto")
    return None


def _sin_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto.lower()) if unicodedata.category(c) != "Mn")


def _duda_relevante(duda: str | None) -> bool:
    """True si alguna frase de la duda de la IA es relevante para aprobar (criterio arriba)."""
    if not duda:
        return False
    for frase in filter(None, (f.strip() for f in re.split(r";|\.(?!\d)", _sin_acentos(duda)))):
        if _FRASE_RELEVANTE.search(frase):
            return True
        if RECHAZAR_SIN_PRECIO_UNITARIO or not _FRASE_IRRELEVANTE.search(frase):
            return True
    return False


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
        for campo in ("etiqueta_visible",)
    ):
        resultado["evidencia_precio"] = "falla"
    elif (numero_precios == 1 and
          _dato(hallazgos, "etiqueta_visible") == "si" and
          _dato(hallazgos, "etiqueta_legible") == "si"):
        resultado["evidencia_precio"] = "ok"
    return resultado


def decidir(features: FeaturesCaptura, hallazgos: HallazgosIA | None) -> DecisionInterna:
    """E3 (local, sin IA) y E5 (IA). Nunca aprueba solo con E3. Solo usa evidencia de las fotos."""
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
        codigo_barras_detectado=_codigo_leido(features),
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
    lejana_contradicha = _lejana_contradicha(hallazgos)
    for campo, valor, codigo, frente in REGLAS_RECHAZO:
        if codigo == "CAPTURA_LEJANA" and lejana_contradicha:
            continue  # se resuelve abajo como duda_calidad, despues de las demas reglas de rechazo
        valores = valor if isinstance(valor, tuple) else (valor,)
        if _dato(hallazgos, campo) in valores:
            return DecisionInterna(**{**campos,
                "decision": "rechazada", "reason_code": codigo,
                "p_valida": P_VALIDA_RECHAZO,
                "fallas": [{
                    "reason_code": codigo, "frente": frente, "fuente": "ia",
                    "detalle": f"{campo}={_dato(hallazgos, campo)}",
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
    # Sin precio legible es duda de precio; una etiqueta "parcial" con precio leido termina en
    # confianza_insuficiente (ejemplo 13).
    if precio is None or _dato(hallazgos, "etiqueta_legible") in ("no", "no_determinable"):
        return revision("duda_precio", "ia")
    if lejana_contradicha:
        return revision("duda_calidad", "ia")

    # Aprobacion conservadora: solo cuando los campos decisivos son explicitamente 'si'.
    # El ejemplo 01 admite es_contratipo_permitido='sin_informacion';
    # PENDIENTE COMITE: confirmar la politica de contratipos en producción.
    campos_si = (
        "producto_visible", "producto_coincide", "contenido_coincide",
        "producto_aislado", "fachada_coincide", "etiqueta_visible",
        "etiqueta_legible", "descripcion_completa", "descripcion_coincide",
    )
    aprobable = (
        numero_precios == 1 and precio is not None and
        all(_dato(hallazgos, campo) == "si" for campo in campos_si) and
        _dato(hallazgos, "foto_borrosa") == "no" and
        _dato(hallazgos, "foto_de_pantalla") == "no" and
        _dato(hallazgos, "es_contratipo_permitido") in ("si", "sin_informacion") and
        _dato(features, "codigo_empaque") != "no_coincide"
    )
    duda = _dato(hallazgos, "duda_principal")
    if aprobable and duda and (NO_APROBAR_CON_DUDA_IA == "cualquiera" or (
            NO_APROBAR_CON_DUDA_IA == "relevante" and _duda_relevante(duda))):
        return revision("confianza_insuficiente", "ia")
    if aprobable:
        return DecisionInterna(**{**campos,
            "decision": "aprobada", "p_valida": 0.985,  # ejemplo; sin calibrar
        })
    return revision("confianza_insuficiente", "ia")
