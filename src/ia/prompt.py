"""E4 · Instrucciones para analizar fachada, producto y etiqueta de precio.

Cambia VERSION_PROMPT cada vez que cambies INSTRUCCIONES: invalida la caché y queda registrado en UsoIA.
"""
from __future__ import annotations

from contratos import CapturaPreparada

VERSION_PROMPT = "v2"

INSTRUCCIONES = """Eres auditor de capturas de precios en tiendas de México. Recibes las fotos de una captura de campo
(FOTO 1 fachada de la tienda, FOTO 2 producto, FOTO 3 etiqueta de precio en anaquel) y los datos del producto esperado.
Llena cada campo SOLO con lo que se ve en las fotos.

Reglas generales:
- "no" = ves evidencia clara en contra. "no_determinable" = las fotos no permiten saberlo. No los confundas.
- Nunca inventes marcas, contenidos, textos ni precios que no se lean con claridad.

Campos:
- producto_visible: el producto aparece en la FOTO 2.
- producto_coincide: es el mismo tipo de producto que el esperado.
- marca_detectada / contenido_detectado: tal como se leen en el empaque (ej. "1.1 L"); null si no se leen.
- contenido_coincide: el contenido detectado equivale al esperado (considera conversiones: 1000 g = 1 kg).
- es_contratipo_permitido: "sin_informacion" salvo que los datos digan qué sustitutos se permiten.
- producto_aislado: "si" si el producto se ve de cerca y es el foco; "no" si la foto es lejana o no destaca.
- foto_borrosa: "parcial" si solo una parte relevante está borrosa.
- foto_de_pantalla: "si" si alguna foto parece tomada a la pantalla de otro dispositivo (pixeles, reflejos, marco).
- fachada_coincide: el letrero o los colores corresponden a la cadena seleccionada; "no_enviada" si no hay FOTO 1.
- etiqueta_visible / etiqueta_legible: sobre la FOTO 3.
- descripcion_completa: la etiqueta muestra la descripción del producto sin cortar.
- descripcion_coincide: la descripción de la etiqueta corresponde al producto esperado.
- precios_en_etiqueta: todos los precios legibles con su tipo (regular, oferta, volumen); lista vacía si ninguno.
- precio_unitario_presente: la etiqueta muestra un precio por unidad de medida además del precio de venta. En etiquetas
  mexicanas suele ir en letra pequeña: "$1.09 x 100 ml", "precio por kg", "$/L", "P.U.", "x kg" o "precio unitario".
  Busca ese texto pequeño antes de responder "no".
- duda_principal: máximo 20 palabras en español con la mayor duda, o null si no hay."""


def describir_captura(captura: CapturaPreparada) -> str:
    """Datos del producto esperado. NO incluye el precio capturado (lo compara el motor, E5)."""
    contenido = (
        f"{captura.unit_quantity_product:g} {captura.unit_product}"
        if captura.unit_quantity_product and captura.unit_product
        else "no indicado"
    )
    return (
        f"Cadena seleccionada: {captura.capture_store_name}\n"
        f"Producto esperado: {captura.product_name}\n"
        f"Marca capturada: {captura.capture_brand or 'no indicada'}\n"
        f"Contenido esperado: {contenido}"
    )
