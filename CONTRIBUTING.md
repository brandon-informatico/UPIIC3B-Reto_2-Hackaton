# Cómo trabajamos — Validat3B

## Roles y ramas

| Integrante | Área | Carpeta(s) | Rama |
|---|---|---|---|
| Pat | Motor e integración | `src/motor/`, `src/pipeline.py` | `feat/motor` |
| Brandon | IA y Azure AI Foundry | `src/ia/` | `feat/ia-foundry` |
| Armando | Dashboard | `dashboard/` | `feat/dashboard` |
| Copka | Carga y limpieza | `src/datos/` | `feat/datos` |
| Ale | Evaluación y métricas | `evaluacion/` | `feat/evaluacion` |

## Flujo de ramas

```
feat/*  ──PR──▶  develop  ──PR──▶  main
```

- **`main`**: versión estable para la demo. Protegida: solo entra por Pull Request desde `develop`.
- **`develop`**: integración. Protegida: solo entra por Pull Request. Pat integra.
- **`feat/*`**: rama de cada integrante. Aquí sí haces push directo.

## Paso a paso (primera vez)

```bash
git clone https://github.com/brandon-informatico/UPIIC3B-Reto_2-Hackaton.git
cd UPIIC3B-Reto_2-Hackaton
git switch feat/TU-RAMA          # ej. feat/datos
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
