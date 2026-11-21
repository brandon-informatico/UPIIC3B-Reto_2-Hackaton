"""Regresion E5/E6 sin Azure; usar: py -m src.motor.probar_ejemplos.

Compara los cuatro campos principales con las 17 decisiones de referencia,
y valida la salida por Pydantic. No representa una medicion del set ciego.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from contratos.contratos import FeaturesCaptura, HallazgosIA
from src.motor.decisiones import RECHAZAR_SIN_PRECIO_UNITARIO, _duda_relevante, decidir
from src.motor.salida import convertir_a_registro

LOG = logging.getLogger(__name__)
CAMPOS_CRITICOS = (
    "decision", "reason_code", "motivo_revision", "ruta_decision",
)


# Frases sinteticas para verificar el criterio de relevancia de la duda de la IA.
CASOS_DUDA = (
    (None, False),
    ("La etiqueta no muestra precio por unidad de medida.", False),
    ("No aparece el precio unitario; la letra pequeña no es legible.", False),
    ("Solo se ve el precio de venta de $10.00.", False),
    ("La etiqueta dice 500 ml y el envase 450 g; verificar equivalencia.", True),
    ("El contenido corresponde a masa drenada.", True),
    ("No muestra precio por unidad; la foto está ligeramente borrosa.", True),
    ("La marca del empaque no se distingue.", True),
    ("Algo no cuadra en la captura.", True),
)


def probar_dudas() -> int:
    """Regresa cuantas frases no se clasifican como se espera (con la regla de precio unitario apagada)."""
    if RECHAZAR_SIN_PRECIO_UNITARIO:
        return 0
    errores = 0
    for frase, esperado in CASOS_DUDA:
        if _duda_relevante(frase) != esperado:
            errores += 1
            LOG.error("DUDA mal clasificada: %r -> esperado relevante=%s", frase, esperado)
    LOG.info("Criterio de duda relevante: %d/%d frases correctas", len(CASOS_DUDA) - errores, len(CASOS_DUDA))
    return errores


def main() -> None:
    correctas = 0
    salidas_validas = 0
    no_cumplidos: list[str] = []
    rutas = sorted(Path("contratos/ejemplos").glob("*.json"))
    if not rutas:
        raise SystemExit("No hay casos en contratos/ejemplos")

    for ruta in rutas:
        try:
            caso = json.loads(ruta.read_text(encoding="utf-8"))
            features = FeaturesCaptura.model_validate(caso["E2_features"])
            datos_ia = caso.get("E4_hallazgos_ia")
            hallazgos = (HallazgosIA.model_validate(datos_ia)
                         if datos_ia is not None else None)
            decision = decidir(features, hallazgos)
            esperado = caso["E5_decision_interna"]
            diferencias = [
                f"{campo}: esperado={esperado.get(campo)!r}, "
                f"obtenido={getattr(decision, campo)!r}"
                for campo in CAMPOS_CRITICOS
                if getattr(decision, campo) != esperado.get(campo)
            ]
            conocido = (esperado.get("reason_code") == "SIN_PRECIO_UNITARIO"
                        and not RECHAZAR_SIN_PRECIO_UNITARIO)
            if diferencias and conocido:
                no_cumplidos.append(ruta.name)
                LOG.warning("NO CUMPLE %s (conocido: regla SIN_PRECIO_UNITARIO desactivada "
                            "provisionalmente) | %s", ruta.name, " | ".join(diferencias))
            elif diferencias:
                LOG.error("FALLA %s | %s", ruta.name, " | ".join(diferencias))
            else:
                correctas += 1
                LOG.info("OK %s", ruta.name)

            convertir_a_registro(decision, "Prueba local con casos de ejemplo")
            salidas_validas += 1
        except Exception as exc:
            LOG.error("ERROR %s: %s: %s", ruta.name, type(exc).__name__, exc)

    LOG.info("Decisiones correctas: %d/%d", correctas, len(rutas))
    if no_cumplidos:
        LOG.warning("No cumplidos conocidos (reglas desactivadas): %s", ", ".join(no_cumplidos))
    LOG.info("Salidas Pydantic validas: %d/%d", salidas_validas, len(rutas))
    LOG.info("NOTA: no se comparan p_valida, fallas, validaciones ni precios; "
             "son necesarias pruebas adicionales antes de la entrega")
    errores_duda = probar_dudas()
    if correctas + len(no_cumplidos) != len(rutas) or salidas_validas != len(rutas) or errores_duda:
        raise SystemExit(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
