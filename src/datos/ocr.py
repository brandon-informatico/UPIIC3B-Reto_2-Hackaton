"""Lectura local de texto (OCR) en la etiqueta de precio, sin tokens.

Usa RapidOCR (modelos ONNX incluidos en el paquete; corre en CPU, sin servicios externos).
De la **etiqueta** extrae: precio, tipo de precio (regular/promocion), descripción y su parecido con el producto
esperado, contenido (450 g, 1.1 L) y un recorte de la etiqueta para mandarle a la IA menos píxeles.

Medido en desarrollo (100 capturas): el OCR de la foto de producto NO sirve para detectar capturas lejanas
(AUC ~0.5) y duplicaba el tiempo, por eso no se hace; el encuadre lo juzga la IA.

Todo es una pista para el motor y la IA, no una decisión: si el OCR no lee nada, los campos quedan en ``None``.
"""
from __future__ import annotations

import logging
import re
import threading
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from src.datos.imagenes import _guardar_jpeg, leer_imagen

try:
    from rapidocr_onnxruntime import RapidOCR
except ImportError:  # pragma: no cover
    RapidOCR = None

log = logging.getLogger(__name__)

_MOTOR = None
_CANDADO = threading.Lock()
_PROMOCION = re.compile(r"\b(oferta|promo\w*|ahorr\w*|descuento|especial|rebaja|llevat\w*|lleve|\d\s*x\s*\$?\d|"
                        r"\d+\s*%|2x1|3x2|segunda|precio\s*bajo)\b")
_UNITARIO = re.compile(r"(precio\s*(por|x)?\s*(unidad|unitario|kg|kilo|litro|lt|gramo|g\b|ml)|p\.?\s*u\.?\b|"
                       r"\$\s*\d+[.,]\d+\s*(por|x|/)\s*(kg|g|gr|grs|l|lt|lts|ml|pz|pza|pieza|unidad|100))")
_CONTENIDO = re.compile(r"(\d+(?:[.,]\d+)?)\s*(kgs?|kilos?|grs?|gramos?|g|mls?|mililitros?|lts?|litros?|l)\b")
_DINERO = re.compile(r"\$\s*(\d{1,4}(?:[.,]\d{1,2})?)")
_NUMERO = re.compile(r"(?<![\d.,])(\d{1,4})(?:[.,](\d{1,2}))?(?![\d])")
UNIDADES = {"kg": ("g", 1000), "kgs": ("g", 1000), "kilo": ("g", 1000), "kilos": ("g", 1000),
            "g": ("g", 1), "gr": ("g", 1), "grs": ("g", 1), "gramo": ("g", 1), "gramos": ("g", 1),
            "ml": ("ml", 1), "mls": ("ml", 1), "mililitro": ("ml", 1), "mililitros": ("ml", 1),
            "l": ("ml", 1000), "lt": ("ml", 1000), "lts": ("ml", 1000), "litro": ("ml", 1000), "litros": ("ml", 1000)}
TOLERANCIA_DESCRIPCION = 0.0  # el recorte no puede perder descripción respecto a la foto completa
MARGEN_ZONA = {"ancho": 5.0, "alto": 3.5}  # en múltiplos de la altura del precio
PALABRAS_VACIAS = {"de", "del", "la", "el", "los", "las", "con", "para", "en", "y", "sabor", "total", "tipo", "pza"}


def disponible() -> bool:
    return RapidOCR is not None


def _motor():
    """Una sola instancia compartida por todos los hilos.

    Medido: compartida con 6 hilos ≈ 0.47 s por etiqueta y resultados idénticos a 1 hilo (48/48); una instancia por
    hilo o procesos separados son más lentos porque ONNX Runtime ya usa todos los núcleos en cada llamada.
    """
    global _MOTOR
    if _MOTOR is None:
        with _CANDADO:
            if _MOTOR is None:
                _MOTOR = RapidOCR()
    return _MOTOR


def sin_acentos(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in texto if not unicodedata.combining(c))


def leer_texto(img: np.ndarray, confianza_min: float = 0.5) -> list[dict[str, Any]]:
    """Cajas de texto: {"texto", "conf", "x0", "y0", "x1", "y1", "alto"} en pixeles de ``img``."""
    if RapidOCR is None or img is None:
        return []
    try:
        resultado, _ = _motor()(img)
    except Exception as error:  # el OCR nunca debe tumbar la captura
        log.debug("OCR falló: %s", error)
        return []
    cajas = []
    for puntos, texto, conf in resultado or []:
        conf = float(conf)
        if conf < confianza_min or not str(texto).strip():
            continue
        xs, ys = [p[0] for p in puntos], [p[1] for p in puntos]
        cajas.append({"texto": str(texto).strip(), "conf": round(conf, 3), "x0": min(xs), "y0": min(ys),
                      "x1": max(xs), "y1": max(ys), "alto": max(ys) - min(ys)})
    return cajas


# ───────────────────────── contenido ─────────────────────────
def contenido_de_texto(texto: str) -> tuple[float, str] | None:
    """'Arroz 1 KG' → (1000.0, 'g'); '360 ml' → (360.0, 'ml'). La primera mención gana."""
    for cantidad, unidad in _CONTENIDO.findall(sin_acentos(texto)):
        base = UNIDADES.get(unidad)
        if base:
            return round(float(cantidad.replace(",", ".")) * base[1], 2), base[0]
    return None


def contenido_esperado(captura: dict[str, Any]) -> tuple[float, str] | None:
    """Contenido del catálogo (unit_quantity_product + unit_product); si no, el que diga product_name."""
    cantidad, unidad = captura.get("unit_quantity_product"), sin_acentos(str(captura.get("unit_product") or ""))
    if cantidad and unidad in UNIDADES:
        base = UNIDADES[unidad]
        return round(float(cantidad) * base[1], 2), base[0]
    return contenido_de_texto(str(captura.get("product_name") or ""))


def comparar_contenido(esperado: tuple[float, str] | None, leido: tuple[float, str] | None) -> str:
    """si / no / no_determinable. Gramos contra mililitros no se puede decidir (ej. 360 g vs 360 ml)."""
    if not esperado or not leido or esperado[1] != leido[1]:
        return "no_determinable"
    return "si" if abs(esperado[0] - leido[0]) <= max(1.0, 0.03 * esperado[0]) else "no"


# ───────────────────────── descripción ─────────────────────────
def _palabras(texto: str) -> list[str]:
    return [p for p in re.findall(r"[a-z]{3,}", sin_acentos(texto)) if p not in PALABRAS_VACIAS]


def similitud_descripcion(texto_etiqueta: str, captura: dict[str, Any]) -> float | None:
    """Fracción de palabras del producto esperado (nombre + marca) que aparecen en la etiqueta.

    Tolera abreviaturas de etiqueta ("SERV" por servilletas, "GV" no) y errores de OCR leves.
    """
    esperadas = _palabras(f"{captura.get('product_name') or ''} {captura.get('capture_brand') or ''}")
    leidas = _palabras(texto_etiqueta)
    if not esperadas or not leidas:
        return None

    def aparece(palabra: str) -> bool:
        return any(leida.startswith(palabra[:4]) and len(leida) >= 3 or palabra.startswith(leida) and len(leida) >= 4
                   or SequenceMatcher(None, palabra, leida).ratio() >= 0.8 for leida in leidas)
    return round(sum(aparece(p) for p in esperadas) / len(esperadas), 3)


# ───────────────────────── precio ─────────────────────────
def _candidatos_precio(caja: dict[str, Any], vecinas: list[dict[str, Any]]) -> list[float]:
    texto = caja["texto"].replace(" ", "").replace("S", "$").replace("O", "0").replace("o", "0")
    dinero = _DINERO.search(texto)
    coincidencia = dinero or _NUMERO.search(texto)
    if not coincidencia:
        return []
    bruto = coincidencia.group(1).replace(",", ".")
    if "." in bruto:
        return [float(bruto)]
    entero = int(bruto)
    # centavos en superíndice: caja pequeña a la derecha con 2 dígitos ("$25" + "00")
    for v in vecinas:
        if (v is not caja and re.fullmatch(r"\d{2}", v["texto"].strip()) and v["x0"] >= caja["x1"] - 0.2 * caja["alto"]
                and v["x0"] - caja["x1"] < caja["alto"] and v["alto"] < 0.8 * caja["alto"]
                and abs(v["y0"] - caja["y0"]) < caja["alto"]):
            return [entero + int(v["texto"]) / 100]
    candidatos = [float(entero)]
    if len(bruto) >= 3:  # "2500" puede ser $25.00 con centavos pegados
        candidatos.append(entero / 100)
    return candidatos


_NO_ES_PRECIO = re.compile(r"\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}|\d{5,}|\d+\s*-\s*\d+\s*-\s*\d+")


def _es_candidata_precio(caja: dict[str, Any]) -> bool:
    """Descarta fechas, códigos (5+ dígitos seguidos), claves tipo 1200-0003-0007 y contenidos (450 GR)."""
    texto = caja["texto"]
    if not re.search(r"\d", texto) or _NO_ES_PRECIO.search(texto.replace(" ", "")):
        return False
    return "$" in texto or not _CONTENIDO.search(sin_acentos(texto))


def leer_precio(cajas: list[dict[str, Any]], captura: dict[str, Any]) -> tuple[float | None, list[float]]:
    """Precio principal = número más grande de la etiqueta (las cajas con "$" pesan más). Si hay ambigüedad
    ("2500" → 2500 o 25.00) se elige el candidato dentro del rango de referencia del catálogo; nunca se usa el
    precio capturado para elegir."""
    con_numero = sorted((c for c in cajas if _es_candidata_precio(c)),
                        key=lambda c: c["alto"] * (1.5 if "$" in c["texto"] else 1.0), reverse=True)
    minimo = captura.get("min_product_price") or 0
    maximo = captura.get("max_product_price") or 0
    todos: list[float] = []
    for caja in con_numero[:3]:
        candidatos = [v for v in _candidatos_precio(caja, cajas) if 0 < v < 10000]
        todos.extend(candidatos)
        if not candidatos:
            continue
        if maximo > 0:
            en_rango = [v for v in candidatos if minimo * 0.5 <= v <= maximo * 1.5]
            if en_rango:
                return round(en_rango[0], 2), sorted(set(todos))
        if caja is con_numero[0]:
            return round(candidatos[-1] if len(candidatos) > 1 and candidatos[0] > 999 else candidatos[0], 2), \
                sorted(set(todos))
    return None, sorted(set(todos))


# ───────────────────────── recorte ─────────────────────────
def zona_etiqueta(cajas: list[dict[str, Any]], ancho: int, alto: int
                  ) -> tuple[tuple[int, int, int, int], list[dict[str, Any]]] | None:
    """Rectángulo alrededor del precio (caja de precio más grande) y del texto cercano (descripción).
    Regresa (x0, y0, x1, y1) y las cajas de texto que quedan dentro."""
    numericas = [c for c in cajas if _es_candidata_precio(c)]
    if not numericas:
        return None
    precio = max(numericas, key=lambda c: c["alto"] * (1.5 if "$" in c["texto"] else 1.0))
    h = max(precio["alto"], 1.0)
    mx, my = MARGEN_ZONA["ancho"] * h, MARGEN_ZONA["alto"] * h
    zona = [precio["x0"] - mx, precio["y0"] - my, precio["x1"] + mx, precio["y1"] + my]
    dentro = [c for c in cajas if zona[0] <= (c["x0"] + c["x1"]) / 2 <= zona[2]
              and zona[1] <= (c["y0"] + c["y1"]) / 2 <= zona[3]]
    x0, y0 = min(c["x0"] for c in dentro), min(c["y0"] for c in dentro)
    x1, y1 = max(c["x1"] for c in dentro), max(c["y1"] for c in dentro)
    margen = 0.5 * h
    caja = (max(0, int(x0 - margen)), max(0, int(y0 - margen)), min(ancho, int(x1 + margen)), min(alto, int(y1 + margen)))
    return caja, dentro


# ───────────────────────── análisis de la etiqueta ─────────────────────────
def analizar_etiqueta(img: np.ndarray, captura: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Lo que se puede leer localmente de la foto de etiqueta. Todo es pista, no decisión."""
    cajas = leer_texto(img)
    texto = " ".join(c["texto"] for c in sorted(cajas, key=lambda c: (round(c["y0"] / 20), c["x0"])))
    plano = sin_acentos(texto)
    precio, candidatos = leer_precio(cajas, captura)
    leido = contenido_de_texto(texto)
    esperado = contenido_esperado(captura)
    capturado = captura.get("capture_price")
    return {
        "texto_legible": any(c["conf"] >= 0.8 and len(c["texto"]) >= 3 for c in cajas),
        "n_cajas_texto": len(cajas),
        "precio_etiqueta": precio,
        "precios_candidatos": candidatos[:6],
        "precio_coincide_captura": None if precio is None or capturado is None else abs(precio - capturado) < 0.01,
        "tipo_precio": None if precio is None else ("promocion" if _PROMOCION.search(plano) else "regular"),
        # El precio unitario suele ser letra muy pequeña: el OCR local casi nunca lo lee en fotos de 960 px.
        # Por eso solo se afirma cuando se encuentra (True); si no, None = "no determinado", nunca False.
        "precio_unitario_visible": True if _UNITARIO.search(plano) else None,
        "descripcion_texto": texto[:200],
        "descripcion_similitud": similitud_descripcion(texto, captura),
        "contenido_etiqueta": None if leido is None else {"cantidad": leido[0], "unidad": leido[1]},
        "contenido_esperado": None if esperado is None else {"cantidad": esperado[0], "unidad": esperado[1]},
        "contenido_coincide": comparar_contenido(esperado, leido),
    }, cajas


def _recortar(img_analizada: np.ndarray, original: np.ndarray | None, zona: tuple[int, int, int, int],
              lado_max: int) -> np.ndarray:
    """Recorta de la foto original (más resolución) si existe; si no, de la copia analizada."""
    fuente, escala = img_analizada, 1.0
    if original is not None:
        fuente, escala = original, original.shape[1] / img_analizada.shape[1]
    x0, y0, x1, y1 = (round(v * escala) for v in zona)
    recorte = fuente[y0:y1, x0:x1]
    factor = min(1.0, lado_max / max(recorte.shape[:2]))
    if factor < 1.0:
        recorte = cv2.resize(recorte, None, fx=factor, fy=factor, interpolation=cv2.INTER_AREA)
    return recorte


def analizar_ocr(captura: dict[str, Any], imagenes: dict[str, Path | None], ruta_cache: Path,
                 originales: dict[str, Path | None] | None = None, lado_recorte: int = 640,
                 hacer_recorte: bool = True) -> dict[str, Any]:
    """OCR de la etiqueta de una captura (sobre la copia normalizada). Nunca lanza excepción.

    Regresa {"disponible", "etiqueta": dict|None, "recorte_etiqueta": Path|None, "recorte_confiable": bool,
             "tokens_recorte_aprox": int|None}.
    ``recorte_confiable`` = al volver a leer el recorte sale el mismo precio y al menos la misma descripción que en
    la foto completa; solo entonces conviene mandarle a la IA el recorte en vez de la foto completa.
    """
    salida: dict[str, Any] = {"disponible": disponible(), "etiqueta": None, "recorte_etiqueta": None,
                              "recorte_confiable": False, "tokens_recorte_aprox": None}
    if not disponible() or not imagenes.get("shelf"):
        return salida
    capture_id = str(captura.get("capture_id", "SIN-ID"))
    try:
        img = leer_imagen(imagenes["shelf"])
        if img is None:
            return salida
        etiqueta, cajas = analizar_etiqueta(img, captura)
        salida["etiqueta"] = etiqueta
        if not hacer_recorte:
            return salida
        resultado = zona_etiqueta(cajas, img.shape[1], img.shape[0])
        if not resultado:
            return salida
        zona, dentro = resultado
        if (zona[2] - zona[0]) < 40 or (zona[3] - zona[1]) < 20:
            return salida
        original = leer_imagen(originales["shelf"]) if originales and originales.get("shelf") else None
        recorte = _recortar(img, original, zona, lado_recorte)
        destino = Path(ruta_cache) / "normalizadas" / "shelf_recorte" / f"{capture_id}_shelf.jpg"
        _guardar_jpeg(recorte, destino, 90)
        salida["recorte_etiqueta"] = destino
        salida["tokens_recorte_aprox"] = round(recorte.shape[0] * recorte.shape[1] / 750)
        # Verificación: se vuelve a leer el recorte. Solo es confiable si reproduce el mismo precio y al menos la
        # misma descripción que la foto completa (si la foto completa no dejó leer descripción, no se arriesga).
        verificado, _ = analizar_etiqueta(recorte, captura)
        sim_completa = etiqueta["descripcion_similitud"]
        sim_recorte = verificado["descripcion_similitud"]
        salida["recorte_confiable"] = bool(
            etiqueta["precio_etiqueta"] is not None
            and verificado["precio_etiqueta"] == etiqueta["precio_etiqueta"]
            and sim_completa is not None and sim_recorte is not None
            and sim_recorte >= sim_completa - TOLERANCIA_DESCRIPCION)
    except Exception as error:
        log.warning("%s: OCR falló: %s", capture_id, error)
    return salida
