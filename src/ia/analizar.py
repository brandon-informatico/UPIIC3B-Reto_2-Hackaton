"""E4 · analizar_captura(captura, features) -> (HallazgosIA | None, UsoIA | None).

- Salida estructurada: el modelo responde con el schema de HallazgosIA y pydantic la valida.
- Caché en cache/ia/<capture_id>.json por versión de prompt: no se paga dos veces la misma captura.
- Reintentos acotados solo en errores temporales (límite por minuto, red, 5xx).
- Si la IA falla regresa (None, uso_ia | None) y el motor manda la captura a revision_manual (ia_error).
"""
from __future__ import annotations

import json
import logging
import time

import anthropic
from pydantic import ValidationError

from contratos import CapturaPreparada, FeaturesCaptura, HallazgosIA, UsoIA
from src.ia.cliente import RAIZ, crear_cliente, leer_config
from src.ia.imagenes import TIPOS_FOTO, TITULOS, bloque_imagen, rutas_fotos
from src.ia.prompt import INSTRUCCIONES, VERSION_PROMPT, describir_captura

log = logging.getLogger(__name__)

MODOS_PENSAMIENTO = {"adaptativo": {"type": "adaptive"}, "desactivado": {"type": "disabled"}}
# Comparación v2 sobre 5 ejemplos reales: desactivado 60/80 · 5704 tok · 1.6 s | adaptativo-low 63/80 · 5961 tok · 2.6 s
# | adaptativo 60/80 · 6553 tok · 5.4 s. PENDIENTE: confirmar con la evaluación de Ale sobre las 100 capturas.
PENSAMIENTO = "adaptativo"
ESFUERZO: str | None = "low"  # None = default del modelo; "low" | "medium" | "high"
MAX_TOKENS = {"adaptativo": 4096, "desactivado": 1024}  # el razonamiento también cuenta como salida
TIMEOUT_S = 90
MAX_INTENTOS = 3
ERRORES_TEMPORALES = (
    anthropic.RateLimitError,
    anthropic.APIConnectionError,
    anthropic.APITimeoutError,
    anthropic.InternalServerError,
)
CARPETA_CACHE = RAIZ / "cache" / "ia"


def version_completa(pensamiento: str, esfuerzo: str | None) -> str:
    """Versión registrada en UsoIA y usada para la caché: prompt + modo de razonamiento."""
    return f"{VERSION_PROMPT}/{pensamiento}" + (f"-{esfuerzo}" if esfuerzo else "")


def _leer_cache(capture_id: str, version: str) -> tuple[HallazgosIA, UsoIA] | None:
    ruta_cache = CARPETA_CACHE / f"{capture_id}.json"
    if not ruta_cache.exists():
        return None
    try:
        datos = json.loads(ruta_cache.read_text(encoding="utf-8"))
        uso_ia = UsoIA(**datos["uso_ia"])
        if uso_ia.version_prompt != version:
            return None
        return HallazgosIA(**datos["hallazgos"]), uso_ia
    except (ValueError, KeyError, ValidationError):
        log.warning("Caché inválida para %s; se vuelve a consultar", capture_id)
        return None


def _guardar_cache(capture_id: str, hallazgos: HallazgosIA, uso_ia: UsoIA) -> None:
    CARPETA_CACHE.mkdir(parents=True, exist_ok=True)
    datos = {"hallazgos": hallazgos.model_dump(), "uso_ia": uso_ia.model_dump()}
    (CARPETA_CACHE / f"{capture_id}.json").write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")


def _armar_contenido(captura: CapturaPreparada, features: FeaturesCaptura | None) -> list[dict]:
    contenido: list[dict] = []
    for tipo, ruta in rutas_fotos(captura, features).items():
        if ruta is None:
            contenido.append({"type": "text", "text": f"{TITULOS[tipo]}: no disponible"})
            continue
        contenido.append({"type": "text", "text": TITULOS[tipo]})
        contenido.append(bloque_imagen(ruta))
    contenido.append({"type": "text", "text": describir_captura(captura)})
    return contenido


def analizar_captura(
    captura: CapturaPreparada,
    features: FeaturesCaptura | None = None,
    *,
    usar_cache: bool = True,
    pensamiento: str = PENSAMIENTO,
    esfuerzo: str | None = ESFUERZO,
) -> tuple[HallazgosIA | None, UsoIA | None]:
    """Manda las fotos de una captura al modelo y regresa sus hallazgos y el consumo."""
    version = version_completa(pensamiento, esfuerzo)
    if usar_cache and (en_cache := _leer_cache(captura.capture_id, version)):
        return en_cache

    config = leer_config()
    contenido = _armar_contenido(captura, features)
    opciones = {"output_config": {"effort": esfuerzo}} if esfuerzo else {}
    inicio = time.perf_counter()
    respuesta = None
    intentos = 0
    while intentos < MAX_INTENTOS:
        intentos += 1
        try:
            respuesta = crear_cliente().with_options(timeout=TIMEOUT_S).messages.parse(
                model=config["modelo"],
                max_tokens=MAX_TOKENS[pensamiento],
                thinking=MODOS_PENSAMIENTO[pensamiento],
                system=INSTRUCCIONES,
                messages=[{"role": "user", "content": contenido}],
                output_format=HallazgosIA,
                **opciones,
            )
            break
        except ERRORES_TEMPORALES as error:
            log.warning("%s · intento %s/%s: %s", captura.capture_id, intentos, MAX_INTENTOS, type(error).__name__)
            if intentos < MAX_INTENTOS:
                # El límite por minuto necesita una pausa más larga que un error de red.
                time.sleep(15 * intentos if isinstance(error, anthropic.RateLimitError) else 2**intentos)
        except (anthropic.APIError, ValidationError) as error:
            log.error("%s · error no recuperable: %s: %s", captura.capture_id, type(error).__name__, error)
            break

    if respuesta is None:
        return None, None

    uso_ia = UsoIA(
        input_tokens=respuesta.usage.input_tokens,
        output_tokens=respuesta.usage.output_tokens,
        cache_read_input_tokens=respuesta.usage.cache_read_input_tokens or 0,
        latencia_ms=round((time.perf_counter() - inicio) * 1000),
        intentos=intentos,
        version_prompt=version,
        modelo=config["modelo"],
        stop_reason=respuesta.stop_reason,
    )
    hallazgos = respuesta.parsed_output
    if respuesta.stop_reason != "end_turn" or hallazgos is None:
        log.error("%s · respuesta inutilizable (stop_reason=%s)", captura.capture_id, respuesta.stop_reason)
        return None, uso_ia

    _guardar_cache(captura.capture_id, hallazgos, uso_ia)
    return hallazgos, uso_ia
