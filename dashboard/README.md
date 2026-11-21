# Dashboard — Responsable: Armando (rama `feat/dashboard`)

Página web **local** que lee los resultados del motor y las métricas de evaluación.
Solo usa la librería estándar de Python: no hay que instalar nada extra.

```bash
python dashboard/servidor.py            # abre http://127.0.0.1:8000
python dashboard/servidor.py --puerto 8080
python dashboard/servidor.py --resultados resultados/resultados_ciego.json --metricas resultados/metricas_ciego.json
```

Escucha solo en `127.0.0.1`: los resultados y las fotos del reto **no salen de la computadora**
(el dashboard no va en `web/`, que se publica en Cloudflare).

## Qué muestra
- Resumen: total, aprobadas, rechazadas y revisión manual (clic en una tarjeta = filtro).
- Métricas: precisión de aprobaciones y JSON válido contra su mínimo eliminatorio, costo operativo,
  tokens, llamadas e imágenes evitadas, costo por tipo de resultado, motivos más frecuentes,
  matriz de confusión, resultados por tanda y calidad del dato.
- Tabla: identificador, decisión, motivo, precio, confianza y explicación; filtro, búsqueda y orden.
- Detalle (clic en una fila): las tres fotos, validaciones, precio capturado vs detectado. ← → para navegar.
- Botón **Recargar**: lee de nuevo los archivos sin reiniciar el servidor.

## Vista previa con datos reales
Si todavía no existe `resultados/resultados.json` pero sí `cache/ingesta.json`, la página abre en **vista previa**:
las capturas reales sin decisión ("pendiente del motor"), con fotos, lo que vio la IA (`cache/hallazgos.json` o
`cache/ia/<id>.json`), las señales de cada foto y el panel **Uso de IA** (`cache/reporte_ia.json`,
`cache/reporte_ingesta.json`). El dashboard nunca decide. Para ver los ejemplos aunque haya caché:
`python dashboard/servidor.py --ejemplos`.

## De dónde lee (la primera que exista)
| Dato | Orden de búsqueda |
|---|---|
| Resultados (E6) | `--resultados` · `config.yaml → dashboard.resultados` · `resultados/resultados.json` · `ejemplos/resultados_ejemplo.json` |
| Decisión interna (E5) | `--decisiones` · `config.yaml → dashboard.decisiones` · `logs/corrida_*.jsonl` más reciente · `ejemplos/decisiones_<x>.jsonl` |
| Métricas | `--metricas` · `config.yaml → dashboard.metricas` · `resultados/metricas.json` · `ejemplos/metricas_<x>.json` |
| Capturas (E1) | `--capturas` · `config.yaml → dashboard.capturas` · `data/capturas.json` + `ejemplos/capturas_<x>.json` |
| Fotos | `cache/normalizadas/<tipo>/` y `data/imagenes/` (`<capture_id>_facade.jpg`, `_product.jpg`, `_shelf.jpg`) |

Si los resultados vienen de `ejemplos/`, la página muestra la etiqueta **Datos de ejemplo** o **Datos ficticios**
y busca sus "hermanos" (`decisiones_`, `metricas_`, `capturas_` con el mismo sufijo); nunca mezcla ejemplos con datos reales.

## Contratos que espera (ver `contratos/contratos.py`)

**Resultados (Pat, E6 `RegistroSalida`):** lista JSON con el formato oficial.
`capture_id`, `decision`, `confidence_score`, `reason_code`, `validaciones{tienda_fachada, producto,
codigo_barras, evidencia_precio}` (solo `ok`/`falla`), `precio_detectado`, `codigo_barras_detectado`, `explicacion`.

**Decisión interna (Pat, E5 `DecisionInterna`, una por línea en `logs/corrida_<id>.jsonl`):** el dashboard usa
`motivo_revision` (las revisiones traen `reason_code` vacío), `tipo_precio`, `ruta_decision` (ia / local / error),
`fallas` y `validaciones` internas (`no_determinable`). Es opcional: sin el log la página funciona, pero las
revisiones aparecen sin motivo.

Cuando una revisión viene de `respaldo_revision()` (error de IA, foto faltante o corrupta) la salida oficial
pone las 4 validaciones en `falla`; el detalle lo avisa y muestra el valor interno.

**Métricas (Ale) — propuesta, `resultados/metricas.json`:**
```json
{
  "total": 100,
  "umbrales": {"precision_aprobaciones_min": 0.97, "json_valido_min": 0.99},
  "precision_aprobaciones": 0.98,
  "json_validos_pct": 1.0,
  "costo_total": 30, "costo_por_captura": 0.3,
  "costo_desglose": {
    "correctas": {"n": 72, "costo_unitario": 0},
    "revision_manual": {"n": 21, "costo_unitario": 1},
    "rechazo_valida": {"n": 1, "costo_unitario": 3},
    "aprobacion_invalida": {"n": 0, "costo_unitario": 10}
  },
  "matriz_confusion": {"aprobada": {"aprobada": 23, "rechazada": 1, "revision_manual": 9}, "rechazada": {}, "revision_manual": {}},
  "calidad_dato": {"reason_code_acierto": 0.81, "precio_acierto": 0.88, "tipo_precio_acierto": 0.9},
  "tokens": {"entrada": 188000, "salida": 21000, "total": 209000, "por_captura": 2090},
  "llamadas": {"ia": 125, "evitadas": 175, "imagenes_enviadas": 225, "imagenes_evitadas": 75, "nota": "texto libre"},
  "por_tanda": [{"tanda": "Tanda noche", "total": 50, "costo": 19, "precision_aprobaciones": 1.0}]
}
```
Porcentajes como fracción (0.98 = 98%). Cualquier bloque que falte simplemente no se dibuja.

## Datos de prueba
```bash
# 17 situaciones de contratos/ejemplos → ejemplos/*_ejemplo.* (fuente por defecto)
python dashboard/preparar_ejemplos.py --contratos contratos/ejemplos

# 100 capturas ficticias con la misma forma (IDs CAP-8xxxxx), para probar volumen
python dashboard/generar_ficticios.py
python dashboard/servidor.py --resultados ejemplos/resultados_ficticios.json
```
