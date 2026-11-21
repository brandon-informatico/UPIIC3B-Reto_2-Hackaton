"""Procesamiento local de una foto: leer, reducir, emparejar luz, medir y leer códigos (sin tokens).

Las señales que dependen de la luz (``brillo``, ``nitidez``) solo sirven para logs: en desarrollo se comprobó
que un modelo que las usa aprende "foto oscura = mala" (todas las aprobadas son de día). Para decidir se usan
``nitidez_norm`` y ``nitidez_zona_max``, que casi no cambian al oscurecer la foto un 15 % (0.6 % vs 27 %).
"""
from __future__ import annotations

import hashlib
import logging
import threading
from pathlib import Path
from typing import Any, get_args

import cv2
import numpy as np

from contratos import TipoFoto

try:  # lector de códigos opcional: sin él, los códigos quedan como "no_leido"
    import zxingcpp
except ImportError:  # pragma: no cover
    zxingcpp = None

log = logging.getLogger(__name__)

RAIZ = Path(__file__).resolve().parents[2]
TIPOS_FOTO: tuple[str, ...] = get_args(TipoFoto)  # ("facade", "product", "shelf"), definido en contratos/
# Solo estos formatos son códigos de producto; los QR de las etiquetas (Soriana) son identificadores internos.
FORMATOS_PRODUCTO = {"EAN13", "EAN8", "UPCA", "UPCE"}

PARAMETROS_DEFECTO: dict[str, Any] = {
    # Etiqueta a 768 px: ~590 tokens (vs 922 a 960) sin perder lectura del precio (medido en desarrollo).
    "lado_max": {"facade": 512, "product": 960, "shelf": 768},
    "clahe": {"facade": 2.0, "product": 2.0, "shelf": 3.0},
    "calidad_jpeg": 85,
    "leer_codigos": True,
}


def ruta_portatil(ruta: Path | str) -> str:
    """Ruta relativa a la raíz del repo si se puede (sirve en cualquier máquina); si no, absoluta."""
    ruta = Path(ruta).resolve()
    try:
        return ruta.relative_to(RAIZ).as_posix()
    except ValueError:
        return ruta.as_posix()


def ruta_absoluta(ruta: str | None) -> Path | None:
    """Inverso de ``ruta_portatil``: las rutas del contrato son relativas a la raíz del repo (o absolutas)."""
    if not ruta:
        return None
    ruta = Path(ruta)
    return ruta if ruta.is_absolute() else RAIZ / ruta


def leer_imagen(ruta: Path | str) -> np.ndarray | None:
    """Lee una imagen BGR. Funciona con rutas con acentos o ñ (cv2.imread no en Windows)."""
    try:
        datos = np.fromfile(str(ruta), dtype=np.uint8)
    except OSError:
        return None
    if datos.size == 0:
        return None
    return cv2.imdecode(datos, cv2.IMREAD_COLOR)


def reducir(img: np.ndarray, lado_max: int) -> np.ndarray:
    alto, ancho = img.shape[:2]
    escala = min(1.0, lado_max / max(alto, ancho))
    if escala >= 1.0:
        return img
    return cv2.resize(img, (round(ancho * escala), round(alto * escala)), interpolation=cv2.INTER_AREA)


def emparejar_luz(img: np.ndarray, fuerza: float) -> np.ndarray:
    """CLAHE sobre la luminancia: iguala fotos de día y de noche en la copia que ve el modelo."""
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    canal_l, canal_a, canal_b = cv2.split(lab)
    canal_l = cv2.createCLAHE(clipLimit=fuerza, tileGridSize=(8, 8)).apply(canal_l)
    return cv2.cvtColor(cv2.merge((canal_l, canal_a, canal_b)), cv2.COLOR_LAB2BGR)


def medir_imagen(img: np.ndarray) -> dict[str, float]:
    """``brillo`` y ``nitidez`` (Laplaciano crudo) solo para logs; ``nitidez_norm`` = var(Laplaciano)/var(imagen);
    ``nitidez_zona_max`` = nitidez normalizada del 10 % de bloques más nítidos (una foto movida no tiene ninguno)."""
    gris = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float64)
    laplaciano = cv2.Laplacian(gris, cv2.CV_64F)
    lado = 48
    bloques = [
        laplaciano[i:i + lado, j:j + lado].var() / (gris[i:i + lado, j:j + lado].var() + 25.0)
        for i in range(0, gris.shape[0] - lado + 1, lado)
        for j in range(0, gris.shape[1] - lado + 1, lado)
    ]
    mejores = sorted(bloques)[-max(1, len(bloques) // 10):] if bloques else [0.0]
    return {
        "brillo": round(float(gris.mean()), 1),
        "nitidez": round(float(laplaciano.var()), 1),
        "nitidez_norm": round(float(laplaciano.var() / (gris.var() + 1e-6)), 4),
        "nitidez_zona_max": round(float(np.mean(mejores)), 4),
    }


def leer_codigos(img: np.ndarray) -> list[dict[str, str]]:
    """Códigos de producto (EAN/UPC) en la imagen original → [{"texto", "formato"}]; [] si no hay."""
    if zxingcpp is None:
        return []
    codigos: dict[str, str] = {}
    try:
        for resultado in zxingcpp.read_barcodes(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)):
            formato = str(resultado.format).split(".")[-1].upper().replace("-", "").replace("_", "")
            if formato in FORMATOS_PRODUCTO and resultado.text.isdigit():
                codigos[resultado.text] = formato
    except Exception as error:  # el lector nunca debe tumbar la captura
        log.debug("Lector de códigos falló: %s", error)
    return [{"texto": texto, "formato": formato} for texto, formato in sorted(codigos.items())]


def mismo_codigo(a: str | None, b: str | None) -> bool:
    """EAN-13 y UPC-A del mismo producto difieren solo por ceros a la izquierda."""
    return bool(a and b) and a.lstrip("0") == b.lstrip("0")


def parecido(img_a: np.ndarray, img_b: np.ndarray) -> float:
    """Correlación de histogramas de color (-1 a 1). Medido: 0.32 en aprobadas, 0.54 borrosas, 0.73 descripción
    incompleta (fotos de producto y etiqueta casi iguales = mala captura). Pista, no regla."""
    def histograma(img: np.ndarray) -> np.ndarray:
        hsv = cv2.cvtColor(cv2.resize(img, (256, 256)), cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [30, 32], [0, 180, 0, 256])
        return cv2.normalize(hist, hist).flatten()
    return round(float(cv2.compareHist(histograma(img_a), histograma(img_b), cv2.HISTCMP_CORREL)), 3)


def guardar_jpeg(img: np.ndarray, destino: Path, calidad: int) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    ok, datos = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, calidad])
    if not ok:
        raise ValueError(f"No se pudo codificar {destino.name}")
    datos.tofile(str(destino))  # tofile también funciona con acentos en la ruta


class CacheFachadas:
    """Procesa cada fachada una sola vez (en desarrollo hay 25 fachadas distintas para 100 capturas)."""

    def __init__(self) -> None:
        self._por_hash: dict[str, dict[str, Any]] = {}
        self._candado = threading.Lock()

    def obtener(self, clave: str) -> dict[str, Any] | None:
        with self._candado:
            return self._por_hash.get(clave)

    def guardar(self, clave: str, info: dict[str, Any]) -> None:
        with self._candado:
            self._por_hash.setdefault(clave, info)

    def __len__(self) -> int:
        return len(self._por_hash)


def procesar_foto(ruta: Path, tipo: str, capture_id: str, ruta_cache: Path, parametros: dict[str, Any],
                  cache_fachadas: CacheFachadas) -> tuple[dict[str, Any], np.ndarray]:
    """Regresa (campos de FotoNormalizada/FachadaNormalizada, copia reducida sin CLAHE).

    Lanza ValueError si la foto no se puede decodificar.
    """
    original = leer_imagen(ruta)
    if original is None:
        raise ValueError("no se pudo decodificar la imagen")
    reducida = reducir(original, parametros["lado_max"][tipo])
    clave = None
    if tipo == "facade":
        clave = hashlib.md5(Path(ruta).read_bytes()).hexdigest()
        previa = cache_fachadas.obtener(clave)
        if previa is not None:
            return {**previa, "repetida": True}, reducida
    para_modelo = emparejar_luz(reducida, parametros["clahe"][tipo])
    destino = Path(ruta_cache) / "normalizadas" / tipo / (f"{clave}.jpg" if clave else f"{capture_id}_{tipo}.jpg")
    guardar_jpeg(para_modelo, destino, parametros["calidad_jpeg"])
    alto, ancho = para_modelo.shape[:2]
    info: dict[str, Any] = {
        "original_wh": f"{original.shape[1]}x{original.shape[0]}",
        "final_wh": f"{ancho}x{alto}",
        "ruta_normalizada": ruta_portatil(destino),
        "tokens_aprox": round(ancho * alto / 750),  # estimación de tokens de imagen en Claude
        **medir_imagen(reducida),
    }
    if tipo == "facade":
        info.update(hash=clave, repetida=False)
        cache_fachadas.guardar(clave, info)
    elif parametros.get("leer_codigos", True) and zxingcpp is not None:
        info["codigos_leidos"] = leer_codigos(original)
    return info, reducida
