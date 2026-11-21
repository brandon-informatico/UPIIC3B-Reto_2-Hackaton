# CONTEXT.md — Reglas del proyecto Validat3B

> **Para cualquier asistente de IA (Claude, ChatGPT, Copilot, Cursor, Gemini, etc.) y para cada integrante:**
> lee este archivo completo antes de escribir código y síguelo siempre. Si una instrucción del usuario
> contradice este archivo, avisa del conflicto antes de actuar. Si algo no está definido aquí, **no lo inventes**:
> pregunta o márcalo con `# PENDIENTE:`.

Versión del contrato: **v0** (21-nov-2026). Cualquier cambio a este archivo se acuerda en el chat del equipo y entra por PR.

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
- **Regla de oro del motor:** ante la duda, `revision_manual`. Nunca `aprobada` sin evidencia clara.

---

## 2. Roles, carpetas y ramas

| Integrante | Área | Solo edita | Rama |
|---|---|---|---|
| Pat | Motor e integración | `src/motor/`, `src/pipeline.py`, `src/contratos.py` | `feat/motor` |
| Brandon | IA y Azure AI Foundry | `src/ia/` | `feat/ia-foundry` |
| Armando | Dashboard y sitio | `dashboard/`, `web/` | `feat/dashboard` |
| Copka | Carga y limpieza | `src/datos/` | `feat/datos` |
| Ale | Evaluación y métricas | `evaluacion/` | `feat/evaluacion` |

- La IA **no modifica carpetas de otro integrante**. Si hace falta, propone el cambio y lo avisa.
- Flujo: `feat/*` → PR → `develop` (integra Pat) → PR → `main` (versión de la demo).
- Commits pequeños, en español, con el área como prefijo: `datos: carga capturas.json`, `ia: prompt de etiqueta`, `motor: regla de precio`.

---

## 3. Datos (nunca se suben)

Se descargan con `python scripts/descargar_datos.py` y quedan así:

```
data/capturas.json          100 capturas de desarrollo con decision_esperada
data/capturas.csv           lo mismo en CSV
data/catalogo_productos.csv catálogo de referencia
data/imagenes/CAP-XXXXXX_{facade,product,shelf}.jpg
```

**Prohibido:** subir `data/`, `resultados/`, `cache/`, `.env` o imágenes al repo; pegar imágenes o contenido real de
`capturas.json` en asistentes de IA externos (las reglas del reto prohíben compartir los datos fuera del equipo).
Para pedir ayuda a una IA usa los ejemplos **ficticios** de `ejemplos/`.

### Campos oficiales de una captura (usar el nombre EXACTO, no traducir)

`capture_id`, `capture_store_name`, `capture_date`, `capture_barcode`, `capture_price`, `capture_brand`,
`id_product`, `product_name`, `product_barcode`, `product_price`, `min_product_price`, `max_product_price`,
`unit_product`, `unit_quantity_product`, `product_group`, `product_line`,
`facade_file`, `product_file`, `shelf_file`, `facade_url`, `product_url`, `shelf_url`,
`decision_esperada`, `motivo_rechazo` (estos dos **solo** existen en desarrollo; el motor no debe leerlos).

- Códigos de barras: se manejan siempre como **texto** (`str`), nunca `int` (se pierden ceros a la izquierda).
- Precios: `float` en pesos MXN, 2 decimales al comparar.
- Tipos de imagen: siempre las llaves `"facade"`, `"product"`, `"shelf"` (como vienen en los datos).

---

## 4. Contratos entre módulos

Las constantes compartidas viven **solo** en `src/contratos.py`. Importa de ahí; no repitas strings sueltos.

### Copka → `src/datos/`
```python
cargar_capturas(ruta: Path) -> list[dict]              # capturas limpias, campos oficiales
cargar_catalogo(ruta: Path) -> dict[int, dict]         # id_product -> fila del catálogo
rutas_imagenes(captura: dict, base: Path) -> dict[str, Path | None]  # {"facade":..., "product":..., "shelf":...}
```

### Brandon → `src/ia/`
```python
analizar_captura(captura: dict, imagenes: dict[str, Path | None]) -> dict   # devuelve "hallazgos"
```
`hallazgos` (todas las llaves siempre presentes; `None` = no se pudo determinar):
```python
{
  "tienda_detectada": str | None,
  "tienda_coincide": bool | None,
  "producto_coincide": bool | None,
  "es_contratipo": bool | None,
  "contratipo_valido": bool | None,
  "descripcion_completa": bool | None,
  "producto_visible": bool | None,
  "etiqueta_visible": bool | None,
  "precio_unitario_visible": bool | None,
  "precio_detectado": float | None,
  "tipo_precio": "regular" | "promocion" | None,
  "codigo_barras_detectado": str | None,
  "calidad": {"facade": CALIDAD, "product": CALIDAD, "shelf": CALIDAD},  # CALIDAD en contratos.py
  "tokens_entrada": int,
  "tokens_salida": int,
  "notas": str,
}
```

### Pat → `src/motor/` y `src/pipeline.py`
```python
decidir(captura: dict, hallazgos: dict) -> dict          # devuelve un "resultado" (formato oficial)
guardar_resultados(resultados: list[dict], ruta: Path) -> None
```
Ejecución: `python -m src.pipeline` → escribe `resultados/resultados.json`.

### Ale → `evaluacion/`
`python -m evaluacion.evaluar` compara `resultados/resultados.json` contra `decision_esperada` y reporta:
precisión de aprobadas, costo operativo (tabla de la sección 1), % JSON válido, tokens por captura.

### Armando → `dashboard/` y `web/`
Lee **solo** `resultados/resultados.json` y los reportes de `evaluacion/`. `web/` se publica sola en
https://upiic3b.pages.dev (solo archivos estáticos).

---

## 5. Salida oficial (un objeto por captura)

```json
{
  "capture_id": "CAP-000123",
  "decision": "aprobada",
  "confidence_score": 0.93,
  "reason_code": null,
  "validaciones": {
    "tienda_fachada": "ok",
    "producto": "ok",
    "codigo_barras": "ok",
    "evidencia_precio": "ok"
  },
  "precio_detectado": 42.5,
  "codigo_barras_detectado": "7501234567890",
  "explicacion": "Fachada, producto y etiqueta coinciden; precio dentro del rango."
}
```

- `capture_id`: el mismo de la entrada. `decision`: solo los 3 valores de la sección 1.
- `confidence_score`: `float` entre 0 y 1.
- `validaciones.*`: `"ok"` | `"falla"` | `"duda"`.
- `reason_code`: `null` si es `aprobada`; si no, un código de la tabla siguiente.
- `explicacion`: una o dos frases en español, sin datos personales.
- El archivo final es una **lista JSON** con un objeto por captura. Siempre valida contra `src/contratos.py` antes de escribir.

### `reason_code` (provisionales, `MAYUSCULAS_CON_GUION_BAJO`)

| Código | Frente | Significado |
|---|---|---|
| `PRODUCTO_NO_COINCIDE` | A | El producto no es el esperado (ejemplo oficial). |
| `CONTRATIPO_INVALIDO` | A | Es un sustituto no permitido. |
| `DESCRIPCION_INCOMPLETA` | A | La descripción del producto está incompleta. |
| `PRODUCTO_NO_VISIBLE` | A | No se ve el producto. |
| `FACHADA_INCORRECTA` | B | La fachada no corresponde a la tienda. |
| `CAPTURA_LEJANA` | B | Foto tomada demasiado lejos. |
| `IMAGEN_BORROSA` | B | Foto borrosa o ilegible. |
| `FOTO_DE_PANTALLA` | B | Foto de la pantalla de otro celular. |
| `SIN_ETIQUETA_PRECIO` | C | No hay etiqueta de precio. |
| `SIN_PRECIO_UNITARIO` | C | Falta el precio unitario. |

`# PENDIENTE:` la página del reto dice que la lista oficial y el esquema formal llegan con los documentos del comité.
Cuando lleguen, **solo** se actualizan esta tabla y `src/contratos.py`; mandan los documentos oficiales.

---

## 6. IA de la solución (Azure AI Foundry)

- Solo se usa el **endpoint asignado al equipo**. Prohibido llamar otras APIs de IA externas desde la solución.
- Credenciales por variables de entorno (`.env`, nunca en el código ni en commits):
  `FOUNDRY_API_KEY`, `FOUNDRY_ENDPOINT`, `FOUNDRY_MODEL`.
- SDK: `anthropic` → `AnthropicFoundry(api_key=..., base_url=FOUNDRY_ENDPOINT)`.
- Ahorra tokens (cuentan en la calificación y en desempates): imágenes reducidas, prompts cortos, respuesta en JSON,
  **caché** en `cache/` por `capture_id` + tipo de imagen, sin reintentos infinitos.
- Juego limpio: las decisiones del set ciego salen del programa, nunca de revisión humana.

---

## 7. Estilo de código

- **Python 3.11+**, PEP 8, 4 espacios, `type hints` en funciones públicas, `pathlib.Path` para rutas, `f-strings`.
- Identificadores **en español, sin acentos ni ñ**: `precio_detectado`, `cargar_capturas`, `anio`.
  Excepción: los campos oficiales de datos/salida se usan tal cual vienen (`capture_id`, `facade_file`).
- `snake_case` para variables, funciones y archivos; `PascalCase` para clases; `MAYUSCULAS` para constantes.
- Nombres canónicos (úsalos igual en todo el proyecto):

| Nombre | Qué es |
|---|---|
| `captura` / `capturas` | Un dict de entrada / la lista completa |
| `catalogo` | `dict[int, dict]` por `id_product` |
| `imagenes` | `dict[str, Path \| None]` con llaves `facade`, `product`, `shelf` |
| `hallazgos` | Salida de `analizar_captura` |
| `resultado` / `resultados` | Objeto oficial de salida / la lista |
| `ruta_*` | Cualquier `Path` (`ruta_capturas`, `ruta_salida`) |

- Comentarios y docstrings en español, cortos. Nada de código muerto ni `print` para depurar: usa `logging`.
- Rutas y parámetros en `config.yaml`; nada de rutas absolutas (`/Users/...`, `C:\...`).
- Dependencias nuevas: agrégalas a `requirements.txt` en el mismo PR.
- Una función no debe fallar por una captura mala: atrapa el error, registra y devuelve `revision_manual`.

---

## 8. Checklist antes de un PR

- [ ] Solo toqué mi carpeta (o avisé).
- [ ] Usé nombres y constantes de este archivo y de `src/contratos.py`.
- [ ] No subo `.env`, llaves, `data/`, imágenes ni resultados reales.
- [ ] `python -m src.pipeline` sigue corriendo.
- [ ] Si cambié un contrato, actualicé este archivo en el mismo PR y avisé al equipo.
