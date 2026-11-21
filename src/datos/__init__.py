"""Carga, limpieza e ingesta local de fotos. Responsable: Copka (rama feat/datos).

Contrato (CONTEXT.md, sección 4):
    cargar_capturas(ruta) -> list[dict]
    cargar_catalogo(ruta) -> dict[int, dict]
    rutas_imagenes(captura, base) -> dict[str, Path | None]
Extra para el pipeline y la IA:
    preparar_captura(...) -> dict      # una captura: fotos verificadas, normalizadas y señales locales
    ingerir(...) -> list[dict]         # todas; CLI: python -m src.datos
"""
from src.datos.cargador import cargar_capturas, cargar_catalogo
from src.datos.imagenes import normalizar_imagenes, rutas_imagenes, verificar_imagenes
from src.datos.ingesta import ingerir, preparar_captura

__all__ = [
    "cargar_capturas", "cargar_catalogo", "rutas_imagenes", "verificar_imagenes",
    "normalizar_imagenes", "preparar_captura", "ingerir",
]
