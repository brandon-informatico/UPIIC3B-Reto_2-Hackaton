"""E4 · Preparación de imágenes antes de enviarlas al modelo."""
from __future__ import annotations

import base64
import io
from pathlib import Path

from PIL import Image, ImageOps

from contratos import CapturaPreparada, FeaturesCaptura
from src.ia.cliente import RAIZ

LADO_MAXIMO = 1024  # px; las fotos del reto vienen de 720×960 hasta 4000×3000
TIPOS_FOTO = ("facade", "product", "shelf")
TITULOS = {"facade": "FOTO 1 · FACHADA", "product": "FOTO 2 · PRODUCTO", "shelf": "FOTO 3 · ETIQUETA DE PRECIO"}
TIPOS_MEDIA = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def _resolver(ruta: str | None) -> Path | None:
    """Rutas relativas a la raíz del repo o a data/ (las de capturas.json empiezan con imagenes/)."""
    if not ruta:
        return None
    for base in (RAIZ, RAIZ / "data"):
        candidata = base / ruta
        if candidata.exists():
            return candidata
    return None


def rutas_fotos(captura: CapturaPreparada, features: FeaturesCaptura | None = None) -> dict[str, Path | None]:
    """Prefiere la foto normalizada de E2 (menos tokens); si no existe, usa la original."""
    rutas: dict[str, Path | None] = {}
    for tipo in TIPOS_FOTO:
        foto = getattr(features, tipo, None) if features else None
        rutas[tipo] = (_resolver(foto.ruta_normalizada) if foto else None) or _resolver(captura.rutas.get(tipo))
    return rutas


def _bytes_reducidos(ruta: Path) -> tuple[bytes, str]:
    """Si la foto mide más de LADO_MAXIMO px, la reduce en memoria (respaldo hasta que exista E2)."""
    with Image.open(ruta) as imagen:
        imagen = ImageOps.exif_transpose(imagen)
        if max(imagen.size) <= LADO_MAXIMO:
            return ruta.read_bytes(), TIPOS_MEDIA[ruta.suffix.lower()]
        imagen.thumbnail((LADO_MAXIMO, LADO_MAXIMO))
        bufer = io.BytesIO()
        imagen.convert("RGB").save(bufer, format="JPEG", quality=85)
        return bufer.getvalue(), "image/jpeg"


def bloque_imagen(ruta: Path) -> dict:
    """Bloque de imagen base64 para la API de mensajes (≈ ancho × alto / 750 tokens)."""
    if ruta.suffix.lower() not in TIPOS_MEDIA:
        raise ValueError(f"Formato de imagen no soportado: {ruta.name}")
    contenido, tipo_media = _bytes_reducidos(ruta)
    datos = base64.standard_b64encode(contenido).decode("ascii")
    return {"type": "image", "source": {"type": "base64", "media_type": tipo_media, "data": datos}}
