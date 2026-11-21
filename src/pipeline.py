"""Pipeline Validat3B (E1 -> E2 -> E3 -> E4 -> E5 -> E6).

Ejecucion: python -m src.pipeline
Las interfaces de IA, datos y modelos pertenecen a contratos/ y a sus equipos.
Nunca se aprueba una captura por el filtro local.
"""
from __future__ import annotations

import argparse
import importlib
import json
import logging
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from contratos.contratos import DecisionInterna, RegistroSalida
from src.motor.integracion import como_captura_preparada, normalizar_con_ingesta
from src.motor.salida import convertir_a_registro, crear_respaldo, explicar

LOG = logging.getLogger(__name__)
MOTIVOS_LOCAL_TERMINALES = frozenset({
    "sin_fotos", "imagen_faltante", "imagen_corrupta"
})


def _funcion(modulos: Iterable[str], nombre: str) -> Callable[..., Any]:
    """Busca una interfaz canonica sin modificar el codigo de companeros."""
    errores: list[str] = []
    for modulo in modulos:
        try:
            objeto = importlib.import_module(modulo)
        except ImportError as exc:
            errores.append(f"{modulo}: {exc}")
            continue
        funcion = getattr(objeto, nombre, None)
        if callable(funcion):
            return funcion
    raise ImportError(f"No se encontro {nombre} en {list(modulos)}. {errores}")


def _valor(objeto: Any, nombre: str, defecto: Any = None) -> Any:
    if isinstance(objeto, dict):
        return objeto.get(nombre, defecto)
    return getattr(objeto, nombre, defecto)


def _id(captura: Any) -> str:
    valor = _valor(captura, "capture_id")
    if valor is None:
        raise ValueError("Captura sin capture_id")
    return str(valor)


def _terminal_local(decision: DecisionInterna) -> bool:
    if _valor(decision, "ruta_decision") != "local":
        return False
    estado = _valor(decision, "decision")
    if estado == "rechazada":
        return True
    return estado == "revision_manual" and _valor(
        decision, "motivo_revision"
    ) in MOTIVOS_LOCAL_TERMINALES


def _convertir_decision(resultado: Any) -> DecisionInterna:
    """Valida E3/E5 contra el contrato oficial."""
    return DecisionInterna.model_validate(resultado)


def _procesar_una(
    captura: Any,
    features: Any,
    decidir: Callable[[Any, Any], Any],
    analizar: Callable[[Any, Any], Any] | None,
) -> tuple[RegistroSalida, dict[str, Any]]:
    capture_id = _id(captura)
    metadatos: dict[str, Any] = {
        "capture_id": capture_id, "llamo_ia": False,
        "tokens_entrada": 0, "tokens_salida": 0,
    }
    hallazgos = None
    try:
        # E3: una decision local segura puede ahorrar una llamada a Azure.
        try:
            previa = _convertir_decision(decidir(features, None))
        except Exception as exc:
            # E3 es opcional mientras se integra: continuamos con IA.
            LOG.warning("E3 no decidio %s (%s)", capture_id, type(exc).__name__)
            previa = None
        if previa is not None and _terminal_local(previa):
            decision = previa
        else:
            # Nunca aprobar con informacion exclusivamente local.
            if analizar is None:
                return crear_respaldo(
                    capture_id, "ia_error", "IA no disponible durante esta ejecucion."
                ), metadatos
            metadatos["llamo_ia"] = True
            try:
                respuesta = analizar(captura, features)
                hallazgos, uso_ia = respuesta
            except Exception as exc:
                LOG.warning("IA fallo para %s: %s", capture_id, type(exc).__name__)
                return crear_respaldo(
                    capture_id, "ia_error", "No fue posible analizar la evidencia con IA."
                ), metadatos
            if hallazgos is None:
                return crear_respaldo(
                    capture_id, "ia_error", "La IA no devolvio hallazgos validos."
                ), metadatos
            if uso_ia is not None:
                uso = uso_ia.model_dump() if hasattr(uso_ia, "model_dump") else dict(uso_ia)
                metadatos["uso_ia"] = uso
                for clave, alias in (
                    ("tokens_entrada", ("input_tokens", "tokens_input", "tokens_entrada")),
                    ("tokens_salida", ("output_tokens", "tokens_output", "tokens_salida")),
                ):
                    for nombre in alias:
                        if isinstance(uso.get(nombre), (int, float)):
                            metadatos[clave] = uso[nombre]
                            break
            decision = _convertir_decision(decidir(features, hallazgos))
            if _valor(decision, "decision") == "aprobada" and _valor(
                decision, "ruta_decision"
            ) != "ia":
                raise ValueError("Aprobada sin ruta_decision=ia")
        registro = convertir_a_registro(decision, explicar(decision, hallazgos))
        metadatos["ruta_decision"] = _valor(decision, "ruta_decision")
        metadatos["decision"] = _valor(decision, "decision")
        return registro, metadatos
    except Exception as exc:
        LOG.exception("Fallo en captura %s: %s", capture_id, exc)
        metadatos["error"] = type(exc).__name__
        return crear_respaldo(
            capture_id, "salida_invalida", "Error interno al procesar la captura."
        ), metadatos


def _normalizar_seguro(capturas: list[Any], normalizar: Callable) -> dict[str, Any]:
    """Ejecuta E2; si falla un lote, intenta aislar la captura danada."""
    try:
        elementos = normalizar(capturas)
        if len(elementos) != len(capturas):
            raise ValueError("E2 devolvio un numero incorrecto de features")
        return {_id(f): f for f in elementos}
    except Exception as exc:
        LOG.warning("Normalizacion del lote fallo (%s); aislando capturas", type(exc).__name__)
        encontrados: dict[str, Any] = {}
        for captura in capturas:
            try:
                elementos = normalizar([captura])
                if len(elementos) != 1:
                    raise ValueError("E2 debe devolver una feature por captura")
                encontrados[_id(captura)] = elementos[0]
            except Exception:
                LOG.exception("E2 fallo en %s", _id(captura))
        return encontrados


def ejecutar(ruta_capturas: Path, ruta_salida: Path, *, sin_ia: bool = False,
             hilos: int = 2) -> dict[str, int]:
    cargar = _funcion(("src.datos.cargador",), "cargar_capturas")
    try:
        normalizar = _funcion(
            ("src.datos.normalizar", "src.datos.limpieza", "src.datos.imagenes"),
            "normalizar",
        )
    except ImportError:
        # Hoy Copka entrega la ingesta (src/datos/ingesta.py), no normalizar(); se adapta aqui.
        LOG.info("E2: usando la ingesta de Copka via src/motor/integracion.py")
        normalizar = normalizar_con_ingesta
    decidir = _funcion(("src.motor.decisiones",), "decidir")
    analizar = None
    if not sin_ia:
        try:
            analizar_ia = _funcion(
                ("src.ia.analizar", "src.ia.cliente", "src.ia.analisis"),
                "analizar_captura",
            )

            def analizar(captura: Any, features: Any) -> Any:
                # src.ia.analizar espera CapturaPreparada; el cargador entrega diccionarios.
                return analizar_ia(como_captura_preparada(captura), features)
        except ImportError:
            LOG.warning("E4 no disponible: casos sin decision local iran a revision")
    capturas = list(cargar(ruta_capturas))
    features_por_id = _normalizar_seguro(capturas, normalizar)
    registros: list[RegistroSalida] = []
    ruta_log = Path("logs") / f"corrida_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}.jsonl"
    ruta_log.parent.mkdir(parents=True, exist_ok=True)
    def una(captura: Any) -> tuple[RegistroSalida, dict[str, Any]]:
        """Nunca lanza: un error en una captura se vuelve su registro de respaldo."""
        capture_id = _id(captura)  # el cargador garantiza capture_id; sin el no hay registro posible
        try:
            features = features_por_id.get(capture_id)
            if features is None:
                registro = crear_respaldo(
                    capture_id, "salida_invalida", "No fue posible normalizar la captura."
                )
                return registro, {"capture_id": capture_id, "llamo_ia": False, "error": "normalizacion"}
            return _procesar_una(captura, features, decidir, analizar)
        except Exception as exc:
            LOG.exception("Fallo inesperado en %s", capture_id)
            registro = crear_respaldo(capture_id, "salida_invalida", "Error interno al procesar la captura.")
            return registro, {"capture_id": capture_id, "llamo_ia": False, "error": type(exc).__name__}

    # Llamadas a la IA en paralelo (cuidar el limite de tokens por minuto); el orden se conserva.
    with ThreadPoolExecutor(max_workers=max(1, hilos)) as ejecutor:
        procesadas = list(ejecutor.map(una, capturas))
    with ruta_log.open("w", encoding="utf-8") as log:
        for registro, metadata in procesadas:
            registros.append(RegistroSalida.model_validate(registro))
            log.write(json.dumps(metadata, ensure_ascii=False, default=str) + "\n")
    if len(registros) != len(capturas):
        raise AssertionError("Se perdieron capturas durante la corrida")
    ruta_salida.parent.mkdir(parents=True, exist_ok=True)
    archivo_temporal = ruta_salida.with_suffix(ruta_salida.suffix + ".tmp")
    archivo_temporal.write_text(
        json.dumps([r.model_dump(mode="json") for r in registros],
                   ensure_ascii=False, indent=2), encoding="utf-8"
    )
    archivo_temporal.replace(ruta_salida)
    resumen = Counter(str(_valor(r, "decision", "desconocida")) for r in registros)
    LOG.info("Capturas=%d, decisiones=%s, salida=%s, log=%s",
             len(capturas), dict(resumen), ruta_salida, ruta_log)
    return dict(resumen)


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline Validat3B")
    parser.add_argument("--capturas", type=Path, default=Path("data/capturas.json"))
    parser.add_argument("--salida", type=Path, default=Path("resultados/resultados.json"))
    parser.add_argument("--sin-ia", action="store_true", help="Prueba sin Azure; no aprueba capturas")
    parser.add_argument("--hilos", type=int, default=2, help="capturas en paralelo (limite de tokens/minuto)")
    argumentos = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ejecutar(argumentos.capturas, argumentos.salida, sin_ia=argumentos.sin_ia, hilos=argumentos.hilos)


if __name__ == "__main__":
    main()
