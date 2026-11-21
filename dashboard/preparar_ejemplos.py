"""Convierte los 17 ejemplos de contratos/ejemplos/ en archivos que lee el dashboard.

    python dashboard/preparar_ejemplos.py --contratos contratos/ejemplos
    python dashboard/preparar_ejemplos.py --contratos "D:/Escritorio/reto 2/contratos/contratos/ejemplos"

Escribe en ejemplos/ (misma forma que producirá el motor real):
  resultados_ejemplo.json    <- E6_registro_salida   (lo que entrega Pat en resultados/resultados.json)
  decisiones_ejemplo.jsonl   <- E5_decision_interna  (lo que Pat deja en logs/corrida_<id>.jsonl)
  capturas_ejemplo.json      <- E1_captura_preparada (precio capturado, tienda, producto)
  metricas_ejemplo.json      <- métricas calculadas con los 17 (decisión esperada = la de la situación)

Los tokens y llamadas salen de E4_uso_ia y las fachadas repetidas de E2_features de cada ejemplo.
"""
import argparse
import json
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "ejemplos"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--contratos", default=str(RAIZ / "contratos" / "ejemplos"),
                    help="carpeta con los 01_…json a 17_…json")
    a = ap.parse_args()
    carpeta = Path(a.contratos)
    archivos = sorted(carpeta.glob("*.json"))
    if not archivos:
        raise SystemExit(f"No encontré ejemplos en {carpeta}")

    resultados, decisiones, capturas = [], [], []
    tok_in = tok_out = tok_cache = llamadas = img_env = img_evit = 0
    for f in archivos:
        d = json.loads(f.read_text(encoding="utf-8"))
        e1, e2, e5, e6, uso = (d.get(k) for k in ("E1_captura_preparada", "E2_features",
                                                  "E5_decision_interna", "E6_registro_salida", "E4_uso_ia"))
        if not e6:
            continue
        resultados.append(e6)
        if e5:
            decisiones.append({**e5, "_situacion": d.get("situacion"), "_descripcion": d.get("descripcion")})
        if e1:
            capturas.append(e1)
        if uso:
            llamadas += 1
            tok_in += uso.get("input_tokens", 0)
            tok_out += uso.get("output_tokens", 0)
            tok_cache += uso.get("cache_read_input_tokens", 0)
        for tipo in ("facade", "product", "shelf"):
            foto = (e2 or {}).get(tipo)
            if not foto:
                continue
            if tipo == "facade" and foto.get("repetida"):
                img_evit += 1
            elif uso:
                img_env += 1

    n = len(resultados)
    clases = ["aprobada", "rechazada", "revision_manual"]
    matriz = {r: {p: 0 for p in clases} for r in clases}
    for r in resultados:  # en los ejemplos, la decisión esperada es la de la situación
        matriz[r["decision"]][r["decision"]] += 1
    cuenta = {c: sum(1 for r in resultados if r["decision"] == c) for c in clases}
    metricas = {
        "ejemplo": True,
        "generado": datetime.now().isoformat(timespec="seconds"),
        "conjunto": f"contratos/ejemplos ({n} situaciones)",
        "total": n,
        "umbrales": {"precision_aprobaciones_min": 0.97, "json_valido_min": 0.99},
        "precision_aprobaciones": 1.0 if cuenta["aprobada"] else None,
        "json_validos_pct": 1.0,
        "costo_total": 0,
        "costo_por_captura": 0.0,
        "costo_desglose": {
            "correctas": {"n": n, "costo_unitario": 0},
            "revision_manual": {"n": 0, "costo_unitario": 1},
            "rechazo_valida": {"n": 0, "costo_unitario": 3},
            "aprobacion_invalida": {"n": 0, "costo_unitario": 10},
        },
        "matriz_confusion": matriz,
        "tokens": {"entrada": tok_in, "salida": tok_out, "cache_lectura": tok_cache,
                   "total": tok_in + tok_out, "por_captura": round((tok_in + tok_out) / n) if n else 0},
        "llamadas": {"ia": llamadas, "evitadas": n - llamadas,
                     "imagenes_enviadas": img_env, "imagenes_evitadas": img_evit,
                     "nota": "fachadas repetidas que no se vuelven a enviar a la IA"},
        "nota": "Métricas de ejemplo: cada situación trae su decisión correcta, por eso no hay errores.",
    }

    SALIDA.mkdir(exist_ok=True)
    (SALIDA / "resultados_ejemplo.json").write_text(json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8")
    (SALIDA / "decisiones_ejemplo.jsonl").write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in decisiones) + "\n", encoding="utf-8")
    (SALIDA / "capturas_ejemplo.json").write_text(json.dumps(capturas, ensure_ascii=False, indent=2), encoding="utf-8")
    (SALIDA / "metricas_ejemplo.json").write_text(json.dumps(metricas, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{n} ejemplos → ejemplos/resultados_ejemplo.json, decisiones_ejemplo.jsonl, "
          f"capturas_ejemplo.json, metricas_ejemplo.json  {cuenta}")


if __name__ == "__main__":
    main()
