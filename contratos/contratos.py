"""Contratos de datos entre etapas del motor Validat3B (pydantic v2).

Cada etapa produce exactamente estas formas. Mientras un módulo real no exista,
quien lo consume usa los ejemplos de contratos/ejemplos/ (misma forma), así nadie espera a nadie.

    E1 carga ─────────► CapturaPreparada
    separar_fotos.py ─► IndiceFotos
    normalizar.py ────► FeaturesCaptura          (E2 visión local, sin tokens)
    E4 IA ────────────► HallazgosIA + UsoIA      (o null si la IA falla)
    E3/E5 decisión ───► DecisionInterna
    E6 salida ────────► RegistroSalida           (formato oficial del reto)

Lo marcado PENDIENTE_COMITE se ajusta en UN solo lugar cuando llegue el esquema oficial.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ───────────────────────── valores compartidos ─────────────────────────
TipoFoto = Literal["facade", "product", "shelf"]
Decision = Literal["aprobada", "rechazada", "revision_manual"]
SiNoND = Literal["si", "no", "no_determinable"]
Frente = Literal["A_identidad", "B_calidad", "C_precio", "sistema"]

# PENDIENTE_COMITE: el ejemplo oficial solo muestra "ok" y "falla".
VALORES_VALIDACION_OFICIAL: tuple[str, ...] = ("ok", "falla")
ValidacionInterna = Literal["ok", "falla", "no_determinable"]

# PENDIENTE_COMITE: lista oficial. Solo PRODUCTO_NO_COINCIDE aparece en el ejemplo publicado;
# los demás son provisionales, nombrados según los motivos reales del reto.
REASON_CODES_PROVISIONALES: dict[str, Frente] = {
    "PRODUCTO_NO_COINCIDE": "A_identidad",
    "CONTRATIPO_INVALIDO": "A_identidad",
    "DESCRIPCION_INCOMPLETA": "A_identidad",
    "PRODUCTO_NO_VISIBLE": "A_identidad",
    "FACHADA_INCORRECTA": "B_calidad",
    "CAPTURA_LEJANA": "B_calidad",
    "IMAGEN_BORROSA": "B_calidad",
    "FOTO_DE_PANTALLA": "B_calidad",
    "SIN_ETIQUETA_PRECIO": "C_precio",
    "SIN_PRECIO_UNITARIO": "C_precio",
}
# Prioridad cuando hay varias fallas: identidad → calidad → precio.
PRIORIDAD_FRENTE: dict[str, int] = {"A_identidad": 0, "B_calidad": 1, "C_precio": 2, "sistema": 3}

MotivoRevision = Literal[
    "duda_identidad", "duda_calidad", "duda_precio", "dos_precios", "precio_distinto_al_capturado",
    "contratipo_sin_informacion", "confianza_insuficiente",
    "imagen_faltante", "imagen_corrupta", "sin_fotos", "ia_error", "salida_invalida",
]


class _Estricto(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ───────────────────────── E1 · carga ─────────────────────────
class CapturaPreparada(_Estricto):
    """Una captura lista para procesar. NUNCA incluye decision_esperada ni motivo_rechazo."""
    capture_id: str = Field(pattern=r"^CAP-\d+$")
    capture_store_name: str
    capture_date: str  # solo para logs; no se usa para decidir
    capture_price: Optional[float]
    capture_brand: Optional[str]
    capture_barcode: Optional[str]
    id_product: int
    product_name: str
    product_barcode: Optional[str]
    product_price: Optional[float]
    min_product_price: Optional[float]
    max_product_price: Optional[float]
    unit_product: Optional[str]
    unit_quantity_product: Optional[float]
    product_group: Optional[str]
    product_line: Optional[str]
    rutas: dict[TipoFoto, Optional[str]]
    banderas_datos: list[str] = []  # ej. "imagen_faltante:product", "precio_invalido", "id_duplicado"

    @field_validator("capture_barcode", "product_barcode", mode="before")
    @classmethod
    def _codigo_como_texto(cls, v):  # conservar ceros a la izquierda
        return None if v is None else str(v)


# ───────────────────────── separar_fotos.py ─────────────────────────
class IndiceFotos(BaseModel):
    """indice_fotos.json → {capture_id: {"facade": ruta, "product": ruta, "shelf": ruta}}."""
    capturas: dict[str, dict[TipoFoto, str]]


# ───────────────────────── E2 · normalizar.py ─────────────────────────
class Codigo(_Estricto):
    texto: str
    formato: str  # "EAN13", "UPCA", "QRCode", ... (los QR no cuentan como código de producto)


class FotoNormalizada(_Estricto):
    original_wh: str = Field(pattern=r"^\d+x\d+$")
    final_wh: str = Field(pattern=r"^\d+x\d+$")
    ruta_normalizada: str
    tokens_aprox: int = Field(ge=0)            # ancho × alto / 750
    brillo: float = Field(ge=0, le=255)        # SOLO para logs: no se usa para decidir (sesgo día/noche)
    nitidez: float = Field(ge=0)               # Laplaciano crudo: depende del brillo → solo logs
    nitidez_norm: float = Field(ge=0)          # var(Laplaciano) / var(imagen): la que usa el motor
    nitidez_zona_max: float = Field(ge=0)      # nitidez normalizada del 10% de bloques más nítidos
    codigos_leidos: Optional[list[Codigo]] = None  # None = no se intentó leer (sin zxing o fachada)


class FachadaNormalizada(FotoNormalizada):
    hash: str
    repetida: bool


class FeaturesCaptura(_Estricto):
    """Una entrada de features.json. Debe existir UNA por cada capture_id de capturas.json."""
    capture_id: str = Field(pattern=r"^CAP-\d+$")
    estado: Literal["completa", "incompleta", "sin_fotos"]
    facade: Optional[FachadaNormalizada] = None
    product: Optional[FotoNormalizada] = None
    shelf: Optional[FotoNormalizada] = None
    parecido_producto_etiqueta: Optional[float] = Field(default=None, ge=-1, le=1)
    # Tres estados: "no_leido" NO es lo mismo que "no_coincide".
    codigo_empaque: Literal["coincide", "no_coincide", "no_leido"]
    codigo_etiqueta: Literal["coincide", "distinto", "no_leido"]  # distinto NO es falla (Walmart/Bodega)
    errores: list[str] = []

    @model_validator(mode="after")
    def _coherencia(self):
        partes = [p for p in ("facade", "product", "shelf") if getattr(self, p) is not None]
        esperado = "completa" if len(partes) == 3 else "sin_fotos" if not partes else "incompleta"
        if self.estado != esperado:
            raise ValueError(f"estado={self.estado} pero hay {len(partes)} fotos procesadas ({esperado})")
        if self.estado != "completa" and not self.errores:
            raise ValueError("una captura no completa debe explicar el motivo en errores")
        return self


# ───────────────────────── E4 · IA ─────────────────────────
class PrecioEtiqueta(_Estricto):
    valor: float = Field(gt=0)
    tipo: Literal["regular", "oferta", "volumen"]


class HallazgosIA(_Estricto):
    """Salida estructurada de claude-haiku-5-5 (output_config.format con este schema)."""
    producto_visible: Literal["si", "no"]
    producto_coincide: SiNoND
    marca_detectada: Optional[str]
    contenido_detectado: Optional[str]
    contenido_coincide: SiNoND
    es_contratipo_permitido: Literal["si", "no", "sin_informacion"]
    producto_aislado: Literal["si", "no"]
    foto_borrosa: Literal["si", "no", "parcial"]
    foto_de_pantalla: Literal["si", "no"]
    fachada_coincide: Literal["si", "no", "no_determinable", "no_enviada"]
    etiqueta_visible: Literal["si", "no"]
    etiqueta_legible: Literal["si", "no", "parcial"]
    descripcion_completa: SiNoND
    descripcion_coincide: SiNoND
    precios_en_etiqueta: list[PrecioEtiqueta]
    precio_unitario_presente: Literal["si", "no"]
    duda_principal: Optional[str] = Field(default=None, max_length=200)


class UsoIA(_Estricto):
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cache_read_input_tokens: int = Field(ge=0, default=0)
    latencia_ms: int = Field(ge=0)
    intentos: int = Field(ge=1)
    version_prompt: str
    modelo: str = "claude-haiku-5-5"
    stop_reason: Optional[str]  # "end_turn" esperado; "refusal"/"max_tokens" ⇒ revisión manual


# ───────────────────────── E3/E5 · decisión ─────────────────────────
class Falla(_Estricto):
    reason_code: str = Field(pattern=r"^[A-Z_]+$")
    frente: Frente
    fuente: Literal["local", "ia", "reglas"]
    detalle: str


class ValidacionesInternas(_Estricto):
    tienda_fachada: ValidacionInterna
    producto: ValidacionInterna
    codigo_barras: ValidacionInterna
    evidencia_precio: ValidacionInterna


class DecisionInterna(_Estricto):
    capture_id: str = Field(pattern=r"^CAP-\d+$")
    decision: Decision
    p_valida: float = Field(ge=0, le=1)       # probabilidad calibrada; no la confianza del modelo
    fallas: list[Falla]
    reason_code: Optional[str]                # el de mayor prioridad entre fallas
    motivo_revision: Optional[MotivoRevision]
    validaciones: ValidacionesInternas
    precio_detectado: Optional[float]
    tipo_precio: Optional[Literal["regular", "oferta", "volumen"]]
    codigo_barras_detectado: Optional[str]
    ruta_decision: Literal["local", "ia", "error"]

    @model_validator(mode="after")
    def _reglas(self):
        if self.decision == "aprobada":
            if self.fallas:
                raise ValueError("una aprobada no puede tener fallas")
            if self.ruta_decision != "ia":
                raise ValueError("nunca se aprueba sin análisis de IA (ruta local/error)")
            if self.motivo_revision:
                raise ValueError("una aprobada no lleva motivo_revision")
        if self.decision == "rechazada":
            if not self.fallas or not self.reason_code:
                raise ValueError("una rechazada necesita al menos una falla y reason_code")
            mejor = min(self.fallas, key=lambda f: PRIORIDAD_FRENTE[f.frente])
            if self.reason_code != mejor.reason_code:
                raise ValueError(f"reason_code debe ser el de mayor prioridad: {mejor.reason_code}")
        if self.decision == "revision_manual" and not self.motivo_revision:
            raise ValueError("una revisión manual necesita motivo_revision")
        return self


# ───────────────────────── E6 · salida oficial ─────────────────────────
class ValidacionesOficiales(_Estricto):
    tienda_fachada: str
    producto: str
    codigo_barras: str
    evidencia_precio: str

    @model_validator(mode="after")
    def _valores(self):
        for k, v in self.model_dump().items():
            if v not in VALORES_VALIDACION_OFICIAL:
                raise ValueError(f"validaciones.{k}={v!r} no está en {VALORES_VALIDACION_OFICIAL}")
        return self


class RegistroSalida(_Estricto):
    """Formato oficial publicado. PENDIENTE_COMITE: confirmar nulos y reason_code en aprobada/revisión."""
    capture_id: str = Field(pattern=r"^CAP-\d+$")
    decision: Decision
    confidence_score: float = Field(ge=0, le=1)
    reason_code: Optional[str]
    validaciones: ValidacionesOficiales
    precio_detectado: Optional[float]
    codigo_barras_detectado: Optional[str]
    explicacion: str = Field(min_length=1, max_length=300)

    @model_validator(mode="after")
    def _rechazo_con_codigo(self):
        if self.decision == "rechazada" and not self.reason_code:
            raise ValueError("una rechazada necesita reason_code")
        return self


def a_oficial(d: DecisionInterna, explicacion: str) -> RegistroSalida:
    """E6: DecisionInterna → RegistroSalida. Único lugar donde se traducen valores internos."""
    conv = lambda v: "ok" if v == "ok" else "falla"  # PENDIENTE_COMITE: ¿existe un valor para "no determinable"?
    # PENDIENTE_COMITE: significado de confidence_score. Provisional: probabilidad que respalda la decisión;
    # en revisión, la de la alternativa más probable (baja = más duda).
    conf = {"aprobada": d.p_valida, "rechazada": 1 - d.p_valida}.get(d.decision, max(d.p_valida, 1 - d.p_valida))
    return RegistroSalida(
        capture_id=d.capture_id, decision=d.decision, confidence_score=round(conf, 3),
        reason_code=d.reason_code,
        validaciones=ValidacionesOficiales(**{k: conv(v) for k, v in d.validaciones.model_dump().items()}),
        precio_detectado=d.precio_detectado, codigo_barras_detectado=d.codigo_barras_detectado,
        explicacion=explicacion,
    )


def respaldo_revision(capture_id: str, motivo: MotivoRevision, explicacion: str) -> RegistroSalida:
    """Registro de respaldo cuando algo falla: siempre válido, siempre revision_manual."""
    return RegistroSalida(
        capture_id=capture_id, decision="revision_manual", confidence_score=0.0, reason_code=None,
        validaciones=ValidacionesOficiales(tienda_fachada="falla", producto="falla",
                                           codigo_barras="falla", evidencia_precio="falla"),
        precio_detectado=None, codigo_barras_detectado=None, explicacion=explicacion,
    )
