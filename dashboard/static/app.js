// Dashboard Validat3B — sin dependencias. Todo el texto se inserta con textContent
// (las explicaciones vienen del modelo y no deben interpretarse como HTML).
"use strict";

const DECISIONES = {
  aprobada: { et: "Aprobadas", color: "var(--ok)", acento: "acento-ok" },
  rechazada: { et: "Rechazadas", color: "var(--bad)", acento: "acento-bad" },
  revision_manual: { et: "Revisión manual", color: "var(--warn)", acento: "acento-warn" },
};
const ETQ_DECISION = { aprobada: "aprobada", rechazada: "rechazada", revision_manual: "revisión manual", pendiente: "pendiente" };
const CORTO = { aprobada: "Aprob.", rechazada: "Rech.", revision_manual: "Revisión" };
// Razones en lenguaje normal (vista ejecutiva). Claves: reason_code y motivo_revision de contratos.py
const RAZONES = {
  PRODUCTO_NO_COINCIDE: "El producto no es el esperado", CONTRATIPO_INVALIDO: "Sustituto no permitido",
  DESCRIPCION_INCOMPLETA: "Etiqueta con descripción incompleta", PRODUCTO_NO_VISIBLE: "No se ve el producto",
  FACHADA_INCORRECTA: "La tienda no corresponde", CAPTURA_LEJANA: "Foto tomada de lejos",
  IMAGEN_BORROSA: "Foto borrosa", FOTO_DE_PANTALLA: "Foto tomada a una pantalla",
  SIN_ETIQUETA_PRECIO: "No se ve la etiqueta de precio", SIN_PRECIO_UNITARIO: "Falta el precio unitario",
  duda_identidad: "Duda sobre el producto", duda_calidad: "Calidad de foto dudosa", duda_precio: "Precio poco legible",
  dos_precios: "La etiqueta tiene dos precios", precio_distinto_al_capturado: "Precio distinto al capturado",
  contratipo_sin_informacion: "Sustituto sin información", confianza_insuficiente: "Confianza insuficiente para aprobar",
  imagen_faltante: "Falta una foto", imagen_corrupta: "Foto dañada", sin_fotos: "Sin fotos",
  ia_error: "No se pudo analizar", salida_invalida: "Error al procesar",
};
// El log del motor no trae motivo_revision: se reconoce por el texto fijo de la explicación (src/motor/salida.py)
const TEXTO_A_MOTIVO = [
  ["identidad o el contenido", "duda_identidad"], ["calidad de la evidencia no permite", "duda_calidad"],
  ["leer con claridad el precio", "duda_precio"], ["mas de un precio", "dos_precios"], ["más de un precio", "dos_precios"],
  ["no coincide con el capturado", "precio_distinto_al_capturado"], ["validar el contratipo", "contratipo_sin_informacion"],
  ["confianza necesaria", "confianza_insuficiente"], ["Falta al menos una", "imagen_faltante"],
  ["no se pudo abrir", "imagen_corrupta"], ["no tiene fotos", "sin_fotos"], ["analizar la evidencia con IA", "ia_error"],
  ["IA no devolvio", "ia_error"], ["IA no disponible", "ia_error"], ["Error interno", "salida_invalida"],
  ["No fue posible normalizar", "salida_invalida"],
];
function motivoDesdeTexto(t) {
  for (const [frase, m] of TEXTO_A_MOTIVO) if ((t || "").includes(frase)) return m;
  return null;
}
const RUTAS = { ia: "Análisis con IA", local: "Reglas locales (sin IA)", error: "Error (respaldo)" };
const RESPALDO = new Set(["imagen_faltante", "imagen_corrupta", "sin_fotos", "ia_error", "salida_invalida"]);
const FOTOS = [["fachada", "Fachada"], ["producto", "Producto"], ["etiqueta", "Etiqueta"]];
const VALIDACIONES = [["tienda_fachada", "Tienda / fachada"], ["producto", "Producto"],
                      ["codigo_barras", "Código de barras"], ["evidencia_precio", "Evidencia de precio"]];

const estado = { previa: false, capturas: [], filtro: "todas", texto: "", col: "capture_id", dir: 1, visibles: [], idx: -1 };

// ---------- utilidades ----------
function el(tag, attrs = {}, ...hijos) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "class") n.className = v;
    else if (k === "style") n.style.cssText = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v === true ? "" : v);
  }
  for (const h of hijos.flat()) if (h != null && h !== false) n.append(h instanceof Node ? h : String(h));
  return n;
}
const $ = (s) => document.querySelector(s);
const pct = (x, d = 1) => (x == null || isNaN(x) ? "—" : (x * 100).toFixed(d) + "%");
const num = (x) => (x == null || isNaN(x) ? "—" : Number(x).toLocaleString("es-MX"));
const dinero = (x) => (x == null || x === "" || isNaN(x) ? "—" : "$" + Number(x).toFixed(2));
const decClase = (d) => (DECISIONES[d] || d === "pendiente" ? "dec dec-" + d : "dec dec-otro");
const decTexto = (d) => ETQ_DECISION[d] || (d ? String(d) : "sin decisión");

async function pedir(url) {
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) throw new Error(url + " → " + r.status);
  return r.json();
}

// ---------- carga ----------
async function cargar() {
  $("#btn-recargar").disabled = true;
  try {
    const [res, met, rep] = await Promise.all([pedir("/api/resultados"), pedir("/api/metricas").catch(() => null),
                                               pedir("/api/reportes").catch(() => null)]);
    estado.previa = !!res.vista_previa;
    estado.capturas = (res.capturas || []).filter((c) => c && typeof c === "object");
    for (const c of estado.capturas) {  // motivo único: reason_code (rechazo) o motivo_revision (E5)
      c._motivo = c.reason_code || c._interno?.motivo_revision ||
        (c.decision === "revision_manual" ? motivoDesdeTexto(c.explicacion) : null);
      c._es_revision = !c.reason_code && !!c._motivo;
      c._razon = c.decision === "aprobada" ? "Todo coincide" : (RAZONES[c._motivo] || c._motivo ||
        (c.decision === "revision_manual" ? "Requiere revisión" : "—"));
    }
    const aviso = $("#aviso-ficticio");
    aviso.hidden = !(res.ficticio || (met && met.ficticio));
    aviso.textContent = /_ejemplo/.test(res.fuente || "") ? "Datos de ejemplo (contratos)" : "Datos ficticios";
    if (estado.previa) { aviso.hidden = false; aviso.textContent = "Vista previa · datos reales"; }
    const ap = $("#aviso-previa");
    ap.hidden = !estado.previa;
    ap.textContent = "Vista previa: todavía no hay resultados del motor. Se muestran las capturas reales sin decisión.";
    $("#fuente").textContent = res.fuente ? `${res.fuente} · ${horaLocal(res.modificado)}` : (res.aviso || "sin resultados");
    $("#fuente").title = res.decisiones ? "Decisión interna: " + res.decisiones : "Sin log de decisión interna";
    pintarResumen();
    pintarCumple(met, rep);
    pintarMetricas(met);
    pintarUso(rep);
    pintarChips();
    pintarTabla();
  } catch (e) {
    $("#fuente").textContent = "Error al cargar: " + e.message;
  } finally {
    $("#btn-recargar").disabled = false;
  }
}
function horaLocal(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(d) ? iso : d.toLocaleTimeString("es-MX", { hour: "2-digit", minute: "2-digit" });
}

// ---------- resumen ----------
function conteos() {
  const c = { aprobada: 0, rechazada: 0, revision_manual: 0, otro: 0 };
  for (const x of estado.capturas) c[DECISIONES[x.decision] ? x.decision : "otro"]++;
  return c;
}
function pintarResumen() {
  const c = conteos(), total = estado.capturas.length;
  const caja = $("#kpis"); caja.replaceChildren();
  if (estado.previa) {
    caja.append(kpi("Capturas reales", num(total), "ingeridas y analizadas por la IA", "acento-ink"));
    for (const [, d] of Object.entries(DECISIONES)) caja.append(kpi(d.et, "—", "pendiente del motor", d.acento));
    $("#barra-dist").replaceChildren();
    return;
  }
  caja.append(kpi("Total de capturas", num(total), c.otro ? `${c.otro} sin decisión válida` : "procesadas", "acento-ink"));
  for (const [k, d] of Object.entries(DECISIONES))
    caja.append(kpi(d.et, num(c[k]), total ? pct(c[k] / total) + " del total" : "—", d.acento, () => filtrar(k)));
  const barra = $("#barra-dist"); barra.replaceChildren();
  for (const [k, d] of Object.entries(DECISIONES))
    if (total && c[k]) barra.append(el("span", { style: `width:${(c[k] / total) * 100}%;background:${d.color}` }));
}
function kpi(etiqueta, valor, sub, acento = "", alClic, estadoMeta) {
  return el("div", { class: "kpi " + acento, style: alClic ? "cursor:pointer" : null, onclick: alClic },
    el("div", { class: "kpi-cab" }, el("span", { class: "et" }, etiqueta),
      estadoMeta ? el("span", { class: "estado " + (estadoMeta.ok ? "estado-ok" : "estado-bad") }, estadoMeta.texto) : null),
    el("div", { class: "v" }, valor), el("div", { class: "s" }, sub));
}

// ---------- métricas ----------
function pintarMetricas(resp) {
  const m = resp && resp.metricas;
  $("#metricas-vacio").hidden = !!m; $("#metricas").hidden = !m;
  $("#metricas-fuente").textContent = resp && resp.fuente ? "· " + resp.fuente : "";
  pintarMotivos();
  if (!m) return;
  const um = m.umbrales || {};
  const minPrec = um.precision_aprobaciones_min ?? 0.97, minJson = um.json_valido_min ?? 0.99;
  const caja = $("#kpis-metricas"); caja.replaceChildren();
  const p = m.precision_aprobaciones, j = m.json_validos_pct;
  caja.append(
    kpi("Precisión de aprobaciones", pct(p), `mínimo ${pct(minPrec, 0)} (eliminatorio)`, p >= minPrec ? "acento-ok" : "acento-bad", null,
        p == null ? null : { ok: p >= minPrec, texto: p >= minPrec ? "cumple" : "no cumple" }),
    kpi("JSON válido", pct(j), `mínimo ${pct(minJson, 0)} (eliminatorio)`, j >= minJson ? "acento-ok" : "acento-bad", null,
        j == null ? null : { ok: j >= minJson, texto: j >= minJson ? "cumple" : "no cumple" }),
    kpi("Costo operativo", num(m.costo_total), `${m.costo_por_captura ?? "—"} por captura`, "acento-ink"),
    kpi("Tokens", num(m.tokens?.total), `${num(m.tokens?.por_captura)} por captura`, "acento-ink"),
    kpi("Llamadas a IA evitadas", num(m.llamadas?.evitadas), `${num(m.llamadas?.ia)} llamadas hechas`, "acento-ink"),
    kpi("Imágenes evitadas", num(m.llamadas?.imagenes_evitadas), m.llamadas?.nota || `${num(m.llamadas?.imagenes_enviadas)} enviadas`, "acento-ink"),
  );

  // Costo por tipo de resultado
  const g = $("#graf-costo"); g.replaceChildren();
  const des = m.costo_desglose || {};
  const filas = [["correctas", "Correctas (0)", "var(--ok)"], ["revision_manual", "A revisión (1)", "var(--warn)"],
                 ["rechazo_valida", "Rechazó válida (3)", "var(--bad)"], ["aprobacion_invalida", "Aprobó inválida (10)", "var(--bad)"]];
  const costos = filas.map(([k]) => (des[k]?.n || 0) * (des[k]?.costo_unitario || 0));
  const maxN = Math.max(1, ...filas.map(([k]) => des[k]?.n || 0));
  filas.forEach(([k, et, color], i) => {
    const n = des[k]?.n || 0;
    g.append(hbar(et, n / maxN, `${n} · ${costos[i]}`, color, `${n} capturas, costo ${costos[i]}`));
  });
  g.append(el("p", { class: "muted small" }, "Formato: capturas · costo aportado."));

  // Matriz de confusión
  const mc = m.matriz_confusion, caj = $("#matriz"); caj.replaceChildren();
  if (mc) {
    const clases = Object.keys(DECISIONES);
    const t = el("table", { class: "mini" },
      el("thead", {}, el("tr", {}, el("th", {}, "Real \\ Motor"), clases.map((c) => el("th", {}, CORTO[c])))),
      el("tbody", {}, clases.map((r) => el("tr", {}, el("th", {}, CORTO[r]),
        clases.map((p) => el("td", { class: r === p ? "celda-ok" : (p === "aprobada" && (mc[r]?.[p] || 0) > 0 ? "celda-bad" : null) }, num(mc[r]?.[p] ?? 0)))))));
    caj.append(t, el("p", { class: "muted small" }, "En rojo: aprobaciones incorrectas (cuestan 10 cada una)."));
  } else caj.append(el("p", { class: "muted" }, "Sin matriz."));

  // Por tanda
  const tt = $("#tandas"); tt.replaceChildren();
  const tandas = m.por_tanda || [];
  if (tandas.length) {
    tt.append(el("table", { class: "mini" },
      el("thead", {}, el("tr", {}, el("th", {}, "Tanda"), el("th", {}, "Capturas"), el("th", {}, "Costo"), el("th", {}, "Precisión aprob."))),
      el("tbody", {}, tandas.map((x) => el("tr", {}, el("td", {}, x.tanda), el("td", {}, num(x.total)), el("td", {}, num(x.costo)),
        el("td", { class: x.precision_aprobaciones != null && x.precision_aprobaciones < minPrec ? "celda-bad" : null }, pct(x.precision_aprobaciones)))))));
  } else tt.append(el("p", { class: "muted" }, "Sin desglose por tanda."));
  if (m.calidad_dato) {
    const cd = m.calidad_dato;
    tt.append(el("h3", { style: "margin-top:16px" }, "Calidad del dato"),
      el("table", { class: "mini" }, el("tbody", {},
        el("tr", {}, el("td", {}, "reason_code correcto"), el("td", {}, pct(cd.reason_code_acierto))),
        el("tr", {}, el("td", {}, "Precio correcto"), el("td", {}, pct(cd.precio_acierto))),
        el("tr", {}, el("td", {}, "Tipo de precio correcto"), el("td", {}, pct(cd.tipo_precio_acierto))))));
  }
}
function hbar(etiqueta, frac, valor, color, titulo) {
  return el("div", { class: "hbar", title: titulo || null },
    el("span", { class: "lab" }, etiqueta),
    el("span", { class: "pista" }, el("span", { class: "relleno", style: `display:block;width:${Math.max(0, Math.min(1, frac)) * 100}%;background:${color}` })),
    el("span", { class: "n" }, valor));
}
function pintarMotivos() {
  const g = $("#graf-motivos"); g.replaceChildren();
  pintarSenales();
  const cuenta = new Map();
  for (const c of estado.capturas) {
    if (c.decision === "aprobada") continue;
    const k = c._razon || "Sin razón";
    const v = cuenta.get(k) || { n: 0, d: c.decision }; v.n++; cuenta.set(k, v);
  }
  const lista = [...cuenta.entries()].sort((a, b) => b[1].n - a[1].n).slice(0, 5);
  if (!lista.length) return g.append(el("p", { class: "muted" }, estado.previa ? "Disponible cuando el motor entregue resultados." : "Sin rechazos ni revisiones."));
  const max = lista[0][1].n;
  for (const [k, v] of lista)
    g.append(hbar(k, v.n / max, String(v.n), DECISIONES[v.d]?.color || "var(--neutral)", `${k}: ${v.n} (${decTexto(v.d)})`));
  g.append(el("p", { class: "muted small" }, "Rojo: rechazo · ámbar: revisión manual."));
}

// ---------- tabla ----------
function pintarChips() {
  const c = conteos(), caja = $("#chips"); caja.replaceChildren();
  const opciones = [["todas", `Todas (${estado.capturas.length})`],
    ...(estado.previa ? [] : Object.entries(DECISIONES).map(([k, d]) => [k, `${d.et} (${c[k]})`]))];
  for (const [k, et] of opciones)
    caja.append(el("button", { class: "chip", "aria-pressed": String(estado.filtro === k), onclick: () => filtrar(k) }, et));
}
function filtrar(k) {
  estado.filtro = estado.filtro === k && k !== "todas" ? "todas" : k;
  pintarChips(); pintarTabla();
}
function pintarTabla() {
  const q = estado.texto.trim().toLowerCase();
  let filas = estado.capturas.filter((c) =>
    (estado.filtro === "todas" || c.decision === estado.filtro) &&
    (!q || [c.capture_id, c._motivo, c._razon, c.explicacion, c.decision, c._meta?.producto_esperado, c._meta?.tienda].some((v) => String(v ?? "").toLowerCase().includes(q))));
  const { col, dir } = estado;
  filas.sort((a, b) => {
    const x = a[col], y = b[col];
    if (x == null && y == null) return 0; if (x == null) return 1; if (y == null) return -1;
    return (typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y), "es")) * dir;
  });
  estado.visibles = filas;
  document.querySelectorAll("#tabla th").forEach((th) => {
    th.classList.remove("orden-asc", "orden-desc");
    if (th.dataset.col === col) th.classList.add(dir > 0 ? "orden-asc" : "orden-desc");
  });
  const tb = $("#tabla tbody"); tb.replaceChildren();
  if (!filas.length) tb.append(el("tr", {}, el("td", { colspan: 4, class: "vacio" }, "Sin capturas para este filtro.")));
  filas.forEach((c, i) => tb.append(el("tr", { onclick: () => abrirDetalle(i), tabindex: 0, onkeydown: (e) => e.key === "Enter" && abrirDetalle(i) },
    el("td", { class: "id" }, c.capture_id ?? "—"),
    el("td", {}, el("span", { class: decClase(c.decision) }, decTexto(c.decision))),
    el("td", { class: "razon", title: c._motivo || "" }, c._razon ?? "—"),
    el("td", { class: "num" }, c.precio_detectado == null && c._precio_ia != null
        ? el("span", { class: "precio-ia", title: "Precio leído por la IA (no es decisión del motor)" }, dinero(c._precio_ia))
        : dinero(c.precio_detectado),
      c._interno?.tipo_precio && c._interno.tipo_precio !== "regular" ? el("div", { class: "tipo-precio" }, c._interno.tipo_precio) : null),
    el("td", { class: "num solo-tec" }, c.confidence_score == null ? "—" : Number(c.confidence_score).toFixed(2)),
    el("td", { class: "expl solo-tec" }, c.explicacion || c._error || ""))));
  $("#conteo").textContent = `· ${filas.length} de ${estado.capturas.length}`;
}

// ---------- detalle ----------
function abrirDetalle(i) {
  estado.idx = i;
  const c = estado.visibles[i]; if (!c) return;
  $("#det-id").textContent = c.capture_id ?? "—";
  const fotos = $("#det-fotos"); fotos.replaceChildren();
  for (const [tipo, et] of FOTOS) {
    const marco = el("div", { class: "marco" });
    const id = encodeURIComponent(c.capture_id ?? "");
    const img = el("img", { src: `/api/imagen/${id}/${tipo}`, alt: `${et} de ${c.capture_id}`, loading: "lazy",
      onclick: (e) => ampliar(e.target.src, e.target.alt) });
    img.addEventListener("error", () => marco.replaceChildren(el("div", { class: "sin" }, "Sin imagen disponible", el("br"), el("span", { class: "small" }, "(se mostrará al conectar las fotos)"))));
    marco.append(img);
    const v = c.validaciones || {};
    const clave = { fachada: "tienda_fachada", producto: "producto", etiqueta: "evidencia_precio" }[tipo];
    fotos.append(el("div", { class: "foto" }, marco, el("div", { class: "pie" }, el("b", {}, et), estadoVal(v[clave]))));
  }
  const meta = c._meta || {}, it = c._interno || {};
  const dif = meta.precio_capturado != null && c.precio_detectado != null ? Number(c.precio_detectado) - Number(meta.precio_capturado) : null;
  $("#det-datos").replaceChildren(el("h3", {}, "Datos"), el("dl", { class: "dl" },
    fila("Decisión", el("span", { class: decClase(c.decision) }, decTexto(c.decision))),
    fila("Razón", c._razon ?? "—"),
    ...(document.body.classList.contains("tecnica") ? [fila("reason_code", el("span", { class: "codigo" }, c.reason_code ?? "—"))] : []),
    ...(document.body.classList.contains("tecnica") ? [
      it.motivo_revision ? fila("Motivo de revisión", el("span", { class: "codigo motivo-rev" }, it.motivo_revision)) : null,
      fila("Confianza", c.confidence_score == null ? "—" : Number(c.confidence_score).toFixed(2)),
      it.ruta_decision ? fila("Ruta de decisión", RUTAS[it.ruta_decision] || it.ruta_decision) : null] : []),
    meta.tienda ? fila("Tienda", meta.tienda) : null,
    meta.producto_esperado ? fila("Producto esperado", meta.producto_esperado + (meta.marca ? ` · ${meta.marca}` : "")) : null,
    fila("Precio capturado", dinero(meta.precio_capturado)),
    fila("Precio detectado", el("span", { class: dif != null && Math.abs(dif) > 0.5 ? "bad-t" : null },
      dinero(c.precio_detectado) + (dif != null && Math.abs(dif) > 0.5 ? `  (dif. ${dif > 0 ? "+" : ""}${dif.toFixed(2)})` : ""))),
    (it.tipo_precio || c.tipo_precio) ? fila("Tipo de precio", it.tipo_precio || c.tipo_precio) : null,
    fila("Código detectado", el("span", { class: "codigo" }, c.codigo_barras_detectado ?? "—"))));
  const v = c.validaciones || {}, vi = it.validaciones || {};
  const respaldo = c.decision === "revision_manual" && (RESPALDO.has(it.motivo_revision) || (it.ruta_decision && it.ruta_decision !== "ia"));
  const caja = $("#det-val");
  caja.replaceChildren(...VALIDACIONES.map(([k, et]) => el("div", { class: "val" }, el("span", {}, et),
    el("span", {}, estadoVal(v[k]),
      vi[k] && vi[k] !== v[k] ? el("span", { class: "muted small solo-tec", title: "Valor interno del motor (E5)" }, "  · interno: ", estadoVal(vi[k])) : null))));
  if (respaldo)
    caja.prepend(el("div", { class: "aviso-respaldo" }, "Sin análisis completo · ", RUTAS[it.ruta_decision] || it.motivo_revision,
      ". Las validaciones en «falla» de la salida oficial son de respaldo, no hallazgos."));
  const fallas = it.fallas || [];
  if (fallas.length)
    caja.append(el("h3", { style: "margin-top:16px", class: "solo-tec" }, "Fallas detectadas"),
      ...fallas.map((f, n) => el("div", { class: "falla solo-tec" + (n === 0 ? " falla-principal" : "") },
        el("span", { class: "codigo" }, f.reason_code), el("span", { class: "muted small" }, ` ${f.frente?.replace("_", " · ") ?? ""} · fuente ${f.fuente ?? "?"}`),
        f.detalle ? el("div", { class: "muted small" }, f.detalle) : null)),
      fallas.length > 1 ? el("p", { class: "muted small solo-tec" }, "La primera es la que se reporta (prioridad identidad → calidad → precio).") : null);
  $("#det-expl").textContent = c.explicacion || c._error || "Sin explicación.";
  pintarTecnico(c.capture_id, i);
  $("#det-ant").disabled = i <= 0; $("#det-sig").disabled = i >= estado.visibles.length - 1;
  const d = $("#detalle"); if (!d.open) d.showModal();
}
function fila(dt, dd) { return [el("dt", {}, dt), el("dd", {}, dd)]; }
// ok = verde, falla = rojo, dudoso = ámbar; cualquier otro valor (p. ej. "no_legible") es informativo, en gris
const TEXTO_VAL = { no_legible: "no leído en foto", no_aplica: "no aplica", no_determinable: "no determinable" };
function estadoVal(x) {
  const s = String(x ?? "—");
  const cls = s === "ok" ? "ok-t" : s === "falla" ? "bad-t" : s === "dudoso" ? "warn-t" : "muted";
  const ico = s === "ok" ? "✓ " : s === "falla" ? "✕ " : s === "dudoso" ? "? " : "";
  return el("b", { class: cls, style: cls === "muted" ? "font-weight:500" : null }, ico + (TEXTO_VAL[s] || s.replace(/_/g, " ")));
}
function ampliar(src, alt) {
  const im = el("img", { src, alt, class: "ampliada", onclick: () => im.remove() });
  $("#detalle").append(im);
}

// ---------- ¿cumple el motor? (vista ejecutiva) ----------
function jsonValido(c) {  // misma forma que RegistroSalida (contratos.py), revisión rápida en el navegador
  const v = c.validaciones || {};
  return /^CAP-\d+$/.test(c.capture_id || "") && ["aprobada", "rechazada", "revision_manual"].includes(c.decision) &&
    typeof c.confidence_score === "number" && c.confidence_score >= 0 && c.confidence_score <= 1 &&
    ["tienda_fachada", "producto", "codigo_barras", "evidencia_precio"].every((k) => v[k] === "ok" || v[k] === "falla") &&
    typeof c.explicacion === "string" && c.explicacion.length > 0 && (c.decision !== "rechazada" || !!c.reason_code);
}
function pintarCumple(resp, rep) {
  const m = resp?.metricas, caja = $("#kpis-cumple"); caja.replaceChildren();
  const minPrec = m?.umbrales?.precision_aprobaciones_min ?? 0.97, minJson = m?.umbrales?.json_valido_min ?? 0.99;
  const meta = (ok, si = "cumple", no = "no cumple") => ({ ok, texto: ok ? "✓ " + si : "✕ " + no });
  // 1) precisión de aprobaciones: solo la puede calcular la evaluación (necesita las respuestas correctas)
  const p = m?.precision_aprobaciones;
  caja.append(p != null
    ? kpi("Precisión de aprobaciones", pct(p), `mínimo ${pct(minPrec, 0)}`, p >= minPrec ? "acento-ok" : "acento-bad", null, meta(p >= minPrec))
    : kpi("Precisión de aprobaciones", "—", `mínimo ${pct(minPrec, 0)} · pendiente de evaluación`, "acento-ink"));
  // 2) JSON válido: de la evaluación o, si no hay, revisado aquí sobre los resultados cargados
  let j = m?.json_validos_pct, sub = `mínimo ${pct(minJson, 0)}`;
  if (j == null && !estado.previa && estado.capturas.length) {
    j = estado.capturas.filter(jsonValido).length / estado.capturas.length; sub += " · revisado en el dashboard";
  }
  caja.append(j != null
    ? kpi("Registros con JSON válido", pct(j), sub, j >= minJson ? "acento-ok" : "acento-bad", null, meta(j >= minJson))
    : kpi("Registros con JSON válido", "—", sub + " · sin resultados aún", "acento-ink"));
  // 3) costo por captura (evaluación) o, mientras no exista, tokens por captura (eficiencia)
  if (m?.costo_por_captura != null)
    caja.append(kpi("Costo por captura", String(m.costo_por_captura), `costo total ${num(m.costo_total)} · menor es mejor`, "acento-ink"));
  else if (rep?.ia?.tokens_por_captura)
    caja.append(kpi("Tokens por captura", num(rep.ia.tokens_por_captura), "eficiencia · costo pendiente de evaluación", "acento-ink"));
  else caja.append(kpi("Costo por captura", "—", "pendiente de evaluación", "acento-ink"));
}
function aplicarVista(tecnica) {
  document.body.classList.toggle("tecnica", tecnica);
  $("#btn-tecnica").setAttribute("aria-pressed", String(tecnica));
  $("#btn-tecnica").textContent = tecnica ? "Vista ejecutiva" : "Vista técnica";
  try { localStorage.setItem("v3b_tecnica", tecnica ? "1" : "0"); } catch { /* sin almacenamiento */ }
  if ($("#detalle").open && estado.idx >= 0) abrirDetalle(estado.idx);
}

// ---------- uso de IA (reportes de Copka y Brandon) ----------
function pintarUso(rep) {
  const ia = rep?.ia, ing = rep?.ingesta;
  $("#sec-uso").hidden = !(ia || ing);
  if (!(ia || ing)) return;
  $("#uso-fuente").textContent = "· " + [rep.fuente_ia, rep.fuente_ingesta].filter(Boolean).join(" · ");
  const n = ia?.capturas || ing?.capturas || 0;
  const imgPorCap = ing?.tokens_imagen_aprox_total && n ? Math.round(ing.tokens_imagen_aprox_total / n) : null;
  const seg = (ia?.segundos || 0) + (ing?.segundos || 0);
  const fallasIA = ia?.fallas ? Object.values(ia.fallas).reduce((a, b) => a + b, 0) : 0;
  const caja = $("#kpis-uso"); caja.replaceChildren(
    kpi("Analizadas por la IA", ia ? `${num(ia.ia_ok)} / ${num(ia.capturas)}` : "—", fallasIA ? `${fallasIA} con error` : "sin errores", ia && ia.ia_ok === ia.capturas ? "acento-ok" : "acento-warn"),
    kpi("Tokens totales", num(ia?.tokens_total), `${num(ia?.tokens_por_captura)} por captura`, "acento-ink"),
    kpi("Entrada por captura", num(ia?.entrada_por_captura), imgPorCap ? `~${num(imgPorCap)} son imágenes` : "", "acento-ink"),
    kpi("Fachadas reutilizadas", ing?.fachadas_distintas != null ? num(n - ing.fachadas_distintas) : "—", ing?.fachadas_distintas != null ? `${ing.fachadas_distintas} únicas para ${n} capturas` : "", "acento-ink"),
    kpi("Tiempo total", seg ? `${Math.round(seg)} s` : "—", n && seg ? `${(seg / n).toFixed(1)} s por captura` : "", "acento-ink"),
    kpi("Reintentos de IA", num(ia?.reintentos), ia?.modo ? "prompt " + ia.modo : "", "acento-ink"),
  );
  const gt = $("#graf-tokens"); gt.replaceChildren();
  if (ia?.entrada_por_captura) {
    const partes = [["Imágenes (aprox.)", imgPorCap || 0, "var(--ok)"],
      ["Instrucciones y texto", Math.max(0, ia.entrada_por_captura - (imgPorCap || 0)), "var(--warn)"],
      ["Respuesta del modelo", ia.salida_por_captura || 0, "var(--neutral)"]];
    const max = Math.max(...partes.map((p) => p[1]), 1);
    partes.forEach(([et, v, col]) => gt.append(hbar(et, v / max, num(v), col)));
    gt.append(el("p", { class: "muted small" }, "Si el caché de instrucciones funcionara, la parte ámbar se cobraría mucho menos a partir de la segunda llamada."));
  } else gt.append(el("p", { class: "muted" }, "Sin reporte de IA."));
  const gc = $("#graf-codigos"); gc.replaceChildren();
  for (const [titulo, d] of [["Empaque (foto producto)", ing?.codigo_empaque], ["Etiqueta (foto anaquel)", ing?.codigo_etiqueta]]) {
    if (!d) continue;
    gc.append(el("div", { class: "small muted", style: "margin-top:6px" }, titulo));
    const tot = Object.values(d).reduce((a, b) => a + b, 0) || 1;
    const col = { coincide: "var(--ok)", no_coincide: "var(--bad)", distinto: "var(--warn)", no_leido: "var(--neutral)" };
    Object.entries(d).sort((a, b) => b[1] - a[1]).forEach(([k, v]) => gc.append(hbar(k.replace(/_/g, " "), v / tot, String(v), col[k] || "var(--neutral)")));
  }
  gc.append(el("p", { class: "muted small" }, "Leer el código es señal positiva; no leerlo no penaliza. «distinto» en etiqueta no es falla (Walmart/Bodega imprimen otro código)."));
}

const SENALES = [
  ["Precio unitario ausente", (h) => h.precio_unitario_presente === "no"],
  ["Etiqueta legible solo parcial o no", (h) => h.etiqueta_legible && h.etiqueta_legible !== "si"],
  ["Descripción incompleta o no determinable", (h) => h.descripcion_completa && h.descripcion_completa !== "si"],
  ["Contenido no coincide o no determinable", (h) => h.contenido_coincide && h.contenido_coincide !== "si"],
  ["Producto no aislado (posible lejana)", (h) => h.producto_aislado === "no"],
  ["Foto borrosa (sí o parcial)", (h) => h.foto_borrosa && h.foto_borrosa !== "no"],
  ["Descripción no coincide o no determinable", (h) => h.descripcion_coincide && h.descripcion_coincide !== "si"],
  ["Dos o más precios en etiqueta", (h) => (h.precios_en_etiqueta || []).length > 1],
  ["Fachada no coincide o no determinable", (h) => h.fachada_coincide && h.fachada_coincide !== "si"],
  ["Producto no coincide o no determinable", (h) => h.producto_coincide && h.producto_coincide !== "si"],
  ["Foto de pantalla", (h) => h.foto_de_pantalla === "si"],
];
function pintarSenales() {
  const conIA = estado.capturas.filter((c) => c._ia);
  $("#panel-senales").hidden = !conIA.length;
  const g = $("#graf-senales"); g.replaceChildren();
  if (!conIA.length) return;
  const filas = SENALES.map(([et, f]) => [et, conIA.filter((c) => f(c._ia)).length]);
  filas.forEach(([et, n]) => g.append(hbar(et, n / conIA.length, `${n}`, "var(--neutral)", `${n} de ${conIA.length} capturas`)));
  g.append(el("p", { class: "muted small" }, `Sobre ${conIA.length} capturas. Indican qué observó la IA; la decisión la toma el motor.`));
}

// ---------- análisis técnico del detalle ----------
const CAMPOS_IA = [  // [campo, etiqueta, valor "bueno"]
  ["fachada_coincide", "Fachada coincide", "si"], ["producto_visible", "Producto visible", "si"],
  ["producto_coincide", "Producto coincide", "si"], ["contenido_coincide", "Contenido coincide", "si"],
  ["producto_aislado", "Producto aislado (cerca)", "si"], ["foto_borrosa", "Foto borrosa", "no"],
  ["foto_de_pantalla", "Foto de pantalla", "no"], ["etiqueta_visible", "Etiqueta visible", "si"],
  ["etiqueta_legible", "Etiqueta legible", "si"], ["descripcion_completa", "Descripción completa", "si"],
  ["descripcion_coincide", "Descripción coincide", "si"], ["precio_unitario_presente", "Precio unitario presente", "si"],
  ["es_contratipo_permitido", "Contratipo permitido", null],
];
function valorIA(v, bueno) {
  const s = v == null ? "—" : String(v).replace(/_/g, " ");
  const cls = bueno == null || v == null ? "muted" : v === bueno ? "ok-t" : (v === "no_determinable" || v === "parcial" || v === "sin_informacion") ? "warn-t" : "bad-t";
  return el("b", { class: cls }, s);
}
const fmt = (x, d = 2) => (x == null || isNaN(x) ? "—" : Number(x).toFixed(d));
async function pintarTecnico(cid, idx) {
  const caja = $("#det-tec-cuerpo");
  caja.replaceChildren(el("p", { class: "muted small" }, "Cargando…"));
  let t = null;
  try { t = (await pedir(`/api/tecnico/${encodeURIComponent(cid)}`)).tecnico; } catch { t = null; }
  if (estado.idx !== idx) return;  // el usuario ya cambió de captura
  $("#det-tec").hidden = !t;
  if (!t) return caja.replaceChildren();
  const ia = t.ia || {}, uso = t.uso_ia || {}, sen = t.senales || {};
  const colIA = el("div", {}, el("h3", {}, "Lo que vio la IA"),
    ...(t.ia ? [
      el("div", { class: "val" }, el("span", {}, "Marca / contenido detectado"), el("b", {}, `${ia.marca_detectada ?? "—"} · ${ia.contenido_detectado ?? "—"}`)),
      ...CAMPOS_IA.map(([k, et, bueno]) => el("div", { class: "val" }, el("span", {}, et), valorIA(ia[k], bueno))),
      el("div", { class: "val" }, el("span", {}, "Precios en etiqueta"),
        el("b", {}, (ia.precios_en_etiqueta || []).map((p) => `${dinero(p.valor)} ${p.tipo}`).join(" · ") || "—")),
      ia.duda_principal ? el("div", { class: "duda" }, el("b", {}, "Duda principal: "), ia.duda_principal) : null,
      ia.error ? el("div", { class: "aviso-respaldo" }, "Error de IA: ", String(ia.error)) : null,
    ] : [el("p", { class: "muted" }, "Sin análisis de IA para esta captura.")]));
  const filaFoto = (tipo, et) => {
    const f = sen[tipo];
    if (!f) return el("tr", {}, el("td", {}, et), el("td", { colspan: 4, class: "muted" }, "sin datos"));
    const cods = (f.codigos_leidos || []).map((c) => `${c.texto} (${c.formato})`).join(", ");
    return el("tr", {}, el("td", {}, et + (f.repetida ? " · repetida" : "")), el("td", {}, f.final_wh ?? "—"),
      el("td", {}, num(f.tokens_aprox)), el("td", {}, fmt(f.nitidez_norm)), el("td", {}, fmt(f.nitidez_zona_max)),
      el("td", { class: "codigo", style: "text-align:left" }, f.codigos_leidos == null ? "—" : (cods || "ninguno")));
  };
  const colSen = el("div", {}, el("h3", {}, "Señales de las fotos (local, sin tokens)"),
    el("table", { class: "mini" },
      el("thead", {}, el("tr", {}, ["Foto", "Tamaño", "Tokens", "Nitidez", "Zona máx.", "Códigos"].map((x) => el("th", {}, x)))),
      el("tbody", {}, filaFoto("facade", "Fachada"), filaFoto("product", "Producto"), filaFoto("shelf", "Etiqueta"))),
    el("div", { class: "val", style: "margin-top:8px" }, el("span", {}, "Parecido producto–etiqueta"), el("b", {}, fmt(sen.parecido_producto_etiqueta))),
    el("div", { class: "val" }, el("span", {}, "Código en empaque / en etiqueta"), el("b", {}, `${(sen.codigo_empaque ?? "—").replace(/_/g, " ")} / ${(sen.codigo_etiqueta ?? "—").replace(/_/g, " ")}`)),
    el("h3", { style: "margin-top:14px" }, "Llamada a la IA"),
    t.uso_ia ? el("div", {},
      el("div", { class: "val" }, el("span", {}, "Tokens entrada / salida"), el("b", {}, `${num(uso.input_tokens)} / ${num(uso.output_tokens)}`)),
      el("div", { class: "val" }, el("span", {}, "Leídos del caché"), el("b", { class: uso.cache_read_input_tokens ? "ok-t" : "muted" }, num(uso.cache_read_input_tokens ?? 0))),
      el("div", { class: "val" }, el("span", {}, "Latencia · intentos"), el("b", {}, `${fmt((uso.latencia_ms || 0) / 1000, 1)} s · ${uso.intentos ?? "—"}`)),
      el("div", { class: "val" }, el("span", {}, "Modelo · prompt"), el("b", {}, `${uso.modelo ?? "—"} · ${uso.version_prompt ?? "—"}`)),
      el("div", { class: "val" }, el("span", {}, "Fin de respuesta"), el("b", { class: uso.stop_reason === "end_turn" ? "ok-t" : "bad-t" }, uso.stop_reason ?? "—")))
      : el("p", { class: "muted" }, "Sin datos de la llamada."));
  caja.replaceChildren(el("div", { class: "tec" }, colIA, colSen));
}

// ---------- eventos ----------
$("#btn-recargar").addEventListener("click", cargar);
$("#btn-tecnica").addEventListener("click", () => aplicarVista(!document.body.classList.contains("tecnica")));
try { aplicarVista(localStorage.getItem("v3b_tecnica") === "1"); } catch { aplicarVista(false); }
$("#buscar").addEventListener("input", (e) => { estado.texto = e.target.value; pintarTabla(); });
document.querySelectorAll("#tabla th").forEach((th) => th.addEventListener("click", () => {
  estado.dir = estado.col === th.dataset.col ? -estado.dir : 1; estado.col = th.dataset.col; pintarTabla();
}));
$("#det-cerrar").addEventListener("click", () => $("#detalle").close());
$("#det-ant").addEventListener("click", () => abrirDetalle(estado.idx - 1));
$("#det-sig").addEventListener("click", () => abrirDetalle(estado.idx + 1));
$("#detalle").addEventListener("click", (e) => { if (e.target.id === "detalle") e.target.close(); });
document.addEventListener("keydown", (e) => {
  if (!$("#detalle").open) return;
  const amp = document.querySelector("img.ampliada");
  if (e.key === "Escape" && amp) { e.preventDefault(); amp.remove(); return; }
  if (e.key === "ArrowLeft" && estado.idx > 0) abrirDetalle(estado.idx - 1);
  if (e.key === "ArrowRight" && estado.idx < estado.visibles.length - 1) abrirDetalle(estado.idx + 1);
});

cargar();
