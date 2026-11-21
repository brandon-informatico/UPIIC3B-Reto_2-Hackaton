"""Servidor local del dashboard de Validat3B. Responsable: Armando (rama feat/dashboard).

Solo usa la librería estándar de Python: no hay que instalar nada.

    python dashboard/servidor.py                 # http://127.0.0.1:8000
    python dashboard/servidor.py --puerto 8080
    python dashboard/servidor.py --resultados resultados/resultados_ciego.json

Escucha solo en 127.0.0.1 (esta computadora): los resultados y las fotos del
reto no salen de la máquina.

Fuentes (en este orden; la primera que exista gana):
  resultados : --resultados | config.yaml dashboard.resultados | resultados/resultados.json
               | ejemplos/resultados_ejemplo.json   (los 17 casos de contratos/)
  decisiones : --decisiones | config.yaml dashboard.decisiones | logs/corrida_*.jsonl más reciente
               | "hermano" del archivo de resultados en ejemplos/ (decisiones_<x>.jsonl)
               -> decisión interna E5: motivo_revision, tipo_precio, ruta_decision, fallas
  métricas   : --metricas   | config.yaml dashboard.metricas   | resultados/metricas.json | hermano en ejemplos/
  capturas   : --capturas   | config.yaml dashboard.capturas   | data/capturas.json + hermano en ejemplos/
  imágenes   : rutas de cache/ingesta.json, cache/normalizadas/<tipo>/ y data/imagenes/
  ingesta    : cache/ingesta.json   (Copka: metadatos, señales de cada foto, fachada de cada captura)
  IA         : cache/hallazgos.json o cache/ia/<id>.json   (Brandon: lo que vio la IA y sus tokens)
  reportes   : cache/reporte_ia.json, cache/reporte_ingesta.json

Si no hay resultados del motor pero sí cache/ingesta.json, la página abre en VISTA PREVIA:
las capturas reales sin decisión ("pendiente del motor"). El dashboard nunca decide.

Si los resultados vienen de ejemplos/, la página muestra la etiqueta "Datos de ejemplo".
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import re
import sys
from datetime import datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

RAIZ = Path(__file__).resolve().parent.parent          # raíz del repo
ESTATICOS = Path(__file__).resolve().parent / "static"
ID_VALIDO = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")

# Nombre del tipo en la URL -> nombres posibles en archivos/carpetas
TIPOS = {
    "fachada": ["facade", "fachada"],
    "producto": ["product", "producto"],
    "etiqueta": ["shelf", "etiqueta", "anaquel"],
}
EXTENSIONES = (".jpg", ".jpeg", ".png", ".webp")


def leer_config() -> dict:
    archivo = RAIZ / "config.yaml"
    if not archivo.exists():
        return {}
    try:
        import yaml  # pyyaml ya está en requirements.txt
        datos = yaml.safe_load(archivo.read_text(encoding="utf-8")) or {}
        return datos.get("dashboard") or {}
    except Exception:
        return {}


def primera_existente(*candidatos) -> Path | None:
    for c in candidatos:
        if not c:
            continue
        p = Path(c)
        p = p if p.is_absolute() else RAIZ / p
        if p.exists():
            return p
    return None


def leer_json_flexible(ruta: Path):
    """Acepta lista JSON, objeto con lista adentro, objeto por capture_id o JSONL."""
    texto = ruta.read_text(encoding="utf-8-sig").strip()
    if not texto:
        return []
    try:
        datos = json.loads(texto)
    except json.JSONDecodeError:
        # JSONL: un objeto por línea; las líneas rotas se reportan, no tumban la página
        datos, rotas = [], 0
        for linea in texto.splitlines():
            linea = linea.strip()
            if not linea:
                continue
            try:
                datos.append(json.loads(linea))
            except json.JSONDecodeError:
                rotas += 1
        if rotas:
            datos.append({"capture_id": f"LINEAS_INVALIDAS_{rotas}", "_error": f"{rotas} líneas con JSON inválido"})
        return datos
    if isinstance(datos, list):
        return datos
    if isinstance(datos, dict):
        for clave in ("resultados", "capturas", "results", "items", "data"):
            if isinstance(datos.get(clave), list):
                return datos[clave]
        if all(isinstance(v, dict) for v in datos.values()):
            return [{"capture_id": k, **v} for k, v in datos.items()]
    return datos


class Fuentes:
    def __init__(self, args):
        cfg = leer_config()
        self.args, self.cfg = args, cfg
        self.ingesta = primera_existente(cfg.get("ingesta"), "cache/ingesta.json")
        self.hallazgos = primera_existente(cfg.get("hallazgos"), "cache/hallazgos.json")
        self.carpeta_ia = primera_existente("cache/ia")
        self.reporte_ia = primera_existente("cache/reporte_ia.json")
        self.reporte_ingesta = primera_existente("cache/reporte_ingesta.json")
        self.resultados = primera_existente(args.resultados, cfg.get("resultados"), "resultados/resultados.json")
        self.vista_previa = self.resultados is None and self.ingesta is not None and not args.ejemplos
        if self.resultados is None and not self.vista_previa:
            self.resultados = primera_existente("ejemplos/resultados_ejemplo.json", "ejemplos/resultados_ficticios.json")
        de_ejemplos = self.es_ficticio(self.resultados)
        self.decisiones = primera_existente(args.decisiones, cfg.get("decisiones"),
                                            None if de_ejemplos else self.ultimo_log(),
                                            *self.hermanos("decisiones", ".jsonl"))
        self.metricas = primera_existente(args.metricas, cfg.get("metricas"),
                                          None if de_ejemplos else "resultados/metricas.json",
                                          *self.hermanos("metricas", ".json"))
        explicita = primera_existente(args.capturas, cfg.get("capturas"))
        self.capturas = [explicita] if explicita else [
            p for p in (primera_existente("data/capturas.json"), primera_existente(*self.hermanos("capturas", ".json"))) if p]
        carpetas = cfg.get("imagenes") or ["cache/normalizadas", "data/imagenes", "ejemplos/imagenes"]
        self.carpetas_imagenes = [RAIZ / c if not Path(c).is_absolute() else Path(c) for c in carpetas]

    def hermanos(self, prefijo, ext):
        """ejemplos/resultados_ejemplo.json -> ejemplos/<prefijo>_ejemplo<ext> (acepta ficticios/ficticias)."""
        r = self.resultados
        if not r or not r.name.startswith("resultados_"):
            return []
        sufijo = r.stem[len("resultados_"):]
        variantes = [sufijo] + ([sufijo[:-2] + "as"] if sufijo.endswith("os") else [])
        return [r.parent / f"{prefijo}_{v}{ext}" for v in variantes]

    @staticmethod
    def ultimo_log():
        logs = sorted((RAIZ / "logs").glob("corrida_*.jsonl"), key=lambda p: p.stat().st_mtime)
        return logs[-1] if logs else None

    @staticmethod
    def es_ficticio(ruta: Path | None) -> bool:
        return bool(ruta) and "ejemplos" in ruta.parts

    def relativa(self, ruta: Path | None) -> str | None:
        if not ruta:
            return None
        try:
            return str(ruta.relative_to(RAIZ)).replace("\\", "/")
        except ValueError:
            return str(ruta)

    def precios_capturados(self) -> dict:
        salida = {}
        for cid, e in self.por_id(self.ingesta).items():
            c = e.get("captura") or {}
            salida[cid] = {"precio_capturado": c.get("capture_price"), "tienda": c.get("capture_store_name"),
                           "producto_esperado": c.get("product_name"), "marca": c.get("capture_brand")}
        for archivo in self.capturas:
            try:
                filas = leer_json_flexible(archivo)
            except Exception:
                continue
            for f in filas if isinstance(filas, list) else []:
                if not isinstance(f, dict) or "capture_id" not in f:
                    continue
                salida.setdefault(str(f["capture_id"]), {
                    "precio_capturado": f.get("capture_price", f.get("precio_capturado")),
                    "tienda": f.get("capture_store_name", f.get("store_chain", f.get("tienda"))),
                    "producto_esperado": f.get("product_name", f.get("descripcion", f.get("producto"))),
                    "marca": f.get("capture_brand"),
                })
        return salida

    def decisiones_internas(self) -> dict:
        """Decisión interna (E5) por capture_id; si hay varias líneas del mismo id gana la última."""
        if not self.decisiones:
            return {}
        try:
            filas = leer_json_flexible(self.decisiones)
        except Exception:
            return {}
        campos = ("motivo_revision", "tipo_precio", "ruta_decision", "fallas", "p_valida", "validaciones", "_descripcion")
        return {str(f["capture_id"]): {k: f.get(k) for k in campos}
                for f in (filas if isinstance(filas, list) else []) if isinstance(f, dict) and "capture_id" in f}

    _cache_json: dict = {}

    def por_id(self, ruta: Path | None) -> dict:
        """Lee una lista JSON con capture_id y la indexa; se vuelve a leer si el archivo cambió."""
        if not ruta or not ruta.exists():
            return {}
        clave = (str(ruta), ruta.stat().st_mtime)
        if clave not in self._cache_json:
            try:
                filas = leer_json_flexible(ruta)
            except Exception:
                filas = []
            self._cache_json[clave] = {str(f["capture_id"]): f for f in filas
                                       if isinstance(f, dict) and "capture_id" in f}
        return self._cache_json[clave]

    def ia_de(self, capture_id: str) -> dict | None:
        h = self.por_id(self.hallazgos).get(capture_id)
        if h is None and self.carpeta_ia:
            archivo = self.carpeta_ia / f"{capture_id}.json"
            if archivo.is_file():
                try:
                    d = json.loads(archivo.read_text(encoding="utf-8"))
                    h = {**(d.get("hallazgos") or {}), "uso_ia": d.get("uso_ia"), "error": d.get("error")}
                except Exception:
                    h = None
        return h

    def tecnico_de(self, capture_id: str) -> dict | None:
        """Hallazgos de la IA + señales locales de cada foto (sin rutas absolutas de otras máquinas)."""
        ia = self.ia_de(capture_id)
        ing = self.por_id(self.ingesta).get(capture_id)
        if not ia and not ing:
            return None
        senales = {}
        for k, v in ((ing or {}).get("senales") or {}).items():
            senales[k] = {a: b for a, b in v.items() if a != "ruta_normalizada"} if isinstance(v, dict) else v
        ia = dict(ia or {})
        uso = ia.pop("uso_ia", None)
        return {"ia": ia or None, "uso_ia": uso, "senales": senales or None,
                "estado_imagenes": (ing or {}).get("estado_imagenes"), "errores_ingesta": (ing or {}).get("errores")}

    def capturas_vista_previa(self) -> list:
        """Capturas reales sin decisión: solo lo que ya existe (ingesta + IA). No decide nada."""
        filas = []
        for cid, e in self.por_id(self.ingesta).items():
            ia = self.ia_de(cid) or {}
            precios = ia.get("precios_en_etiqueta") or []
            filas.append({
                "capture_id": cid, "decision": "pendiente", "confidence_score": None, "reason_code": None,
                "validaciones": {}, "precio_detectado": None, "codigo_barras_detectado": None,
                "explicacion": ia.get("duda_principal") or ("Sin dudas de la IA." if ia else "Sin análisis de IA."),
                "_precio_ia": precios[0]["valor"] if precios else None,
                "_ia": {k: v for k, v in ia.items() if k not in ("uso_ia", "capture_id")} or None,
            })
        return filas

    def buscar_imagen(self, capture_id: str, tipo: str) -> Path | None:
        e = self.por_id(self.ingesta).get(capture_id)
        if e:
            for clave in ("imagenes_normalizadas", "imagenes"):
                ruta = (e.get(clave) or {}).get(TIPOS[tipo][0])
                if ruta:
                    p = Path(ruta)
                    p = p if p.is_absolute() else RAIZ / p
                    if p.is_file():
                        return p
        nombres = TIPOS.get(tipo, [])
        for base in self.carpetas_imagenes:
            if not base.exists():
                continue
            for n in nombres:
                for ext in EXTENSIONES:
                    for cand in (base / n / f"{capture_id}{ext}",
                                 base / n / f"{capture_id}_{n}{ext}",
                                 base / f"{capture_id}_{n}{ext}",
                                 base / "imagenes" / f"{capture_id}_{n}{ext}"):
                        if cand.is_file():
                            return cand
        return None


def crear_manejador(fuentes: Fuentes):
    class Manejador(SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(ESTATICOS), **kw)

        def log_message(self, formato, *args):  # registro corto en consola
            sys.stderr.write(f"[{datetime.now():%H:%M:%S}] {formato % args}\n")

        def responder_json(self, datos, estado=HTTPStatus.OK):
            cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
            self.send_response(estado)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)

        def do_GET(self):
            ruta = unquote(urlparse(self.path).path)
            try:
                if ruta == "/api/salud":
                    return self.responder_json({"ok": True, "hora": datetime.now().isoformat(timespec="seconds")})
                if ruta == "/api/resultados":
                    return self.api_resultados()
                if ruta == "/api/metricas":
                    return self.api_metricas()
                if ruta == "/api/reportes":
                    return self.api_reportes()
                if ruta.startswith("/api/tecnico/"):
                    cid = ruta.rsplit("/", 1)[-1]
                    if not ID_VALIDO.match(cid):
                        return self.responder_json({"error": "petición inválida"}, HTTPStatus.BAD_REQUEST)
                    return self.responder_json({"capture_id": cid, "tecnico": fuentes.tecnico_de(cid)})
                if ruta.startswith("/api/imagen/"):
                    return self.api_imagen(ruta)
                if ruta.startswith("/api/"):
                    return self.responder_json({"error": "ruta no encontrada"}, HTTPStatus.NOT_FOUND)
            except Exception as e:  # nunca tumbar el servidor durante la demo
                return self.responder_json({"error": str(e)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return super().do_GET()

        def api_resultados(self):
            if fuentes.vista_previa:
                capturas = fuentes.capturas_vista_previa()
                extras = fuentes.precios_capturados()
                for c in capturas:
                    c["_meta"] = extras.get(c["capture_id"], {})
                mod = datetime.fromtimestamp(fuentes.ingesta.stat().st_mtime).isoformat(timespec="seconds")
                return self.responder_json({"fuente": fuentes.relativa(fuentes.ingesta), "ficticio": False,
                                            "vista_previa": True, "modificado": mod, "decisiones": None,
                                            "capturas": capturas})
            if not fuentes.resultados:
                return self.responder_json({"fuente": None, "ficticio": False, "capturas": [],
                                            "aviso": "No hay archivo de resultados todavía."})
            capturas = leer_json_flexible(fuentes.resultados)
            extras = fuentes.precios_capturados()
            internas = fuentes.decisiones_internas()
            for c in capturas:
                if isinstance(c, dict):
                    cid = str(c.get("capture_id"))
                    c.setdefault("_meta", extras.get(cid, {}))
                    c.setdefault("_interno", internas.get(cid))
                    ia = fuentes.ia_de(cid)
                    if ia:
                        c.setdefault("_ia", {k: v for k, v in ia.items() if k not in ("uso_ia", "capture_id")})
            mod = datetime.fromtimestamp(fuentes.resultados.stat().st_mtime).isoformat(timespec="seconds")
            return self.responder_json({
                "fuente": fuentes.relativa(fuentes.resultados),
                "ficticio": fuentes.es_ficticio(fuentes.resultados),
                "vista_previa": False,
                "modificado": mod,
                "decisiones": fuentes.relativa(fuentes.decisiones),
                "capturas": capturas,
            })

        def api_metricas(self):
            if not fuentes.metricas:
                return self.responder_json({"fuente": None, "ficticio": False, "metricas": None})
            datos = json.loads(fuentes.metricas.read_text(encoding="utf-8-sig"))
            return self.responder_json({
                "fuente": fuentes.relativa(fuentes.metricas),
                "ficticio": fuentes.es_ficticio(fuentes.metricas),
                "metricas": datos,
            })

        def api_reportes(self):
            def leer(p):
                try:
                    return json.loads(p.read_text(encoding="utf-8")) if p else None
                except Exception:
                    return None
            return self.responder_json({"ia": leer(fuentes.reporte_ia), "ingesta": leer(fuentes.reporte_ingesta),
                                        "fuente_ia": fuentes.relativa(fuentes.reporte_ia),
                                        "fuente_ingesta": fuentes.relativa(fuentes.reporte_ingesta)})

        def api_imagen(self, ruta):
            partes = ruta.strip("/").split("/")  # api, imagen, id, tipo
            if len(partes) != 4 or not ID_VALIDO.match(partes[2]) or partes[3] not in TIPOS:
                return self.responder_json({"error": "petición inválida"}, HTTPStatus.BAD_REQUEST)
            archivo = fuentes.buscar_imagen(partes[2], partes[3])
            if not archivo:
                return self.responder_json({"error": "sin imagen"}, HTTPStatus.NOT_FOUND)
            cuerpo = archivo.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", mimetypes.guess_type(archivo.name)[0] or "image/jpeg")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.send_header("Cache-Control", "max-age=300")
            self.end_headers()
            self.wfile.write(cuerpo)

    return Manejador


def main():
    p = argparse.ArgumentParser(description="Dashboard local de Validat3B")
    p.add_argument("--puerto", type=int, default=8000)
    p.add_argument("--resultados")
    p.add_argument("--metricas")
    p.add_argument("--capturas")
    p.add_argument("--ejemplos", action="store_true", help="usar los ejemplos aunque exista cache/ingesta.json")
    p.add_argument("--decisiones", help="log de decisiones internas (E5), p. ej. logs/corrida_01.jsonl")
    args = p.parse_args()

    fuentes = Fuentes(args)
    print("Validat3B · dashboard local")
    print(f"  resultados : {fuentes.relativa(fuentes.resultados) or '(ninguno)'}"
          + ("   → VISTA PREVIA con " + fuentes.relativa(fuentes.ingesta) if fuentes.vista_previa else ""))
    print(f"  ingesta/IA : {fuentes.relativa(fuentes.ingesta) or '-'} · {fuentes.relativa(fuentes.hallazgos) or fuentes.relativa(fuentes.carpeta_ia) or '-'}")
    print(f"  decisiones : {fuentes.relativa(fuentes.decisiones) or '(ninguno)'}")
    print(f"  métricas   : {fuentes.relativa(fuentes.metricas) or '(ninguno)'}")
    print(f"  capturas   : {', '.join(fuentes.relativa(c) for c in fuentes.capturas) or '(ninguno)'}")
    print(f"  abre       : http://127.0.0.1:{args.puerto}   (Ctrl+C para detener)")
    servidor = ThreadingHTTPServer(("127.0.0.1", args.puerto), crear_manejador(fuentes))
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")


if __name__ == "__main__":
    main()
