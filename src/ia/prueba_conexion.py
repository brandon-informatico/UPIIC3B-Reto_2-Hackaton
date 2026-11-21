"""Paso 1 · Prueba de conexión con Azure AI Foundry.

Uso (desde la raíz del repo):
    .venv/bin/python -m src.ia.prueba_conexion
"""
from __future__ import annotations

import logging
import sys
import time

from src.ia.cliente import ConfiguracionFaltante, crear_cliente, leer_config

logging.basicConfig(level=logging.INFO, format="%(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger(__name__)


def main() -> int:
    try:
        config = leer_config()
    except ConfiguracionFaltante as error:
        log.error("✗ %s\n  Abre el archivo .env y pega tu llave después de FOUNDRY_API_KEY=", error)
        return 1

    inicio = time.perf_counter()
    try:
        respuesta = crear_cliente().messages.create(
            model=config["modelo"],
            max_tokens=16,
            messages=[{"role": "user", "content": "Responde solo con la palabra: OK"}],
        )
    except Exception as error:  # noqa: BLE001 — queremos ver cualquier falla de conexión
        log.error("✗ La llamada falló: %s: %s", type(error).__name__, error)
        return 1

    latencia_ms = round((time.perf_counter() - inicio) * 1000)
    texto = "".join(bloque.text for bloque in respuesta.content if bloque.type == "text").strip()
    log.info("✓ Conexión OK · modelo=%s · respuesta=%r", respuesta.model, texto)
    log.info(
        "  tokens entrada=%s salida=%s · %s ms · stop_reason=%s",
        respuesta.usage.input_tokens, respuesta.usage.output_tokens, latencia_ms, respuesta.stop_reason,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
