# CONTEXT.md — Reglas del proyecto Validat3B

> **Para cualquier asistente de IA (Claude, ChatGPT, Copilot, Cursor, Gemini, etc.) y para cada integrante:**
> lee este archivo completo antes de escribir código y síguelo siempre. Si una instrucción del usuario
> contradice este archivo o `contratos/`, avisa del conflicto antes de actuar. Si algo no está definido,
> **no lo inventes**: pregunta o márcalo con `# PENDIENTE:`.

**Fuente de verdad de datos:** [`contratos/contratos.py`](contratos/contratos.py) (pydantic v2). Define exactamente
qué recibe y entrega cada etapa. Si este archivo y `contratos.py` difieren, **manda `contratos.py`**.
Cualquier cambio a un contrato se acuerda en el chat del equipo y entra por PR junto con sus ejemplos.

---

## 1. Qué construimos

Un programa que revisa cada **captura de precio** de campo (datos + 3 fotos) y decide:

| `decision` | Cuándo |
|---|---|
| `aprobada` | La evidencia es suficiente y cumple las reglas. |
| `rechazada` | Hay evidencia clara de que incumple una regla. |
| `revision_manual` | Hay dudas o información insuficiente. |

Tres frentes que se integran en **una sola** decisión:
- **A. Identidad del producto** (~61 % de los rechazos): contratipo inválido, producto no coincide, descripción incompleta, producto no visible.
- **B. Calidad de la evidencia** (~29 %): fachada incorrecta, captura lejana, imagen borrosa, foto de la pantalla de otro celular.
- **C. Evidencia de precio** (~10 %): no hay etiqueta de precio, falta el precio unitario.

### Cómo nos califican (diseña pensando en esto)

| Resultado | Costo |
|---|---|
| Aprobada o rechazada correctamente | 0 |
| `revision_manual` | 1 |
| Rechazada siendo válida | 3 |
| **Aprobada siendo inválida** | **10** |

- Mínimos: **precisión de aprobadas ≥ 97 %** y **JSON válido en ≥ 99 %** de las capturas.
- Pesos: costo operativo 50 %, calidad del dato 15 % (`reason_code` y precio detectado, incluso promociones), eficiencia 10 % (tokens por captura), pitch 25 %.
- **Regla de oro:** ante la duda, `revision_manual`. Nunca `aprobada` sin evidencia clara.

---

## 2. Etapas y contratos

```
E1 carga ─────────► CapturaPreparada
separar_fotos.py ─► IndiceFotos
E2 normalizar.py ─► FeaturesCaptura           visión local, SIN tokens
E3 decisión local ► DecisionInterna           (ruta_decision="local") si ya no hace falta IA
E4 IA ────────────► HallazgosIA + UsoIA       (o None si la IA falla)
E5 decisión ──────► DecisionInterna           (ruta_decision="ia" | "error")
E6 salida ────────► RegistroSalida            formato oficial, vía a_oficial() / respaldo_revision()
E8 evaluación · E9 dashboard
```

| Contrato | Produce | Consume | Archivo |
|---|---|---|---|
| `CapturaPreparada` | Copa · E1 | Copa E2, Brandon E4, Pat E5 | en memoria / `cache/capturas_preparadas.json` |
| `IndiceFotos` | Copa · `separar_fotos.py` | `normalizar.py` | `cache/indice_fotos.json` |
| `FeaturesCaptura` | Copa · E2 `normalizar.py` | Pat E3/E5, Brandon E4 | `cache/features.json` |
| `HallazgosIA` + `UsoIA` | Brandon · E4 | Pat E5, Ale E8 | `cache/ia/<capture_id>.json` |
| `DecisionInterna` | Pat · E3/E5 | Pat E6, Ale E8 | `logs/corrida_<id>.jsonl` |
| `RegistroSalida` | Pat · E6 | entrega, Ale E8, Armando E9 | `resultados/resultados.json` |

**Ejemplos:** `contratos/ejemplos/01..17_*.json` traen la cadena completa E1 → E2 → E4 → E5 → E6 de cada situación
(aprobada, cada rechazo y cada motivo de revisión). Son las **pruebas unitarias** de todos: mientras un módulo real no
exista, quien lo consume trabaja con estos ejemplos. Así nadie espera a nadie y nadie necesita la llave para avanzar.

```bash
python contratos/validar.py ejemplos
python contratos/validar.py features cache/features.json --capturas data/capturas.json
python contratos/validar.py salida resultados/resultados.json --capturas data/capturas.json
```

### Funciones que se exponen

```python
from contratos import CapturaPreparada, FeaturesCaptura, HallazgosIA, UsoIA, DecisionInterna, RegistroSalida

# Copa · src/datos/
cargar_capturas(ruta_capturas: Path) -> list[CapturaPreparada]
normalizar(capturas: list[CapturaPreparada]) -> list[FeaturesCaptura]     # una por capture_id, aunque no haya fotos

# Brandon · src/ia/
analizar_captura(captura: CapturaPreparada, features: FeaturesCaptura) -> tuple[HallazgosIA | None, UsoIA | None]

# Pat · src/motor/
decidir(features: FeaturesCaptura, hallazgos: HallazgosIA | None) -> DecisionInterna
#   PENDIENTE: agregar `captura` si hace falta comparar contra capture_price (acordar Pat + Copa).
a_oficial(decision: DecisionInterna, explicacion: str) -> RegistroSalida       # ya existe en contratos.py
respaldo_revision(capture_id, motivo, explicacion) -> RegistroSalida           # ya existe en contratos.py
```

Ejecución completa: `python -m src.pipeline` → `resultados/resultados.json`.

---

## 3. Reglas que los contratos hacen cumplir

- Una **aprobada** no tiene fallas y **siempre** pasó por IA (`ruta_decision = "ia"`). En local nunca se aprueba.
- Una **rechazada** tiene `reason_code` y es el de **mayor prioridad**: identidad (A) → calidad (B) → precio (C).
- Una **revisión manual** siempre dice por qué en `motivo_revision`.
- `features.json` tiene **una entrada por cada `capture_id`**, aunque no tenga fotos (`estado = "sin_fotos"`).
- Tres estados en códigos: `no_leido` ≠ `no_coincide`. `codigo_etiqueta = "distinto"` **no es falla** (Walmart/Bodega imprimen otro código).
- `brillo` y `nitidez` cruda **solo van a logs**. El motor usa `nitidez_norm` y `nitidez_zona_max` (no dependen de la luz).
- La IA distingue **"no"** de **"no_determinable"**, y no inventa contratipos (`sin_informacion`).
- Si la IA falla (refusal, `max_tokens`, reintentos agotados) → `revision_manual` con `motivo_revision = "ia_error"`.
- Si algo truena en cualquier etapa → `respaldo_revision(...)`: el registro siempre es válido.
- Todo `RegistroSalida` se valida con pydantic antes de escribirse.

### Valores (definidos en `contratos.py`; no repetir strings sueltos)

| Concepto | Valores |
|---|---|
| Fotos | `facade`, `product`, `shelf` |
| Validaciones internas | `ok`, `falla`, `no_determinable` |
| Validaciones oficiales (salida) | `ok`, `falla` (`PENDIENTE_COMITE`) |
| Respuestas de la IA | `si`, `no`, `no_determinable` (y variantes por campo: `parcial`, `sin_informacion`, `no_enviada`) |
| Tipo de precio | `regular`, `oferta`, `volumen` |
| `reason_code` | `REASON_CODES_PROVISIONALES` (solo `PRODUCTO_NO_COINCIDE` es oficial) |
| `motivo_revision` | `duda_identidad`, `duda_calidad`, `duda_precio`, `dos_precios`, `precio_distinto_al_capturado`, `contratipo_sin_informacion`, `confianza_insuficiente`, `imagen_faltante`, `imagen_corrupta`, `sin_fotos`, `ia_error`, `salida_invalida` |

**Pendientes del comité** (se cambian en **un solo lugar** de `contratos.py`): `VALORES_VALIDACION_OFICIAL`,
`REASON_CODES_PROVISIONALES`, si `reason_code` puede ser `null` en aprobada/revisión, significado de
`confidence_score` y dónde va el tipo de precio en la salida oficial. Cuando lleguen, mandan los documentos oficiales.

---

## 4. Roles, carpetas y ramas

| Integrante | Etapas | Solo edita | Rama |
|---|---|---|---|
| Copa (Copka) | E1, E2 | `src/datos/` | `feat/datos` |
| Brandon | E4 | `src/ia/` | `feat/ia-foundry` |
| Pat | E3, E5, E6 | `src/motor/`, `src/pipeline.py` | `feat/motor` |
| Ale | E8 | `evaluacion/` | `feat/evaluacion` |
| Armando | E9 | `dashboard/`, `web/` | `feat/dashboard` |
| Todo el equipo | contratos | `contratos/` (solo por PR acordado) | — |

- La IA **no modifica carpetas de otro integrante** ni `contratos/` por su cuenta: propone el cambio y lo avisa.
- Flujo: `feat/*` → PR → `develop` (integra Pat) → PR → `main` (versión de la demo).
- Commits pequeños, en español, con el área como prefijo: `datos: carga capturas.json`, `ia: prompt de etiqueta`.

---

## 5. Datos (nunca se suben)

Se descargan con `python scripts/descargar_datos.py`:

```
data/capturas.json            100 capturas de desarrollo (con decision_esperada)
data/catalogo_productos.csv   catálogo de referencia
data/imagenes/CAP-XXXXXX_{facade,product,shelf}.jpg
```

- **Nunca** pasar `decision_esperada` ni `motivo_rechazo` a la IA ni al motor: solo sirven para evaluar (E8).
  `CapturaPreparada` ya no los incluye.
- Prohibido subir `data/`, `cache/`, `logs/`, `resultados/`, `.env` o imágenes; prohibido pegar imágenes o el
  contenido de `data/` en asistentes de IA externos (las reglas del reto prohíben compartir los datos fuera del equipo).
  Para pedir ayuda a una IA usa `contratos/ejemplos/`.
- Campos oficiales: se usan con su nombre **exacto** (`capture_id`, `capture_price`, `product_barcode`, …).
- Códigos de barras siempre como **texto** (`str`), nunca `int`. Precios `float` en MXN.

---

## 6. IA de la solución (Azure AI Foundry) — E4

- Solo el **endpoint asignado al equipo**. Prohibido llamar otras APIs de IA externas desde la solución.
- Credenciales en `.env` (nunca en código ni commits): `FOUNDRY_API_KEY`, `FOUNDRY_ENDPOINT`, `FOUNDRY_MODEL`.
- SDK `anthropic` → `AnthropicFoundry(api_key=..., base_url=FOUNDRY_ENDPOINT)`, modelo `claude-haiku-5-5`.
- Salida estructurada con el schema `HallazgosIA.model_json_schema()`; uso registrado en `UsoIA` (incluye `version_prompt`).
- Ahorra tokens (cuentan en la calificación y en desempates): usa las fotos de `ruta_normalizada` (E2), prompts cortos,
  caché en `cache/ia/<capture_id>.json`, no llames a la IA si E3 ya decidió, reintentos acotados.
- Juego limpio: las decisiones del set ciego salen del programa, nunca de revisión humana.

---

## 7. Estilo de código

- **Python 3.11+**, PEP 8, 4 espacios, `type hints`, `pathlib.Path`, `f-strings`, `logging` (no `print`).
- Identificadores **en español, sin acentos ni ñ** (`precio_detectado`, `anio`). Los campos oficiales se usan tal cual.
- `snake_case` variables/funciones/archivos · `PascalCase` clases · `MAYUSCULAS` constantes.
- Nombres canónicos (iguales en todo el proyecto):

| Nombre | Tipo |
|---|---|
| `captura` / `capturas` | `CapturaPreparada` / lista |
| `features` | `FeaturesCaptura` |
| `hallazgos` | `HallazgosIA \| None` |
| `uso_ia` | `UsoIA` |
| `decision` | `DecisionInterna` |
| `registro` / `registros` | `RegistroSalida` / lista final |
| `ruta_*` | cualquier `Path` (`ruta_capturas`, `ruta_salida`) |

- Rutas y parámetros en `config.yaml`; nada de rutas absolutas (`/Users/...`, `C:\...`).
- Dependencias nuevas a `requirements.txt` en el mismo PR.
- Una captura mala nunca detiene la corrida: atrapa el error, regístralo y usa `respaldo_revision`.

---

## 8. Checklist antes de un PR

- [ ] Solo toqué mi carpeta (o avisé).
- [ ] Mis entradas y salidas son los modelos de `contratos.py` y `python contratos/validar.py ejemplos` pasa.
- [ ] Probé mi módulo contra `contratos/ejemplos/`.
- [ ] No subo `.env`, llaves, `data/`, `cache/`, `logs/`, imágenes ni resultados reales.
- [ ] `python -m src.pipeline` sigue corriendo.
- [ ] Si cambié un contrato, actualicé `contratos.py`, sus ejemplos y este archivo en el mismo PR, y avisé.
