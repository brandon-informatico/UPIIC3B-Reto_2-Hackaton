"""Descarga los datos oficiales de desarrollo del reto a data/.

Uso:
    python scripts/descargar_datos.py            # metadatos + imágenes (~97 MB)
    python scripts/descargar_datos.py --sin-imagenes

Resultado:
    data/capturas.json, data/capturas.csv, data/catalogo_productos.csv, data/LEEME.md
    data/imagenes/CAP-XXXXXX_{facade,product,shelf}.jpg

Los datos NO se suben al repositorio (data/ está en .gitignore) por las reglas del reto.
"""
from __future__ import annotations

import argparse
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

URL_BASE = "https://hackaton3b.com/descargas/"
ZIP_METADATOS = "Validat3B_desarrollo_metadatos.zip"
ZIP_IMAGENES = "Validat3B_desarrollo_imagenes.zip"
RAIZ = Path(__file__).resolve().parent.parent


def descargar_y_extraer(nombre_zip: str, destino: Path) -> int:
    """Baja un zip oficial y acomoda su contenido en destino. Regresa archivos copiados."""
    copiados = 0
    with tempfile.TemporaryDirectory() as tmp:
        ruta_zip = Path(tmp) / nombre_zip
        print(f"Descargando {nombre_zip} ...")
        urllib.request.urlretrieve(URL_BASE + nombre_zip, ruta_zip)
        carpeta = Path(tmp) / "extraido"
        with zipfile.ZipFile(ruta_zip) as archivo_zip:
            archivo_zip.extractall(carpeta)
        for archivo in carpeta.rglob("*"):
            if not archivo.is_file() or archivo.name.startswith(".") or "__MACOSX" in archivo.parts:
                continue
            es_imagen = archivo.suffix.lower() in {".jpg", ".jpeg", ".png"}
            salida = destino / "imagenes" / archivo.name if es_imagen else destino / archivo.name
            salida.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(archivo, salida)
            copiados += 1
    return copiados


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--destino", type=Path, default=RAIZ / "data")
    parser.add_argument("--sin-imagenes", action="store_true")
    args = parser.parse_args()

    args.destino.mkdir(parents=True, exist_ok=True)
    total = descargar_y_extraer(ZIP_METADATOS, args.destino)
    if not args.sin_imagenes:
        total += descargar_y_extraer(ZIP_IMAGENES, args.destino)
    imagenes = len(list((args.destino / "imagenes").glob("*"))) if (args.destino / "imagenes").exists() else 0
    print(f"Listo: {total} archivos en {args.destino} ({imagenes} imágenes).")


if __name__ == "__main__":
    main()
