"""Genera datos FICTICIOS para probar el dashboard sin depender de los demás módulos.

    python dashboard/generar_ficticios.py

Crea en ejemplos/:
  resultados_ficticios.json  -> formato oficial de salida (lista de capturas)
  decisiones_ficticias.jsonl -> decisión interna (E5): motivo_revision, tipo_precio, ruta, fallas
  capturas_ficticias.json    -> metadatos mínimos (precio capturado, cadena, producto)
  metricas_ficticias.json    -> contrato PROPUESTO para el reporte de Ale

Nada de esto es dato real del reto. Los identificadores son CAP-8xxxxx.
Tiene la forma de contratos.py (E1, E5 y E6) y 100 capturas para probar volumen:
    python dashboard/servidor.py --resultados ejemplos/resultados_ficticios.json
"""
import json
import random
from collections import Counter
from datetime import datetime
from pathlib import Path

random.seed(3)
RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "ejemplos"

CADENAS = ["Soriana", "Neto", "Chedraui", "Bodega Aurrera", "Walmart", "Bara"]
PRODUCTOS = [
    ("Atún en agua 140 g", 18.5), ("Pasta moñito 200 g", 11.0), ("Pasta estrella 200 g", 11.0),
    ("Leche entera 1 L", 26.9), ("Frijol negro 900 g", 34.5), ("Aceite vegetal 1 L", 42.5),
    ("Galletas María 170 g", 15.9), ("Detergente en polvo 1 kg", 38.0), ("Arroz 1 kg", 29.9),
    ("Café soluble 120 g", 64.0), ("Papel higiénico 4 rollos", 32.5), ("Sardina en tomate 425 g", 27.0),
]
VALIDACION_OK = {"tienda_fachada": "ok", "producto": "ok", "codigo_barras": "ok", "evidencia_precio": "ok"}

# reason_code provisionales de contratos.py: (código, frente, validación interna que falla, explicación, peso)
RECHAZOS = [
    ("CAPTURA_LEJANA", "B_calidad", "producto", "El producto aparece entre muchos en el anaquel; no se puede ligar a la etiqueta.", 18),
    ("IMAGEN_BORROSA", "B_calidad", "evidencia_precio", "La etiqueta está desenfocada y el precio no es legible.", 11),
    ("DESCRIPCION_INCOMPLETA", "A_identidad", "producto", "La descripción de la etiqueta está incompleta y no permite confirmar el producto.", 5),
    ("PRODUCTO_NO_COINCIDE", "A_identidad", "producto", "El producto de la foto es de otra marca que la esperada.", 3),
    ("SIN_ETIQUETA_PRECIO", "C_precio", "evidencia_precio", "La foto de etiqueta no muestra ninguna etiqueta de precio.", 2),
]
# motivo_revision de contratos.py: (motivo, validación interna no determinable, explicación, ruta)
REVISIONES = [
    ("dos_precios", "evidencia_precio", "La etiqueta muestra precio regular y de oferta; requiere revisión.", "ia"),
    ("duda_identidad", "producto", "No se puede confirmar la presentación del producto (g vs ml).", "ia"),
    ("confianza_insuficiente", None, "La evidencia se ve bien pero la confianza no alcanza para aprobar.", "ia"),
    ("precio_distinto_al_capturado", "evidencia_precio", "El precio de la etiqueta difiere del capturado.", "ia"),
]


def tipo_precio():
    return random.choices(["regular", "oferta", "volumen"], [80, 15, 5])[0]


def crear():
    """Devuelve (capturas E1, resultados E6, decisiones E5, esperados)."""
    capturas, resultados, decisiones, esperados = [], [], [], []
    reales = ["aprobada"] * 33 + ["rechazada"] * 34 + ["revision_manual"] * 33
    random.shuffle(reales)
    pesos = [r[4] for r in RECHAZOS]

    for i, real in enumerate(reales, start=1):
        cid = f"CAP-8{i:05d}"  # cumple ^CAP-\d+$; la serie 8xxxxx es ficticia
        nombre, precio = random.choice(PRODUCTOS)
        precio = round(precio * random.uniform(0.9, 1.15), 1)
        cadena = random.choice(CADENAS)
        codigo = "750" + "".join(random.choice("0123456789") for _ in range(10))
        capturas.append({"capture_id": cid, "capture_store_name": cadena, "product_name": nombre,
                         "capture_price": precio, "capture_barcode": codigo})

        r = random.random()
        if real == "aprobada":
            decision = "aprobada" if r < 0.70 else ("revision_manual" if r < 0.97 else "rechazada")
        elif real == "rechazada":
            decision = "rechazada" if r < 0.78 else ("revision_manual" if r < 0.995 else "aprobada")
        else:
            decision = "revision_manual" if r < 0.75 else ("rechazada" if r < 0.98 else "aprobada")

        val = dict(VALIDACION_OK)
        fallas, reason, motivo, ruta = [], None, None, "ia"
        precio_det, tp = precio, tipo_precio()
        if decision == "aprobada":
            p_valida = round(random.uniform(0.91, 0.99), 3)
            explicacion = "Producto, etiqueta y precio coinciden con lo esperado."
        elif decision == "rechazada":
            reason, frente, campo, explicacion, _ = random.choices(RECHAZOS, pesos)[0]
            fallas = [{"reason_code": reason, "frente": frente, "fuente": "ia", "detalle": campo + "=falla"}]
            val[campo] = "falla"
            p_valida = round(random.uniform(0.03, 0.30), 3)
            if reason in ("IMAGEN_BORROSA", "SIN_ETIQUETA_PRECIO"):
                precio_det, tp = None, None
        else:
            motivo, campo, explicacion, ruta = random.choice(REVISIONES)
            if campo:
                val[campo] = "no_determinable"
            p_valida = round(random.uniform(0.40, 0.88), 3)
            if motivo == "precio_distinto_al_capturado":
                precio_det = round(precio * 1.4, 1)

        conf = p_valida if decision == "aprobada" else 1 - p_valida if decision == "rechazada" else max(p_valida, 1 - p_valida)
        decisiones.append({"capture_id": cid, "decision": decision, "p_valida": p_valida, "fallas": fallas,
                           "reason_code": reason, "motivo_revision": motivo, "validaciones": val,
                           "precio_detectado": precio_det, "tipo_precio": tp,
                           "codigo_barras_detectado": None, "ruta_decision": ruta})
        resultados.append({
            "capture_id": cid, "decision": decision, "confidence_score": round(conf, 3),
            "reason_code": reason,
            "validaciones": {k: ("ok" if v == "ok" else "falla") for k, v in val.items()},  # igual que a_oficial()
            "precio_detectado": precio_det, "codigo_barras_detectado": None, "explicacion": explicacion,
        })
        esperados.append(real)

    # Una captura con error de IA: respaldo_revision() → todo "falla", confianza 0
    cid = resultados[-1]["capture_id"]
    resultados[-1] = {"capture_id": cid, "decision": "revision_manual", "confidence_score": 0.0, "reason_code": None,
                      "validaciones": {k: "falla" for k in VALIDACION_OK}, "precio_detectado": None,
                      "codigo_barras_detectado": None,
                      "explicacion": "No se obtuvo análisis automático; se envía a revisión manual."}
    decisiones[-1].update({"decision": "revision_manual", "p_valida": 0.5, "fallas": [], "reason_code": None,
                           "motivo_revision": "ia_error", "precio_detectado": None, "tipo_precio": None,
                           "validaciones": {k: "no_determinable" for k in VALIDACION_OK}, "ruta_decision": "error"})
    return capturas, resultados, decisiones, esperados


COSTO = {("aprobada", "aprobada"): 0, ("rechazada", "rechazada"): 0, ("revision_manual", "revision_manual"): 0}


def costo(real, pred):
    if real == pred:
        return 0
    if pred == "revision_manual":
        return 1
    if pred == "rechazada" and real == "aprobada":
        return 3
    if pred == "aprobada" and real != "aprobada":
        return 10
    return 1 if real == "revision_manual" else 0  # rechazada vs revisión: supuesto, confirmar con comité


def metricas(resultados, esperados):
    clases = ["aprobada", "rechazada", "revision_manual"]
    matriz = {r: {p: 0 for p in clases} for r in clases}
    desglose = Counter()
    total_costo = 0
    for res, real in zip(resultados, esperados):
        pred = res["decision"]
        matriz[real][pred] += 1
        c = costo(real, pred)
        total_costo += c
        clave = ("correctas" if c == 0 and real == pred else
                 "revision_manual" if pred == "revision_manual" else
                 "rechazo_valida" if pred == "rechazada" and real == "aprobada" else
                 "aprobacion_invalida" if pred == "aprobada" else "otros")
        desglose[clave] += 1
    aprobadas_pred = sum(matriz[r]["aprobada"] for r in clases)
    precision = matriz["aprobada"]["aprobada"] / aprobadas_pred if aprobadas_pred else None
    n = len(resultados)
    tokens_entrada = 188_000 + random.randint(-5000, 5000)
    tokens_salida = n * 210

    def tanda(nombre, idx):
        sub = [(resultados[i], esperados[i]) for i in idx]
        ap = [r for r, e in sub if r["decision"] == "aprobada"]
        ok = [r for r, e in sub if r["decision"] == "aprobada" and e == "aprobada"]
        return {"tanda": nombre, "total": len(sub),
                "costo": sum(costo(e, r["decision"]) for r, e in sub),
                "precision_aprobaciones": round(len(ok) / len(ap), 4) if ap else None}

    mitad = n // 2
    return {
        "ficticio": True,
        "generado": datetime.now().isoformat(timespec="seconds"),
        "conjunto": "desarrollo (ficticio)",
        "total": n,
        "umbrales": {"precision_aprobaciones_min": 0.97, "json_valido_min": 0.99},
        "precision_aprobaciones": round(precision, 4) if precision is not None else None,
        "json_validos_pct": 1.0,
        "costo_total": total_costo,
        "costo_por_captura": round(total_costo / n, 3),
        "costo_desglose": {
            "correctas": {"n": desglose["correctas"], "costo_unitario": 0},
            "revision_manual": {"n": desglose["revision_manual"], "costo_unitario": 1},
            "rechazo_valida": {"n": desglose["rechazo_valida"], "costo_unitario": 3},
            "aprobacion_invalida": {"n": desglose["aprobacion_invalida"], "costo_unitario": 10},
        },
        "matriz_confusion": matriz,
        "calidad_dato": {"reason_code_acierto": 0.81, "precio_acierto": 0.88, "tipo_precio_acierto": 0.9},
        "tokens": {"entrada": tokens_entrada, "salida": tokens_salida,
                   "total": tokens_entrada + tokens_salida,
                   "por_captura": round((tokens_entrada + tokens_salida) / n)},
        "llamadas": {"ia": 125, "evitadas": 175,
                     "imagenes_enviadas": 225, "imagenes_evitadas": 75,
                     "nota": "75 fachadas repetidas se analizan una sola vez (25 únicas)"},
        "tiempo_total_s": 412,
        "por_tanda": [tanda("Tanda noche", range(0, mitad)), tanda("Tanda día", range(mitad, n))],
    }


def main():
    SALIDA.mkdir(exist_ok=True)
    capturas, resultados, decisiones, esperados = crear()
    (SALIDA / "decisiones_ficticias.jsonl").write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in decisiones) + "\n", encoding="utf-8")
    (SALIDA / "capturas_ficticias.json").write_text(json.dumps(capturas, ensure_ascii=False, indent=2), encoding="utf-8")
    (SALIDA / "resultados_ficticios.json").write_text(json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8")
    (SALIDA / "metricas_ficticias.json").write_text(json.dumps(metricas(resultados, esperados), ensure_ascii=False, indent=2), encoding="utf-8")
    print(Counter(r["decision"] for r in resultados))
    print("Listo: ejemplos/resultados_ficticios.json, capturas_ficticias.json, metricas_ficticias.json")


if __name__ == "__main__":
    main()
