# UPIIC3B-Reto_2-Hackaton
Todos los días, equipos de Tiendas 3B recorren el mercado y capturan fotos de tiendas, productos y etiquetas de precio. Esa evidencia alimenta decisiones de precio reales. Pero una foto borrosa, un producto equivocado o una etiqueta que no corresponde pueden colarse y contaminar los datos. El reto es validar cada captura con las imágenes.

## Validat3B

Programa que revisa automáticamente cada captura (datos + 3 fotos: fachada, producto y etiqueta) y decide `aprobada`, `rechazada` o `revision_manual`, con explicación en el JSON oficial.

### Instalación

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # llena tus credenciales (no se sube)
```

### Ejecución

```bash
python -m src.pipeline
```

### Estructura

```
src/datos/     Copka    — carga y limpieza
src/ia/        Brandon  — Azure AI Foundry
src/motor/     Pat      — reglas y salida
src/pipeline.py Pat     — integra el flujo
evaluacion/    Ale      — métricas y calidad
dashboard/     Armando  — visualización
docs/          contratos, ficha y pitch
ejemplos/      datos ficticios
```

Roles, ramas y flujo de trabajo: ver [CONTRIBUTING.md](CONTRIBUTING.md).
