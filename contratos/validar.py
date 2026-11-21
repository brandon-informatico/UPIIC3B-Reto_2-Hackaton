"""Valida archivos contra los contratos. Sale con código 1 si algo no cumple.

Uso:
  python contratos/validar.py ejemplos                                   # los 17 ejemplos por situación
  python contratos/validar.py features cache/features.json --capturas data/capturas.json
  python contratos/validar.py salida resultados/resultados.json --capturas data/capturas.json
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from pydantic import ValidationError  # noqa: E402

from contratos import (CapturaPreparada, DecisionInterna, FeaturesCaptura, HallazgosIA,  # noqa: E402
                       RegistroSalida, UsoIA)

MODELOS = {"E1_captura_preparada": CapturaPreparada, "E2_features": FeaturesCaptura,
           "E4_hallazgos_ia": HallazgosIA, "E4_uso_ia": UsoIA,
           "E5_decision_interna": DecisionInterna, "E6_registro_salida": RegistroSalida}


def _errores(modelo, datos):
    try:
        modelo.model_validate(datos)
        return []
    except ValidationError as e:
        return [f"{'.'.join(map(str, x['loc'])) or '(registro)'}: {x['msg']}" for x in e.errors()]


def _ids_esperados(ruta):
    return [c["capture_id"] for c in json.loads(Path(ruta).read_text(encoding="utf-8"))] if ruta else None


def validar_ejemplos(carpeta):
    malos = 0
    for f in sorted(Path(carpeta).glob("*.json")):
        doc = json.loads(f.read_text(encoding="utf-8"))
        errs = [f"{k}: {m}" for k, mod in MODELOS.items() if doc.get(k) is not None for m in _errores(mod, doc[k])]
        malos += bool(errs)
        print(("OK   " if not errs else "FALLA") + f" {f.name}")
        for e in errs[:5]:
            print("      " + e)
    return malos


def validar_registros(registros, modelo, esperados, nombre):
    """registros: lista de dicts con capture_id. Revisa forma, duplicados y faltantes."""
    malos, resumen = 0, Counter()
    for r in registros:
        errs = _errores(modelo, r)
        if errs:
            malos += 1
            for e in errs:
                resumen[e.split(":")[0] + ": " + e.split(":", 1)[1].strip()[:70]] += 1
    ids = [r.get("capture_id") for r in registros]
    dup = [i for i, n in Counter(ids).items() if n > 1]
    falt = sorted(set(esperados) - set(ids)) if esperados is not None else []
    print(f"{nombre}: {len(registros)} registros · válidos {len(registros) - malos} · inválidos {malos}"
          f" · duplicados {len(dup)} · faltantes {len(falt)}")
    for e, n in resumen.most_common(12):
        print(f"   {n:4}× {e}")
    if falt:
        print(f"   faltan: {falt[:10]}{' …' if len(falt) > 10 else ''}")
    return malos + len(dup) + len(falt)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("que", choices=["ejemplos", "features", "salida"])
    ap.add_argument("ruta", nargs="?")
    ap.add_argument("--capturas", help="capturas.json para revisar que no falte ningún capture_id")
    a = ap.parse_args()
    if a.que == "ejemplos":
        malos = validar_ejemplos(a.ruta or Path(__file__).parent / "ejemplos")
    else:
        datos = json.loads(Path(a.ruta).read_text(encoding="utf-8"))
        registros = list(datos.values()) if isinstance(datos, dict) else datos
        modelo = FeaturesCaptura if a.que == "features" else RegistroSalida
        malos = validar_registros(registros, modelo, _ids_esperados(a.capturas), a.ruta)
    sys.exit(1 if malos else 0)


if __name__ == "__main__":
    main()
