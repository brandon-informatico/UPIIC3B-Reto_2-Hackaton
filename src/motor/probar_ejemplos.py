"""Regresion E5/E6 sin Azure; usar: py -m src.motor.probar_ejemplos.

Compara los cuatro campos principales con las 17 decisiones de referencia,
y valida la salida por Pydantic. No representa una medicion del set ciego.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from contratos.contratos import FeaturesCaptura, HallazgosIA
from src.motor.decisiones import decidir
from src.motor.salida import convertir_a_registro

LOG = logging.getLogger(__name__)
CAMPOS_CRITICOS = (
    "decision", "reason_code", "motivo_revision", "ruta_decision",
)


def main() -> None:
    correctas = 0
    salidas_validas = 0
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
            if diferencias:
                LOG.error("FALLA %s | %s", ruta.name, " | ".join(diferencias))
            else:
                correctas += 1
                LOG.info("OK %s", ruta.name)

            convertir_a_registro(decision, "Prueba local con casos de ejemplo")
            salidas_validas += 1
        except Exception as exc:
            LOG.error("ERROR %s: %s: %s", ruta.name, type(exc).__name__, exc)

    LOG.info("Decisiones correctas: %d/%d", correctas, len(rutas))
    LOG.info("Salidas Pydantic validas: %d/%d", salidas_validas, len(rutas))
    LOG.info("NOTA: no se comparan p_valida, fallas, validaciones ni precios; "
             "son necesarias pruebas adicionales antes de la entrega")
    if correctas != len(rutas) or salidas_validas != len(rutas):
        raise SystemExit(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
