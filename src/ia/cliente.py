"""Cliente de Azure AI Foundry. Lee FOUNDRY_API_KEY, FOUNDRY_ENDPOINT y FOUNDRY_MODEL de .env."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from anthropic import AnthropicFoundry
from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parents[2]
VARIABLES = ("FOUNDRY_API_KEY", "FOUNDRY_ENDPOINT", "FOUNDRY_MODEL")

load_dotenv(RAIZ / ".env")


class ConfiguracionFaltante(RuntimeError):
    """Falta alguna variable FOUNDRY_* en .env."""


def leer_config() -> dict[str, str]:
    """Regresa la configuración del endpoint o falla con un mensaje claro."""
    faltan = [nombre for nombre in VARIABLES if not os.getenv(nombre, "").strip()]
    if faltan:
        raise ConfiguracionFaltante(f"Faltan en .env: {', '.join(faltan)}")
    return {
        "api_key": os.environ["FOUNDRY_API_KEY"].strip(),
        "endpoint": os.environ["FOUNDRY_ENDPOINT"].strip(),
        "modelo": os.environ["FOUNDRY_MODEL"].strip(),
    }


@lru_cache(maxsize=1)
def crear_cliente() -> AnthropicFoundry:
    """Un solo cliente por proceso; reintentos acotados (límite de tokens por minuto)."""
    config = leer_config()
    return AnthropicFoundry(api_key=config["api_key"], base_url=config["endpoint"], max_retries=2, timeout=60)
