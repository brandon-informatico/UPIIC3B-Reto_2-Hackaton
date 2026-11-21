"""Hoja de revisión visual de los recortes de etiqueta (para validar a ojo, en local).

    python -m src.datos.revision                 # 24 capturas → cache/revision_recortes.jpg
    python -m src.datos.revision --n 48 --solo-confiables

Cada fila: foto de etiqueta completa (izquierda) y su recorte (derecha), con el capture_id, si el recorte es
confiable, el precio leído por OCR y el capturado. Se abre con cualquier visor de imágenes; no sale de la máquina.
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import cv2
import numpy as np

from src.datos.imagenes import _guardar_jpeg, leer_imagen
from src.datos.ingesta import RAIZ

log = logging.getLogger(__name__)
ALTO_FILA = 260


def _miniatura(ruta: str | None, alto: int) -> np.ndarray:
    img = leer_imagen(RAIZ / ruta) if ruta else None
    if img is None:
        return np.full((alto, alto, 3), 200, np.uint8)
    return cv2.resize(img, (max(1, round(img.shape[1] * alto / img.shape[0])), alto), interpolation=cv2.INTER_AREA)


def hoja_revision(ruta_ingesta: Path, ruta_salida: Path, n: int = 24, solo_confiables: bool = False) -> int:
    preparadas = json.loads(Path(ruta_ingesta).read_text(encoding="utf-8"))
    filas = []
    for p in preparadas:
        if not p.get("recorte_etiqueta") or (solo_confiables and not p.get("recorte_confiable")):
            continue
        completa = _miniatura(p["imagenes_normalizadas"].get("shelf"), ALTO_FILA)
        recorte = _miniatura(p["recorte_etiqueta"], ALTO_FILA)
        separador = np.full((ALTO_FILA, 12, 3), 255, np.uint8)
        fila = np.hstack([completa, separador, recorte])
        etiqueta = (p.get("ocr") or {}).get("etiqueta") or {}
        texto = (f"{p['capture_id']}  confiable={p.get('recorte_confiable')}  "
                 f"OCR=${etiqueta.get('precio_etiqueta')}  capturado=${p['captura'].get('capture_price')}")
        barra = np.full((28, fila.shape[1], 3), 255, np.uint8)
        cv2.putText(barra, texto, (6, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 1, cv2.LINE_AA)
        filas.append(np.vstack([barra, fila]))
        if len(filas) >= n:
            break
    if not filas:
        return 0
    ancho = max(f.shape[1] for f in filas)
    filas = [np.hstack([f, np.full((f.shape[0], ancho - f.shape[1], 3), 255, np.uint8)]) for f in filas]
    _guardar_jpeg(np.vstack(filas), Path(ruta_salida), 85)
    return len(filas)


def main() -> None:
    parser = argparse.ArgumentParser(description="Hoja de revisión visual de recortes de etiqueta.")
    parser.add_argument("--ingesta", type=Path, default=RAIZ / "cache/ingesta.json")
    parser.add_argument("--salida", type=Path, default=RAIZ / "cache/revision_recortes.jpg")
    parser.add_argument("--n", type=int, default=24)
    parser.add_argument("--solo-confiables", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    total = hoja_revision(args.ingesta, args.salida, args.n, args.solo_confiables)
    log.info("Hoja de revisión con %d capturas → %s", total, args.salida)


if __name__ == "__main__":
    main()
