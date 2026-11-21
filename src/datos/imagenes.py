"""Fotos de cada captura: localizar, verificar, normalizar y medir (todo local, sin tokens).

Pasos por captura:
1. ``rutas_imagenes``: ubica fachada, producto y etiqueta (por metadatos y, si no, por nombre de archivo).
2. ``verificar_imagenes``: cada foto queda ``ok``, ``faltante`` o ``corrupta``.
3. ``normalizar_imagenes``: copia reducida con luz emparejada (CLAHE) para el modelo, señales locales
   comparables entre capturas y lectura de códigos de barras.

Las señales que dependen de la luz (``brillo``, ``nitidez``) solo sirven para logs: en desarrollo se comprobó
que un modelo que las usa aprende "foto oscura = mala" (todas las aprobadas son de día). Para decidir se usan
``nitidez_norm`` y ``nitidez_zona_max``, que no cambian al oscurecer o aclarar la foto.
"""
from __future__ import annotations

import hashlib
import logging
import re
import threading
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from typing import get_args

from contratos import TipoFoto
from src.archivos import nombre_archivo

TIPOS_IMAGEN: tuple[str, ...] = get_args(TipoFoto)  # ("facade", "product", "shelf"), definido en contratos/

try:  # lector de códigos opcional: sin él, los códigos quedan como "no_leido"
    import zxingcpp
except ImportError:  # pragma: no cover
    zxingcpp = None

log = logging.getLogger(__name__)

EXTENSIONES = {".jpg", ".jpeg", ".png", ".webp"}
SINONIMOS_TIPO = {
    "facade": "facade", "fachada": "facade",
    "product": "product", "producto": "product",
    "shelf": "shelf", "etiqueta": "shelf", "anaquel": "shelf", "label": "shelf",
}
_PATRON_NOMBRE = re.compile(r"^(?P<id>CAP-\d+)[_\-](?P<tipo>[a-zA-Z]+)$", re.IGNORECASE)
# Solo estos formatos son códigos de producto; los QR de las etiquetas (Soriana) son identificadores internos.
FORMATOS_PRODUCTO = {"EAN13", "EAN8", "UPCA", "UPCE"}

ESTADO_OK, ESTADO_FALTANTE, ESTADO_CORRUPTA = "ok", "faltante", "corrupta"

PARAMETROS_DEFECTO: dict[str, Any] = {
    "lado_max": {"facade": 512, "product": 960, "shelf": 960},
    "clahe": {"facade": 2.0, "product": 2.0, "shelf": 3.0},
    "calidad_jpeg": 85,
    "leer_codigos": True,
}


# ───────────────────────── localizar ─────────────────────────
def indexar_carpeta(carpeta: Path) -> dict[str, dict[str, Path]]:
    """Agrupa fotos sueltas por nombre: {capture_id: {"facade": ruta, ...}}.

    Respaldo para cuando las rutas de los metadatos no existen (p. ej. el set ciego llega con otra estructura).
    Acepta ``CAP-123_facade.jpg`` y sinónimos (fachada, producto, etiqueta, anaquel).
    """
    indice: dict[str, dict[str, Path]] = {}
    carpeta = Path(carpeta)
    if not carpeta.exists():
        return indice
    for foto in sorted(carpeta.rglob("*")):
        if foto.suffix.lower() not in EXTENSIONES:
            continue
        coincidencia = _PATRON_NOMBRE.match(foto.stem)
        if not coincidencia:
            continue
        tipo = SINONIMOS_TIPO.get(coincidencia.group("tipo").lower())
        if tipo:
            indice.setdefault(coincidencia.group("id").upper(), {}).setdefault(tipo, foto)
    return indice


def rutas_imagenes(captura: dict[str, Any], base: Path,
                   indice: dict[str, dict[str, Path]] | None = None) -> dict[str, Path | None]:
    """Contrato de CONTEXT.md: {"facade": Path|None, "product": Path|None, "shelf": Path|None}.

    Usa ``<tipo>_file`` relativo a ``base``; si no existe, busca en ``indice`` (de ``indexar_carpeta``).
    """
    base = Path(base)
    imagenes: dict[str, Path | None] = {}
    for tipo in TIPOS_IMAGEN:
        ruta = None
        relativa = captura.get(f"{tipo}_file")
        if relativa:
            candidata = base / relativa
            if candidata.is_file():
                ruta = candidata
        if ruta is None and indice:
            ruta = indice.get(str(captura.get("capture_id", "")).upper(), {}).get(tipo)
        imagenes[tipo] = ruta
    return imagenes


# ───────────────────────── leer y verificar ─────────────────────────
def leer_imagen(ruta: Path) -> np.ndarray | None:
    """Lee una imagen BGR. Funciona con rutas con acentos o ñ (cv2.imread no en Windows)."""
    try:
        datos = np.fromfile(str(ruta), dtype=np.uint8)
    except OSError:
        return None
    if datos.size == 0:
        return None
    return cv2.imdecode(datos, cv2.IMREAD_COLOR)


def verificar_imagenes(imagenes: dict[str, Path | None]) -> dict[str, str]:
    """Estado de cada foto: ``ok``, ``faltante`` o ``corrupta`` (no se puede decodificar)."""
    estados: dict[str, str] = {}
    for tipo in TIPOS_IMAGEN:
        ruta = imagenes.get(tipo)
        if ruta is None or not Path(ruta).is_file():
            estados[tipo] = ESTADO_FALTANTE
        else:
            estados[tipo] = ESTADO_OK if leer_imagen(ruta) is not None else ESTADO_CORRUPTA
    return estados


# ───────────────────────── medir ─────────────────────────
def _reducir(img: np.ndarray, lado_max: int) -> np.ndarray:
    alto, ancho = img.shape[:2]
    escala = min(1.0, lado_max / max(alto, ancho))
    if escala >= 1.0:
        return img
    return cv2.resize(img, (round(ancho * escala), round(alto * escala)), interpolation=cv2.INTER_AREA)


def _emparejar_luz(img: np.ndarray, fuerza: float) -> np.ndarray:
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    canal_l, canal_a, canal_b = cv2.split(lab)
    canal_l = cv2.createCLAHE(clipLimit=fuerza, tileGridSize=(8, 8)).apply(canal_l)
    return cv2.cvtColor(cv2.merge((canal_l, canal_a, canal_b)), cv2.COLOR_LAB2BGR)


def medir_imagen(img: np.ndarray) -> dict[str, float]:
    """Señales de calidad sobre la versión reducida (comparables entre capturas).

    - ``brillo`` y ``nitidez`` (Laplaciano crudo): dependen de la luz → solo logs.
    - ``nitidez_norm``: var(Laplaciano) / var(imagen); no cambia si la foto se oscurece o aclara.
    - ``nitidez_zona_max``: nitidez normalizada del 10 % de bloques más nítidos (la etiqueta suele ser esa zona;
      una foto movida no tiene ninguna zona nítida).
    """
    gris = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float64)
    laplaciano = cv2.Laplacian(gris, cv2.CV_64F)
    varianza = float(gris.var())
    lado = 48
    bloques = [
        laplaciano[i:i + lado, j:j + lado].var() / (gris[i:i + lado, j:j + lado].var() + 25.0)
        for i in range(0, gris.shape[0] - lado + 1, lado)
        for j in range(0, gris.shape[1] - lado + 1, lado)
    ]
    mejores = sorted(bloques)[-max(1, len(bloques) // 10):] if bloques else [0.0]
    return {
        "brillo": round(float(gris.mean()), 1),
        "contraste": round(float(np.sqrt(varianza)), 1),
        "nitidez": round(float(laplaciano.var()), 1),
        "nitidez_norm": round(float(laplaciano.var() / (varianza + 1e-6)), 4),
        "nitidez_zona_max": round(float(np.mean(mejores)), 4),
    }


def leer_codigos(img: np.ndarray) -> list[dict[str, str]]:
    """Códigos de producto (EAN/UPC) legibles en la imagen original; lista vacía si no hay o no hay lector."""
    if zxingcpp is None:
        return []
    codigos = {}
    try:
        for resultado in zxingcpp.read_barcodes(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)):
            formato = str(resultado.format).split(".")[-1].upper().replace("-", "").replace("_", "")
            if formato in FORMATOS_PRODUCTO and resultado.text.isdigit():
                codigos[resultado.text] = formato
    except Exception as error:  # el lector nunca debe tumbar la captura
        log.debug("Lector de códigos falló: %s", error)
    return [{"texto": texto, "formato": formato} for texto, formato in sorted(codigos.items())]


def _mismo_codigo(a: str | None, b: str | None) -> bool:
    """EAN-13 y UPC-A del mismo producto difieren solo por ceros a la izquierda."""
    return bool(a and b) and a.lstrip("0") == b.lstrip("0")


def _parecido(img_a: np.ndarray, img_b: np.ndarray) -> float:
    """Correlación de histogramas de color (-1 a 1). Producto y etiqueta casi iguales = posible mala captura."""
    def histograma(img: np.ndarray) -> np.ndarray:
        hsv = cv2.cvtColor(cv2.resize(img, (256, 256)), cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [30, 32], [0, 180, 0, 256])
        return cv2.normalize(hist, hist).flatten()
    return round(float(cv2.compareHist(histograma(img_a), histograma(img_b), cv2.HISTCMP_CORREL)), 3)


# ───────────────────────── normalizar ─────────────────────────
class CacheFachadas:
    """Evalúa cada fachada una sola vez (en desarrollo hay 25 fachadas distintas para 100 capturas)."""

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


def _guardar_jpeg(img: np.ndarray, destino: Path, calidad: int) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    ok, datos = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, calidad])
    if not ok:
        raise ValueError(f"No se pudo codificar {destino.name}")
    datos.tofile(str(destino))  # tofile también funciona con acentos en la ruta


def _procesar_foto(ruta: Path, tipo: str, capture_id: str, ruta_cache: Path,
                   parametros: dict[str, Any], cache_fachadas: CacheFachadas) -> tuple[dict[str, Any], np.ndarray]:
    original = leer_imagen(ruta)
    if original is None:
        raise ValueError("no se pudo decodificar la imagen")
    clave = None
    if tipo == "facade":
        clave = hashlib.md5(Path(ruta).read_bytes()).hexdigest()
        previa = cache_fachadas.obtener(clave)
        if previa is not None:
            return {**previa, "repetida": True}, _reducir(original, parametros["lado_max"][tipo])
    reducida = _reducir(original, parametros["lado_max"][tipo])
    para_modelo = _emparejar_luz(reducida, parametros["clahe"][tipo])
    nombre = f"{clave}.jpg" if clave else f"{nombre_archivo(capture_id)}_{tipo}.jpg"
    destino = ruta_cache / "normalizadas" / tipo / nombre
    _guardar_jpeg(para_modelo, destino, parametros["calidad_jpeg"])
    alto, ancho = para_modelo.shape[:2]
    info: dict[str, Any] = {
        "original_wh": f"{original.shape[1]}x{original.shape[0]}",
        "final_wh": f"{ancho}x{alto}",
        "ruta_normalizada": destino.as_posix(),
        "tokens_aprox": round(ancho * alto / 750),  # estimación de tokens de imagen en Claude
        **medir_imagen(reducida),
    }
    if tipo == "facade":
        info.update(hash=clave, repetida=False)
        cache_fachadas.guardar(clave, info)
    elif parametros.get("leer_codigos", True):
        info["codigos_leidos"] = leer_codigos(original)
    return info, reducida


def normalizar_imagenes(captura: dict[str, Any], imagenes: dict[str, Path | None], ruta_cache: Path,
                        cache_fachadas: CacheFachadas | None = None,
                        parametros: dict[str, Any] | None = None) -> dict[str, Any]:
    """Normaliza las fotos de una captura y regresa sus señales locales.

    Nunca lanza excepción por una foto mala: se anota en ``errores`` y se procesan las demás.
    Regresa (todas las llaves siempre presentes):
        estado_imagenes: {"facade": "ok"|"faltante"|"corrupta", ...}
        imagenes_normalizadas: {"facade": Path|None, ...}   ← lo que se manda al modelo
        senales: {"facade": dict|None, "product": dict|None, "shelf": dict|None,
                  "parecido_producto_etiqueta": float|None,
                  "codigo_empaque": "coincide"|"no_coincide"|"no_leido",
                  "codigo_etiqueta": "coincide"|"distinto"|"no_leido",
                  "codigo_barras_detectado": str|None, "tokens_imagen_aprox": int}
        errores: [str]
    """
    parametros = {**PARAMETROS_DEFECTO, **(parametros or {})}
    cache_fachadas = cache_fachadas if cache_fachadas is not None else CacheFachadas()
    ruta_cache = Path(ruta_cache)
    capture_id = str(captura.get("capture_id", "SIN-ID"))
    estado = verificar_imagenes(imagenes)
    senales: dict[str, Any] = {tipo: None for tipo in TIPOS_IMAGEN}
    normalizadas: dict[str, Path | None] = {tipo: None for tipo in TIPOS_IMAGEN}
    reducidas: dict[str, np.ndarray] = {}
    errores: list[str] = [f"{tipo}: {e}" for tipo, e in estado.items() if e != ESTADO_OK]

    for tipo in TIPOS_IMAGEN:
        if estado[tipo] != ESTADO_OK:
            continue
        try:
            info, reducidas[tipo] = _procesar_foto(imagenes[tipo], tipo, capture_id, ruta_cache,
                                                   parametros, cache_fachadas)
            senales[tipo] = info
            normalizadas[tipo] = Path(info["ruta_normalizada"])
        except Exception as error:  # una foto mala no detiene la captura
            estado[tipo] = ESTADO_CORRUPTA
            errores.append(f"{tipo}: {error}")
            log.warning("%s %s: %s", capture_id, tipo, error)

    if "product" in reducidas and "shelf" in reducidas:
        senales["parecido_producto_etiqueta"] = _parecido(reducidas["product"], reducidas["shelf"])
    else:
        senales["parecido_producto_etiqueta"] = None

    esperado = captura.get("product_barcode")
    empaque = [c["texto"] for c in (senales["product"] or {}).get("codigos_leidos", [])]
    etiqueta = [c["texto"] for c in (senales["shelf"] or {}).get("codigos_leidos", [])]
    senales["codigo_empaque"] = ("no_leido" if not empaque else
                                 "coincide" if any(_mismo_codigo(c, esperado) for c in empaque) else "no_coincide")
    senales["codigo_etiqueta"] = ("no_leido" if not etiqueta else
                                  "coincide" if any(_mismo_codigo(c, esperado) for c in etiqueta) else "distinto")
    coincidentes = [c for c in empaque + etiqueta if _mismo_codigo(c, esperado)]
    senales["codigo_barras_detectado"] = (coincidentes or empaque or etiqueta or [None])[0]
    senales["tokens_imagen_aprox"] = sum(
        (senales[t] or {}).get("tokens_aprox", 0) for t in TIPOS_IMAGEN
        if not (t == "facade" and (senales[t] or {}).get("repetida")))
    return {"estado_imagenes": estado, "imagenes_normalizadas": normalizadas, "senales": senales, "errores": errores}
