from contratos.contratos import DecisionInterna, FeaturesCaptura, HallazgosIA


def decidir(features: FeaturesCaptura, hallazgos: HallazgosIA | None) -> DecisionInterna:
    validaciones = {
        "tienda_fachada": "no_determinable",
        "producto": "no_determinable",
        "codigo_barras": "no_determinable",
        "evidencia_precio": "no_determinable",
    }

    # Reglas provisionales, pendientes de confirmar.
    reglas = [
        ("es_contratipo_permitido", "no", "CONTRATIPO_INVALIDO", "A_identidad"),
        ("producto_coincide", "no", "PRODUCTO_NO_COINCIDE", "A_identidad"),
        ("descripcion_completa", "no", "DESCRIPCION_INCOMPLETA", "A_identidad"),
        ("producto_aislado", "no", "CAPTURA_LEJANA", "B_calidad"),
        ("foto_de_pantalla", "si", "FOTO_DE_PANTALLA", "B_calidad"),
        ("fachada_coincide", "no", "FACHADA_INCORRECTA", "B_calidad"),
        ("etiqueta_visible", "no", "SIN_ETIQUETA_PRECIO", "C_precio"),
        ("precio_unitario_presente", "no", "SIN_PRECIO_UNITARIO", "C_precio"),
    ]

    if features.estado == "completa" and hallazgos is not None:
        for campo, valor, codigo, frente in reglas:
            if getattr(hallazgos, campo) == valor:
                return DecisionInterna(
                    capture_id=features.capture_id,
                    decision="rechazada",
                    p_valida=0.5,
                    fallas=[{
                        "reason_code": codigo,
                        "frente": frente,
                        "fuente": "ia",
                        "detalle": f"{campo}={valor}",
                    }],
                    reason_code=codigo,
                    motivo_revision=None,
                    validaciones=validaciones,
                    precio_detectado=None,
                    tipo_precio=None,
                    codigo_barras_detectado=None,
                    ruta_decision="ia",
                )

    if features.estado == "sin_fotos":
        motivo, ruta = "sin_fotos", "local"
    elif features.estado == "incompleta":
        motivo, ruta = "imagen_faltante", "local"
    elif hallazgos is None:
        motivo, ruta = "ia_error", "error"
    else:
        motivo, ruta = "confianza_insuficiente", "ia"

    return DecisionInterna(
        capture_id=features.capture_id,
        decision="revision_manual",
        p_valida=0.5,  # PENDIENTE: calibrar.
        fallas=[],
        reason_code=None,
        motivo_revision=motivo,
        validaciones=validaciones,
        precio_detectado=None,
        tipo_precio=None,
        codigo_barras_detectado=None,
        ruta_decision=ruta,
    )
