"""Carga (E1) y visión local (E2), sin tokens. Responsable: Copa (rama feat/datos).

Contrato (CONTEXT.md y contratos/contratos.py):
    cargar_capturas(ruta_capturas) -> list[CapturaPreparada]
    normalizar(capturas) -> list[FeaturesCaptura]          # una por capture_id, aunque no haya fotos
    separar_fotos(carpeta) -> IndiceFotos
CLI: python -m src.datos  → cache/capturas_preparadas.json, cache/indice_fotos.json, cache/features.json
"""
from src.datos.cargador import cargar_capturas, cargar_catalogo
from src.datos.normalizar import normalizar
from src.datos.separar_fotos import separar_fotos

__all__ = ["cargar_capturas", "cargar_catalogo", "normalizar", "separar_fotos"]
