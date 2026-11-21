# Cómo trabajamos — Validat3B

> Antes de programar lee **[CONTEXT.md](CONTEXT.md)**: reglas, nombres y contratos que todos (y sus IA) seguimos.

## Roles y ramas

| Integrante | Área | Carpeta(s) | Rama |
|---|---|---|---|
| Pat | Motor e integración (E3, E5, E6) | `src/motor/`, `src/pipeline.py` | `feat/motor` |
| Brandon | IA y Azure AI Foundry (E4) | `src/ia/` | `feat/ia-foundry` |
| Armando | Dashboard y sitio (E9) | `dashboard/`, `web/` | `feat/dashboard` |
| Copka | Carga y visión local (E1, E2) | `src/datos/` | `feat/datos` |
| Ale | Evaluación y métricas (E8) | `evaluacion/` | `feat/evaluacion` |

## Flujo de ramas

```
feat/*  ──PR──▶  develop  ──PR──▶  main
```

- **`main`**: versión estable para la demo. Por acuerdo del equipo, solo entra por Pull Request desde `develop` (GitHub Free no permite bloquearlo en repos privados: respétalo tú).
- **`develop`**: integración. Por acuerdo del equipo, solo entra por Pull Request. Pat integra.
- **`feat/*`**: rama de cada integrante. Aquí sí haces push directo.

## Paso a paso (primera vez)

```bash
git clone https://github.com/brandon-informatico/UPIIC3B-Reto_2-Hackaton.git
cd UPIIC3B-Reto_2-Hackaton
git switch feat/TU-RAMA          # ej. feat/datos
python scripts/descargar_datos.py   # datos oficiales a data/ (no se suben)
pip install -r requirements.txt
python contratos/validar.py ejemplos   # los 17 ejemplos deben salir OK
```

## Ciclo de trabajo

```bash
git pull origin develop          # trae lo último de los demás
# ... trabaja en tu carpeta ...
git add .
git commit -m "datos: carga capturas.json"
git push                         # sube a tu rama feat/*
```

Luego en GitHub: **Pull Request de `feat/TU-RAMA` → `develop`**. Cambios pequeños y frecuentes.

## Reglas

1. Trabaja solo en tu carpeta; si necesitas tocar otra, avisa a su responsable.
2. **Nunca** subas `.env`, llaves, imágenes ni datos del reto (`data/`, `resultados/`, `cache/` ya están en `.gitignore`).
3. En `ejemplos/` solo datos ficticios.
4. Si una llave se sube por error, avisa de inmediato: borrar el archivo no la quita del historial y hay que rotarla.
