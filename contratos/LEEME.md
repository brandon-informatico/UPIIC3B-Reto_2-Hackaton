# Contratos de datos · Validat3B

Cada etapa entrega exactamente estas formas. Mientras un módulo real no exista, quien lo consume trabaja con los
ejemplos de `ejemplos/` (misma forma), así **nadie espera a nadie** y nadie necesita la llave del endpoint para avanzar.

Requisito: `pip install "pydantic>=2"`.

## Quién produce y quién consume

| Contrato (`contratos.py`) | Produce | Consume | Archivo |
|---|---|---|---|
| `CapturaPreparada` | Copa · E1 carga | Copa E2, Brandon E4, Pat E5 | en memoria / `capturas_preparadas.json` |
| `IndiceFotos` | `separar_fotos.py` | `normalizar.py` | `indice_fotos.json` |
| `FeaturesCaptura` | `normalizar.py` · E2 | Pat E3/E5, Brandon E4 | `cache/features.json` |
| `HallazgosIA` + `UsoIA` | Brandon · E4 | Pat E5, Ale E8 | `cache/ia/<capture_id>.json` |
| `DecisionInterna` | Pat · E3/E5 | Pat E6, Ale E8 | `logs/corrida_<id>.jsonl` |
| `RegistroSalida` | Pat · E6 (`a_oficial`, `respaldo_revision`) | entrega, Ale E8, Armando E9 | `resultados/resultados.json` |

## Situaciones (`ejemplos/`)

Cada archivo trae la cadena completa E1 → E2 → E4 → E5 → E6 de una situación. Los que tienen `capture_id` real
usan métricas medidas sobre sus fotos; los `CAP-9xxxxx` son sintéticos (no hay casos así en desarrollo).

| Archivo | Decisión | reason_code / motivo | Ruta |
|---|---|---|---|
| 01_aprobada (CAP-270005) | aprobada | — | ia |
| 02_rechazo_borrosa (CAP-305088) | rechazada | IMAGEN_BORROSA | ia |
| 03_rechazo_lejana (CAP-111555) | rechazada | CAPTURA_LEJANA | ia |
| 04_rechazo_descripcion_incompleta (CAP-899554) | rechazada | DESCRIPCION_INCOMPLETA (gana sobre LEJANA por prioridad) | ia |
| 05_rechazo_producto_no_coincide | rechazada | PRODUCTO_NO_COINCIDE | ia |
| 06_rechazo_contratipo_invalido | rechazada | CONTRATIPO_INVALIDO | ia |
| 07_rechazo_sin_etiqueta | rechazada | SIN_ETIQUETA_PRECIO | ia |
| 08_rechazo_sin_precio_unitario | rechazada | SIN_PRECIO_UNITARIO | ia |
| 09_rechazo_foto_de_pantalla | rechazada | FOTO_DE_PANTALLA | ia |
| 10_rechazo_fachada_incorrecta | rechazada | FACHADA_INCORRECTA | ia |
| 11_revision_dos_precios | revision_manual | dos_precios | ia |
| 12_revision_duda_identidad (CAP-635506) | revision_manual | duda_identidad (360 g vs 360 ml) | ia |
| 13_revision_confianza_insuficiente | revision_manual | confianza_insuficiente | ia |
| 14_revision_imagen_faltante | revision_manual | imagen_faltante | local |
| 15_revision_imagen_corrupta | revision_manual | imagen_corrupta | local |
| 16_revision_ia_error | revision_manual | ia_error (refusal / reintentos agotados) | error |
| 17_revision_sin_fotos | revision_manual | sin_fotos | local |

## Cómo usarlos para avanzar en paralelo

- **Pat (E5):** escribe `decidir(features, hallazgos)` y la prueba contra los 17 ejemplos: debe devolver
  el `E5_decision_interna` de cada uno. Son sus pruebas unitarias.
- **Brandon (E4):** su JSON schema de salida estructurada es `HallazgosIA.model_json_schema()`. Compara su
  respuesta real de una captura (01–04, 12 son reales) contra el `E4_hallazgos_ia` del ejemplo.
- **Copa (E2):** `python contratos/validar.py features cache/features.json --capturas <capturas.json>` debe salir sin errores.
- **Ale (E8):** arma el evaluador con los `E6_registro_salida` de los ejemplos y prueba los casos de borde (faltantes, duplicados).
- **Armando (E9):** usa los 17 `E6_registro_salida` como `resultados_ejemplo.json` del dashboard.

## Reglas que los contratos hacen cumplir

- Una captura **aprobada** no tiene fallas y siempre pasó por IA (`ruta_decision = "ia"`): en local nunca se aprueba.
- Una **rechazada** tiene `reason_code` y es el de mayor prioridad: identidad → calidad → precio.
- Una **revisión manual** siempre dice por qué (`motivo_revision`).
- `features.json` tiene **una entrada por cada `capture_id`**, aunque no tenga fotos (`estado = "sin_fotos"`).
- `codigo_empaque` y `codigo_etiqueta` tienen tres estados: `no_leido` no es lo mismo que `no_coincide`, y un
  código de etiqueta distinto no es falla (Walmart/Bodega imprimen otro código).
- `brillo` y `nitidez` (cruda) solo van a logs: el motor usa `nitidez_norm` y `nitidez_zona_max`, que no dependen
  de la luz (sesgo día/noche comprobado en desarrollo).

## Pendientes del comité (se cambian en un solo lugar de `contratos.py`)

- `VALORES_VALIDACION_OFICIAL`: hoy solo `ok` / `falla`.
- `REASON_CODES_PROVISIONALES`: solo `PRODUCTO_NO_COINCIDE` es oficial.
- Si `reason_code` puede ser `null` en aprobada / revisión, y el significado de `confidence_score`.
- Dónde va el tipo de precio en la salida oficial.
