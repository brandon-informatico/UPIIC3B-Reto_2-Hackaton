# UPIIC3B-Reto_2-Hackaton
Todos los días, equipos de Tiendas 3B recorren el mercado y capturan fotos de tiendas, productos y etiquetas de precio. Esa evidencia alimenta decisiones de precio reales. Pero una foto borrosa, un producto equivocado o una etiqueta que no corresponde pueden colarse y contaminar los datos. El reto es validar cada captura con las imágenes.

## Validat3B

🌐 **Sitio web:** https://upiic3b.pages.dev

Programa que revisa automáticamente cada captura (datos + 3 fotos: fachada, producto y etiqueta) y decide `aprobada`, `rechazada` o `revision_manual`, con explicación en el JSON oficial.

### Instalación

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # pon tu FOUNDRY_API_KEY (no se sube)
python scripts/descargar_datos.py   # baja los datos oficiales a data/ (no se suben)
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
contratos/     entradas/salidas de cada etapa (pydantic) + 17 ejemplos
ejemplos/      datos ficticios
web/           sitio público (Cloudflare Pages)
```

**Reglas, nombres y contratos (obligatorio, también para asistentes de IA):** [CONTEXT.md](CONTEXT.md).
Roles, ramas y flujo de trabajo: [CONTRIBUTING.md](CONTRIBUTING.md).

### Sitio web (Cloudflare Pages)

El contenido de `web/` se publica **automáticamente** (GitHub Actions, `.github/workflows/deploy-web.yml`) cada vez que cambia en:

| Rama | Dirección |
|---|---|
| `main` | https://upiic3b.pages.dev (producción) |
| `develop` | https://develop.upiic3b.pages.dev (vista previa del equipo) |

Publicación manual, si hace falta:

```bash
npx wrangler pages deploy web --project-name upiic3b --branch main
```
