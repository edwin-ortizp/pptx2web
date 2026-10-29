"use strict";
/* Asistente pptx2web — UI sobre window.pywebview.api (definida en gui/app.py).
   No contiene lógica de conversión: solo orquesta llamadas al backend. */

const $ = (id) => document.getElementById(id);
const api = () => window.pywebview.api;

// variables de color editables (subconjunto legible para el usuario)
const COLOR_VARS = [
  ["--accent", "Acento", "Resaltados y barra activa"],
  ["--panel", "Panel lateral", "Fondo del sidebar"],
  ["--bg", "Fondo", "Lienzo detrás de la lámina"],
  ["--ink", "Texto", "Color de texto principal"],
  ["--muted", "Texto tenue", "Texto secundario"],
  ["--line", "Bordes", "Líneas y separadores"],
];

const TOTAL_STEPS = 8;

const DEFAULT_PEN = { colors: ["#e3342f", "#ffd60a", "#39b54a", "#2f6fed", "#ffffff"],
  penSize: 3, highlighterSize: 18, eraserSize: 28 };
const DEFAULT_POINTER = { size: 18, color: "#ff3b30" };

const state = {
  loaded: false,
  step: 0,
  themes: [],
  deck: null,
  config: {
    theme: "default",
    colors: {},
    layout: { sidebarSide: "left", panels: ["thumbnails"] },  // defaultPanel: lo decide resolve salvo que el usuario elija
    course: {},
    sections: [],
    pointer: { ...DEFAULT_POINTER },
    pen: { ...DEFAULT_PEN, colors: [...DEFAULT_PEN.colors] },
    activities: {},
  },
  activityRows: [],
  output: { scale: "2.0", quality: 82, format: "webp", zip: false, outDir: null },
};

let previewTimer = null;
const pendingUiErrors = [];

// ───────────────────────── navegación de pasos ─────────────────────────

function goStep(n) {
  if (n > 0 && !state.loaded) return;
  state.step = Math.max(0, Math.min(TOTAL_STEPS - 1, n));
  document.querySelectorAll(".pane").forEach((p) =>
    p.classList.toggle("active", +p.dataset.pane === state.step));
  document.querySelectorAll(".step").forEach((s) => {
    const i = +s.dataset.step;
    s.classList.toggle("active", i === state.step);
    s.classList.toggle("disabled", i > 0 && !state.loaded);
    s.classList.toggle("done", state.loaded && i < state.step);
  });
  $("nav-back").disabled = state.step === 0;
  $("nav-next").disabled = !state.loaded || state.step === TOTAL_STEPS - 1;
  renderDots();
  $("panel-scroll").scrollTop = 0;
}

function renderDots() {
  $("nav-dots").innerHTML = Array.from({ length: TOTAL_STEPS },
    (_, i) => `<i class="${i === state.step ? "on" : ""}"></i>`).join("");
}

// ───────────────────────── previsualización ─────────────────────────

function schedulePreview() {
  if (!state.loaded) return;
  clearTimeout(previewTimer);
  previewTimer = setTimeout(refreshPreview, 280);
}

async function refreshPreview() {
  if (!state.loaded) return;
  const res = await api().build_preview(state.config);
  if (res && res.ok) {
    const f = $("preview-frame");
    f.hidden = false;
    $("preview-empty").hidden = true;
    f.src = res.url;
    $("preview-tag").textContent = "actualizado";
  }
}

// ───────────────────────── paso 1: archivo ─────────────────────────

async function pickPptx() {
  const button = $("pick-pptx");
  if (button.disabled) return;
  button.disabled = true;
  try {
    const path = await api().pick_pptx();
    if (path) await loadDeck(path);
  } catch (error) {
    reportError(error);
    alert("No se pudo completar la operación. Consulta la carpeta de diagnóstico.");
  } finally {
    button.disabled = false;
  }
}

async function loadDeck(path) {
  try {
    $("preview-loading").hidden = false;
    $("preview-empty").hidden = true;
    $("preview-tag").textContent = "renderizando…";
    const res = await api().load_deck(path);
    $("preview-loading").hidden = true;
    if (!res || !res.ok) {
      $("preview-tag").textContent = "error";
      alert(res ? res.error : "No se pudo cargar el archivo");
      return;
    }
    state.deck = res;
    state.loaded = true;

    // si el .pptx ya traía config, adoptarla
    if (res.config) mergeExistingConfig(res.config);

    $("di-title").textContent = res.title;
    $("di-count").textContent = res.slideCount;
    $("deck-info").hidden = false;
    if (res.configPath) {
      $("di-config").textContent = res.configPath.split(/[\\/]/).pop();
      $("di-config-row").hidden = false;
    }
    $("badge-title").textContent = res.title;
    $("badge-sub").textContent = `${res.slideCount} láminas`;
    $("deck-badge").hidden = false;

    buildThemeCards();
    buildSwatches();
    renderSections();
    renderQuizzes();
    renderDeckWarnings();
    await refreshActivities();
    renderLinks();
    syncCourseInputs();
    syncSideSeg();
    syncDefaultPanelSeg();
    syncToolControls();

    goStep(1);
    await refreshPreview();
  } catch (error) {
    $("preview-tag").textContent = "error";
    reportError(error);
    alert("No se pudo cargar la presentación. Consulta la carpeta de diagnóstico.");
  } finally {
    $("preview-loading").hidden = true;
  }
}

function mergeExistingConfig(cfg) {
  state.config = {
    theme: cfg.theme || "default",
    colors: cfg.colors || {},
    layout: { sidebarSide: "left", panels: ["thumbnails"], ...(cfg.layout || {}) },
    course: cfg.course || {},
    sections: cfg.sections || [],
    pointer: { ...DEFAULT_POINTER, ...(cfg.pointer || {}) },
    pen: { ...DEFAULT_PEN, colors: [...DEFAULT_PEN.colors], ...(cfg.pen || {}) },
    activities: cfg.activities || {},
  };
}

// ───────────────────────── paso 2: tema y colores ─────────────────────────

function buildThemeCards() {
  const wrap = $("theme-cards");
  wrap.innerHTML = "";
  for (const t of state.themes) {
    const card = document.createElement("button");
    card.className = "theme-card" + (t.name === state.config.theme ? " active" : "");
    const dots = ["--panel", "--accent", "--ink", "--bg"]
      .map((v) => `<span style="background:${t.colors[v] || "#000"}"></span>`).join("");
    card.innerHTML = `<div class="tc-name">${t.name}</div><div class="tc-dots">${dots}</div>`;
    card.addEventListener("click", () => {
      state.config.theme = t.name;
      // los colores propios del usuario se respetan; el resto sale del tema
      buildThemeCards();
      buildSwatches();
      schedulePreview();
    });
    wrap.appendChild(card);
  }
}

function themeColors() {
  const t = state.themes.find((x) => x.name === state.config.theme);
  return t ? t.colors : {};
}

function buildSwatches() {
  const base = themeColors();
  const wrap = $("color-swatches");
  wrap.innerHTML = "";
  for (const [v, label, desc] of COLOR_VARS) {
    const value = state.config.colors[v] || base[v] || "#000000";
    const row = document.createElement("div");
    row.className = "swatch";
    row.innerHTML = `<input type="color" value="${toHex6(value)}">
      <div class="swatch-meta"><b>${label}</b><span>${desc}</span></div>`;
    row.querySelector("input").addEventListener("input", (e) => {
      state.config.colors[v] = e.target.value;
      schedulePreview();
    });
    wrap.appendChild(row);
  }
}

function toHex6(c) {
  if (/^#[0-9a-f]{3}$/i.test(c)) return "#" + c.slice(1).split("").map((x) => x + x).join("");
  return /^#[0-9a-f]{6}$/i.test(c) ? c : "#000000";
}

function syncSideSeg() {
  document.querySelectorAll("#side-seg button").forEach((b) =>
    b.classList.toggle("active", b.dataset.side === state.config.layout.sidebarSide));
}

function syncDefaultPanelSeg() {
  // si el usuario no eligió, refleja lo que hará config.resolve: "sections"
  // cuando hay secciones, si no "thumbnails"
  const hasSections = state.config.sections.length > 0;
  const current = state.config.layout.defaultPanel
    || (hasSections ? "sections" : "thumbnails");
  document.querySelectorAll("#default-panel-seg button").forEach((b) => {
    b.classList.toggle("active", b.dataset.panel === current);
    if (b.dataset.panel === "sections") b.disabled = !hasSections;
  });
  $("default-panel-help").hidden = hasSections;
}

// ───────────────────────── paso 3: secciones ─────────────────────────

function renderSections() {
  const wrap = $("sections");
  wrap.innerHTML = "";
  if (state.config.sections.length) {
    const head = document.createElement("div");
    head.className = "section-head";
    head.innerHTML = "<span>Título</span><span>Desde</span><span>Hasta</span><span></span>";
    wrap.appendChild(head);
  }
  state.config.sections.forEach((sec, i) => {
    const row = document.createElement("div");
    row.className = "section-row";
    row.innerHTML = `
      <input type="text" placeholder="Nombre de la sección" value="${escapeAttr(sec.title || "")}">
      <input type="number" class="from-to" min="1" max="${state.deck.slideCount}" value="${sec.from || ""}">
      <input type="number" class="from-to" min="1" max="${state.deck.slideCount}" value="${sec.to || ""}">
      <button class="row-del" title="Eliminar">×</button>`;
    const [title, from, to] = row.querySelectorAll("input");
    title.addEventListener("input", () => { sec.title = title.value; validateAndPreview(); });
    from.addEventListener("input", () => { sec.from = parseInt(from.value) || null; validateAndPreview(); });
    to.addEventListener("input", () => { sec.to = parseInt(to.value) || null; validateAndPreview(); });
    row.querySelector(".row-del").addEventListener("click", () => {
      state.config.sections.splice(i, 1);
      renderSections();
      validateAndPreview();
    });
    wrap.appendChild(row);
  });
}

function addSection() {
  const last = state.config.sections[state.config.sections.length - 1];
  const start = last ? Math.min((last.to || 0) + 1, state.deck.slideCount) : 1;
  state.config.sections.push({ title: "", from: start, to: state.deck.slideCount });
  renderSections();
  syncDefaultPanelSeg();
}

async function validateAndPreview() {
  const res = await api().validate_config(state.config);
  const msg = $("sections-msg");
  if (!res.ok) {
    msg.hidden = false;
    msg.className = "notice err";
    msg.textContent = res.error;
  } else if (res.warnings && res.warnings.length) {
    msg.hidden = false;
    msg.className = "notice warn";
    msg.textContent = res.warnings.join(" · ");
  } else {
    msg.hidden = true;
  }
  if (res.ok) schedulePreview();
  syncDefaultPanelSeg(); // habilitar/inhabilitar "Contenido" según haya secciones
}

// ──────────────── apariencia: puntero láser + dibujo ────────────────

function syncToolControls() {
  const p = state.config.pointer;
  $("pointer-color").value = toHex6(p.color || DEFAULT_POINTER.color);
  $("pointer-size").value = p.size || DEFAULT_POINTER.size;
  $("pointer-size-val").textContent = p.size || DEFAULT_POINTER.size;
  const pen = state.config.pen;
  $("pen-size").value = pen.penSize; $("pen-size-val").textContent = pen.penSize;
  $("hl-size").value = pen.highlighterSize; $("hl-size-val").textContent = pen.highlighterSize;
  $("er-size").value = pen.eraserSize; $("er-size-val").textContent = pen.eraserSize;
  renderPenSwatches();
}

function renderPenSwatches() {
  const wrap = $("pen-swatches");
  wrap.innerHTML = "";
  state.config.pen.colors.forEach((c, i) => {
    const sw = document.createElement("div");
    sw.className = "pen-swatch";
    sw.innerHTML = `<input type="color" value="${toHex6(c)}"><span class="pen-del" title="Quitar">×</span>`;
    sw.querySelector("input").addEventListener("input", (e) => {
      state.config.pen.colors[i] = e.target.value;
    });
    sw.querySelector(".pen-del").addEventListener("click", () => {
      if (state.config.pen.colors.length > 1) {
        state.config.pen.colors.splice(i, 1);
        renderPenSwatches();
      }
    });
    wrap.appendChild(sw);
  });
}

// ──────────────── pasos 4 y 5: quizzes y enlaces (solo lectura) ────────────────

function renderQuizzes() {
  const wrap = $("quizzes-list");
  wrap.innerHTML = "";
  const slides = state.deck.slides.filter((s) => s.quiz);
  renderSyntaxHelp("quiz", !slides.length);
  if (!slides.length) {
    wrap.innerHTML = `<div class="inter-empty">No se detectaron quizzes.<br>
      Se definen en las <b>notas</b> de la lámina con un bloque <code>[quiz]</code>.</div>`;
    return;
  }
  for (const s of slides) {
    const card = document.createElement("div");
    card.className = "inter-slide";
    let html = `<div class="inter-head">Lámina ${s.index} — ${escapeHtml(s.title)}</div>`;
    if (s.quiz.question) html += `<div class="inter-q">${escapeHtml(s.quiz.question)}</div>`;
    html += `<div class="inter-opts">`;
    for (const o of s.quiz.options) {
      html += `<div class="inter-opt ${o.correct ? "ok" : ""}">
        <span class="mark">${o.correct ? "✓" : "·"}</span>${escapeHtml(o.text)}</div>`;
    }
    html += `</div>`;
    const fb = [s.quiz.feedbackOk && `✓ ${s.quiz.feedbackOk}`, s.quiz.feedbackKo && `✕ ${s.quiz.feedbackKo}`]
      .filter(Boolean).join(" · ");
    if (fb) html += `<div class="inter-fb">${escapeHtml(fb)}</div>`;
    card.innerHTML = html;
    wrap.appendChild(card);
  }
}

// ───────────────────────── ayuda de sintaxis ─────────────────────────
// Única fuente de la ayuda: la usan las tarjetas de cada paso y el diálogo.
// Quien administra los PPT puede no tener el README: todo debe estar aquí.

const SYNTAX_HELP = {
  quiz: {
    title: "Quiz (pregunta con opciones)",
    template: `[quiz]
¿Cuál es el evento que inspecciona el incremento?
- Daily Scrum
+ Sprint Review
- Sprint Planning
ok: ¡Correcto! La Review inspecciona el incremento.
no: Repasa la sección de eventos de Scrum.`,
    rules: [
      "Va en las <b>notas del orador</b> y <b>[quiz]</b> debe ser lo primero.",
      "<b>+</b> marca la opción correcta (exactamente una); <b>-</b> las incorrectas. Mínimo 2 opciones.",
      "La pregunta es opcional (omítela si ya se ve en la lámina).",
      "<b>ok:</b> y <b>no:</b> son los mensajes al acertar o fallar (opcionales).",
    ],
  },
  activity: {
    title: "Actividad interactiva (artefacto HTML)",
    template: `[actividad: sprint-eventos | Ordena los eventos del Sprint]`,
    rules: [
      "Una línea en las <b>notas del orador</b>, en cualquier posición (puede ir con otras notas o con un quiz).",
      "Lo que va antes de <b>|</b> es el <b>alias</b>; lo de después, el texto del botón (opcional).",
      "Guarda el HTML como <b>actividades/sprint-eventos.html</b> junto al .pptx, o selecciónalo en el paso Actividades.",
      "Máximo una actividad por lámina. Si cambias el HTML, usa “Actualizar actividades” (no hace falta republicar).",
    ],
  },
  link: {
    title: "Enlaces",
    template: null,
    rules: [
      "No llevan sintaxis: usa <b>Insertar → Vínculo</b> en PowerPoint sobre un texto, forma o imagen.",
      "“Lugar de este documento” crea un enlace a otra lámina; una dirección web abre la página.",
    ],
  },
};

function syntaxCard(kind, open) {
  const h = SYNTAX_HELP[kind];
  const code = h.template
    ? `<pre class="syntax-code">${escapeHtml(h.template)}</pre>
       <button class="ghost-btn sm copy-btn" type="button">Copiar plantilla</button>`
    : "";
  const rules = h.rules.map((r) => `<li>${r}</li>`).join("");
  const wrap = document.createElement("details");
  wrap.className = "syntax-card";
  wrap.open = open;
  wrap.innerHTML = `<summary>¿Cómo se escribe? — ${escapeHtml(h.title)}</summary>
    <div class="syntax-body">${code}<ul class="syntax-rules">${rules}</ul></div>`;
  const btn = wrap.querySelector(".copy-btn");
  if (btn) btn.addEventListener("click", () => copyText(h.template, btn));
  return wrap;
}

// tarjeta del paso: abierta si el deck no trae nada de ese tipo
function renderSyntaxHelp(kind, open) {
  const host = document.querySelector(`[data-syntax="${kind}"]`);
  if (!host) return;
  host.innerHTML = "";
  host.appendChild(syntaxCard(kind, open));
}

function openSyntaxDialog() {
  const all = $("syntax-all");
  all.innerHTML = "";
  for (const kind of Object.keys(SYNTAX_HELP)) all.appendChild(syntaxCard(kind, true));
  $("syntax-dialog").showModal();
}

async function copyText(text, btn) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
  }
  const label = btn.textContent;
  btn.textContent = "✓ Copiada";
  setTimeout(() => { btn.textContent = label; }, 1500);
}

// avisos del deck (quiz malformado, actividad repetida…) en su paso
function renderDeckWarnings() {
  const warnings = state.deck.warnings || [];
  const show = (id, list) => {
    const box = $(id);
    box.hidden = !list.length;
    box.innerHTML = list.length
      ? `<b>Revisa en el PowerPoint:</b>` + list.map((w) => `<div>• ${escapeHtml(w)}</div>`).join("")
      : "";
  };
  show("quizzes-warn", warnings.filter((w) => /\[quiz\]/i.test(w)));
  show("activities-warn", warnings.filter((w) => /actividad/i.test(w)));
}

// ───────────────────────── actividades ─────────────────────────

const ACT_STATUS = {
  ok: ["ok", "✓ Lista"],
  missing_file: ["bad", "✕ Falta archivo"],
  unused: ["warn", "⚠ No citada en ninguna lámina"],
};

async function refreshActivities() {
  const res = await api().activity_status(state.config);
  const msg = $("activities-msg");
  if (!res || !res.ok) {
    msg.className = "notice err";
    msg.textContent = res ? res.error : "No se pudo revisar las actividades";
    msg.hidden = false;
    return;
  }
  msg.hidden = true;
  state.activityRows = res.rows;
  renderActivities();
}

function renderActivities() {
  const rows = state.activityRows;
  const wrap = $("activities-list");
  wrap.innerHTML = "";
  const cited = rows.filter((r) => r.slides.length);
  renderSyntaxHelp("activity", !rows.length);
  const ready = cited.filter((r) => r.status === "ok").length;
  $("activities-summary").textContent = cited.length
    ? `${ready} de ${cited.length} actividad(es) citadas están listas` : "";
  const stepLabel = document.querySelector('.step[data-step="4"] .step-l');
  stepLabel.textContent = cited.length && ready < cited.length
    ? `Actividades (${ready}/${cited.length})` : "Actividades";

  if (!rows.length) {
    wrap.innerHTML = `<div class="inter-empty">No se detectaron actividades.<br>
      Escribe en las <b>notas</b> de una lámina <code>[actividad: mi-alias]</code>
      (o <code>[actividad: mi-alias | Texto del botón]</code>) y pon el HTML en
      <code>actividades/mi-alias.html</code> junto al .pptx, o selecciónalo aquí.</div>`;
    return;
  }
  for (const r of rows) {
    const [cls, label] = ACT_STATUS[r.status];
    const card = document.createElement("div");
    card.className = "inter-slide act-row";
    const where = r.slides.length ? `Lámina ${r.slides.join(", ")}` : "Sin lámina";
    const file = r.resolved ? r.resolved.split(/[\\/]/).pop() : "—";
    card.innerHTML = `
      <div class="act-top">
        <span class="act-alias">${escapeHtml(r.alias)}</span>
        <span class="act-badge ${cls}">${label}</span>
      </div>
      <div class="act-meta">${escapeHtml(where)} · Archivo: <b>${escapeHtml(file)}</b>${r.auto ? " (carpeta actividades/)" : ""}</div>
      <div class="act-actions">
        <button class="ghost-btn sm" data-act="pick">${r.resolved ? "Cambiar HTML…" : "Seleccionar HTML…"}</button>
        ${r.resolved && !/^https?:/i.test(r.resolved) ? `<button class="link-btn" data-act="test">Probar</button>` : ""}
        ${r.file ? `<button class="link-btn" data-act="clear">quitar asociación</button>` : ""}
      </div>`;
    card.querySelector('[data-act="pick"]').addEventListener("click", () => pickActivity(r.alias));
    card.querySelector('[data-act="test"]')?.addEventListener("click", () => api().open_url(fileUrl(r.resolved)));
    card.querySelector('[data-act="clear"]')?.addEventListener("click", () => {
      delete state.config.activities[r.alias];
      onActivitiesChanged();
    });
    wrap.appendChild(card);
  }
}

function fileUrl(path) {
  return /^https?:/i.test(path) ? path : "file:///" + path.replace(/\\/g, "/").replace(/^\/+/, "");
}

async function pickActivity(alias) {
  try {
    const path = await api().pick_activity();
    if (!path) return;
    state.config.activities = state.config.activities || {};
    state.config.activities[alias] = { ...(state.config.activities[alias] || {}), file: path };
    await onActivitiesChanged();
  } catch (error) {
    reportError(error);
    alert("No se pudo seleccionar el archivo. Consulta la carpeta de diagnóstico.");
  }
}

async function onActivitiesChanged() {
  await refreshActivities();
  schedulePreview();
}

async function updateActivities() {
  const btn = $("update-activities");
  btn.disabled = true;
  const msg = $("activities-msg");
  try {
    const res = await api().update_activities({ config: state.config, outDir: state.output.outDir });
    msg.hidden = false;
    if (res && res.ok) {
      msg.className = "notice";
      msg.textContent = `✓ Actividades actualizadas en ${res.outDir}`;
      state.activityRows = res.rows;
      renderActivities();
    } else {
      msg.className = "notice err";
      msg.textContent = res ? res.error : "No se pudo actualizar";
    }
  } catch (error) {
    reportError(error);
  } finally {
    btn.disabled = false;
  }
}

function renderLinks() {
  const wrap = $("links-list");
  wrap.innerHTML = "";
  const slides = state.deck.slides.filter((s) => s.links && s.links.length);
  if (!slides.length) {
    wrap.innerHTML = `<div class="inter-empty">No se detectaron enlaces.<br>
      Son los <b>hipervínculos</b> que pongas en PowerPoint (a una web o a otra lámina).</div>`;
    return;
  }
  for (const s of slides) {
    const card = document.createElement("div");
    card.className = "inter-slide";
    let html = `<div class="inter-head">Lámina ${s.index} — ${escapeHtml(s.title)}</div>`;
    for (const lk of s.links) {
      const target = lk.href ? lk.href : (lk.slide ? `→ lámina ${lk.slide}` : "?");
      const type = lk.href ? "enlace" : "interno";
      html += `<div class="inter-link"><span class="lk-type">${type}</span>
        <span class="lk-target">${escapeHtml(target)}${lk.tooltip ? ` — ${escapeHtml(lk.tooltip)}` : ""}</span></div>`;
    }
    card.innerHTML = html;
    wrap.appendChild(card);
  }
}

// ───────────────────────── paso 4: curso ─────────────────────────

function syncCourseInputs() {
  $("course-title").value = state.config.course.title || "";
  const logo = state.config.course.logo;
  $("logo-name").textContent = logo ? logo.split(/[\\/]/).pop() : "Ninguno";
  $("clear-logo").hidden = !logo;
}

async function pickLogo() {
  const button = $("pick-logo");
  if (button.disabled) return;
  button.disabled = true;
  try {
    const path = await api().pick_logo();
    if (path) {
      state.config.course.logo = path;
      syncCourseInputs();
      schedulePreview();
    }
  } catch (error) {
    reportError(error);
    alert("No se pudo completar la operación. Consulta la carpeta de diagnóstico.");
  } finally {
    button.disabled = false;
  }
}

// ───────────────────────── paso 5: publicar ─────────────────────────

function setConverting(busy) {
  $("convert-btn").disabled = busy;
  $("pick-pptx").disabled = busy;
}

async function convert() {
  if ($("convert-btn").disabled) return;
  setConverting(true);
  $("result").hidden = true;
  $("progress-wrap").hidden = false;
  setProgress(4, "Iniciando…");
  try {
    const result = await api().convert({
      config: state.config,
      scale: parseFloat(state.output.scale),
      quality: state.output.quality,
      format: state.output.format,
      zip: state.output.zip,
      outDir: state.output.outDir,
    });
    if (!result || !result.started) throw new Error(result?.error || "No se pudo iniciar la conversión");
  } catch (error) {
    reportError(error);
    alert(error.message);
    $("progress-wrap").hidden = true;
  } finally {
    if ($("progress-wrap").hidden) setConverting(false);
  }
}

const STAGE_LABELS = {
  render: "Renderizando láminas con PowerPoint…",
  metadata: "Extrayendo metadatos…",
  media: "Procesando media…",
  images: "Optimizando imágenes…",
  package: "Empaquetando…",
  done: "Listo",
};

function setProgress(pct, label) {
  $("progress-bar").style.width = `${pct}%`;
  if (label) $("progress-label").textContent = label;
}

// recibe eventos del backend (gui/app.py → evaluate_js)
window.guiEvent = (event, payload) => {
  if (event === "progress") {
    const { stage, current, total } = payload;
    if (stage === "render" && current && total) {
      setProgress(5 + Math.round((current / total) * 60), `Renderizando lámina ${current} de ${total}…`);
    } else if (stage === "images" && current && total) {
      setProgress(70 + Math.round((current / total) * 18), `Optimizando imagen ${current} de ${total}…`);
    } else {
      const base = { metadata: 66, media: 68, images: 70, package: 95, done: 100 };
      setProgress(base[stage] ?? 5, STAGE_LABELS[stage] || "Procesando…");
    }
  } else if (event === "done") {
    setProgress(100, "Completado");
    showResult(payload);
    setConverting(false);
  } else if (event === "error") {
    $("progress-wrap").hidden = true;
    setConverting(false);
    alert("Error en la conversión:\n\n" + payload.message);
  } else if (event === "update-available") {
    showUpdateToast(payload);
  } else if (event === "themes-updated") {
    refreshThemes();
  }
};

// ───────────────────────── actualizaciones OTA ─────────────────────────

let pendingUpdate = null;

function showUpdateToast(update) {
  pendingUpdate = update;
  $("ota-msg").textContent = `Hay una nueva versión (${update.version}) disponible.`;
  $("ota-apply").disabled = false;
  $("ota-apply").textContent = "Actualizar ahora";
  $("ota-toast").hidden = false;
}

async function applyUpdate() {
  const button = $("ota-apply");
  if (button.disabled) return;
  button.disabled = true;
  try {
    if (!pendingUpdate) return;
    $("ota-apply").disabled = true;
    $("ota-apply").textContent = "Descargando…";
    const res = await api().apply_update(pendingUpdate);
    // si tuvo éxito la app se cierra sola; si no, restauramos el botón
    if (res && !res.ok) {
      alert(res.error || "No se pudo actualizar");
      $("ota-apply").disabled = false;
      $("ota-apply").textContent = "Actualizar ahora";
    }
  } catch (error) {
    reportError(error);
    alert("No se pudo completar la operación. Consulta la carpeta de diagnóstico.");
  } finally {
    button.disabled = false;
    button.textContent = "Actualizar ahora";
  }
}

async function refreshThemes() {
  state.themes = await api().list_themes();
  if (state.loaded) buildThemeCards();
}

function showResult(r) {
  state.lastResult = r;
  const mb = (r.imageBytes / 1024 / 1024).toFixed(1);
  let html = `<div>${r.slideCount} láminas · ${mb} MB${r.mediaCount ? ` · ${r.mediaCount} media` : ""}</div>`;
  html += `<div style="color:var(--muted);margin-top:4px">${r.outDir}</div>`;
  const acts = (r.activities || []).filter((a) => a.slides.length);
  if (acts.length) {
    const ok = acts.filter((a) => a.status === "ok").length;
    html += `<div style="margin-top:4px">Actividades incluidas: ${ok}${ok < acts.length ? ` · faltantes: ${acts.length - ok}` : ""}</div>`;
  }
  if (r.warnings && r.warnings.length) {
    html += `<div class="warn-line" style="margin-top:8px">${r.warnings.length} advertencia(s):</div>`;
    html += r.warnings.map((w) => `<div class="warn-line">• ${escapeHtml(w)}</div>`).join("");
  }
  $("result-body").innerHTML = html;
  $("result").hidden = false;
}

// ───────────────────────── utilidades ─────────────────────────

function escapeHtml(s) {
  return String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}
function escapeAttr(s) { return escapeHtml(s).replace(/"/g, "&quot;"); }

// ───────────────────────── arranque ─────────────────────────

function wire() {
  $("pick-pptx").addEventListener("click", pickPptx);
  $("update-activities").addEventListener("click", updateActivities);
  $("nav-back").addEventListener("click", () => goStep(state.step - 1));
  $("nav-next").addEventListener("click", () => goStep(state.step + 1));
  document.querySelectorAll(".step").forEach((s) =>
    s.addEventListener("click", () => goStep(+s.dataset.step)));

  document.querySelectorAll("#side-seg button").forEach((b) =>
    b.addEventListener("click", () => {
      state.config.layout.sidebarSide = b.dataset.side;
      syncSideSeg();
      schedulePreview();
    }));
  $("reset-colors").addEventListener("click", () => {
    state.config.colors = {};
    buildSwatches();
    schedulePreview();
  });

  // puntero láser
  $("pointer-color").addEventListener("input", (e) => { state.config.pointer.color = e.target.value; });
  $("pointer-size").addEventListener("input", (e) => {
    state.config.pointer.size = +e.target.value; $("pointer-size-val").textContent = e.target.value;
  });
  // dibujo
  $("pen-size").addEventListener("input", (e) => {
    state.config.pen.penSize = +e.target.value; $("pen-size-val").textContent = e.target.value;
  });
  $("hl-size").addEventListener("input", (e) => {
    state.config.pen.highlighterSize = +e.target.value; $("hl-size-val").textContent = e.target.value;
  });
  $("er-size").addEventListener("input", (e) => {
    state.config.pen.eraserSize = +e.target.value; $("er-size-val").textContent = e.target.value;
  });
  $("add-pen-color").addEventListener("click", () => {
    state.config.pen.colors.push("#ffffff");
    renderPenSwatches();
  });

  document.querySelectorAll("#default-panel-seg button").forEach((b) =>
    b.addEventListener("click", () => {
      if (b.disabled) return;
      state.config.layout.defaultPanel = b.dataset.panel;
      syncDefaultPanelSeg();
      schedulePreview();
    }));

  $("add-section").addEventListener("click", addSection);

  $("course-title").addEventListener("input", (e) => {
    state.config.course.title = e.target.value;
    schedulePreview();
  });
  $("pick-logo").addEventListener("click", pickLogo);
  $("clear-logo").addEventListener("click", () => {
    delete state.config.course.logo;
    syncCourseInputs();
    schedulePreview();
  });

  $("opt-scale").addEventListener("change", (e) => { state.output.scale = e.target.value; });
  $("opt-quality").addEventListener("input", (e) => {
    state.output.quality = +e.target.value; $("quality-val").textContent = e.target.value;
  });
  $("opt-format").addEventListener("change", (e) => { state.output.format = e.target.value; });
  $("opt-zip").addEventListener("change", (e) => { state.output.zip = e.target.checked; });
  $("pick-out").addEventListener("click", async () => {
    const button = $("pick-out");
    if (button.disabled) return;
    button.disabled = true;
    try {
      const d = await api().pick_output_dir();
      if (d) { state.output.outDir = d; $("out-name").textContent = d; }
    } catch (error) { reportError(error); alert("No se pudo abrir el selector de carpeta."); }
    finally { button.disabled = false; }
  });
  $("convert-btn").addEventListener("click", convert);
  $("open-result").addEventListener("click", () => state.lastResult && api().open_url(state.lastResult.indexUrl));
  $("open-folder").addEventListener("click", () => state.lastResult && api().open_folder(state.lastResult.outDir));

  $("ota-apply").addEventListener("click", applyUpdate);
  $("ota-dismiss").addEventListener("click", () => { $("ota-toast").hidden = true; });

  $("show-syntax").addEventListener("click", openSyntaxDialog);
  $("close-syntax").addEventListener("click", () => $("syntax-dialog").close());

  $("show-diagnostics").addEventListener("click", () => {
    $("diagnostics-dialog").showModal();
    refreshDiagnostics();
  });
  $("close-diagnostics").addEventListener("click", () => $("diagnostics-dialog").close());
  $("refresh-diagnostics").addEventListener("click", refreshDiagnostics);
  $("copy-diagnostics").addEventListener("click", async () => {
    const field = $("diagnostics-content");
    try {
      await navigator.clipboard.writeText(field.value);
      $("diagnostics-status").textContent = "Logs copiados. Puedes pegarlos en un mensaje a soporte.";
    } catch (error) {
      field.focus();
      field.select();
      $("diagnostics-status").textContent = "Pulsa Ctrl+C para copiar los logs seleccionados.";
    }
  });
  $("open-diagnostics").addEventListener("click", async () => {
    const result = await api().open_diagnostics();
    if (!result.ok) alert("Los logs están en: " + result.path);
  });
  renderDots();
}

async function boot() {
  setInterval(() => { api().diagnostic_heartbeat().catch(() => {}); }, 2000);
  api().diagnostic_heartbeat().catch(() => {});
  pendingUiErrors.splice(0).forEach(reportError);
  wire();
  state.themes = await api().list_themes();
  buildThemeCards();
  api().run_update_check();  // OTA en segundo plano (no bloquea la UI)
}

window.addEventListener("pywebviewready", boot);

function reportError(error) {
  if (!window.pywebview?.api) {
    if (pendingUiErrors.length < 20) pendingUiErrors.push(error);
    return;
  }
  Promise.resolve(api().report_ui_error(String(error?.message || error), String(error?.stack || ""))).catch(() => {});
}
window.addEventListener("error", event => reportError(event.error || event.message));
window.addEventListener("unhandledrejection", event => reportError(event.reason));

async function refreshDiagnostics() {
  const button = $("refresh-diagnostics");
  if (button.disabled) return;
  button.disabled = true;
  $("diagnostics-status").textContent = "Leyendo logs…";
  try {
    const result = await api().read_diagnostics();
    if (!result.ok) throw new Error(result.error);
    $("diagnostics-content").value = result.text;
    $("diagnostics-status").textContent = result.session + (result.truncated ? " · Últimos 256 KB. El historial completo está en la carpeta." : " · Sesión actual");
    $("diagnostics-content").scrollTop = $("diagnostics-content").scrollHeight;
  } catch (error) {
    reportError(error);
    $("diagnostics-status").textContent = "No se pudieron leer los logs. Usa Abrir carpeta.";
  } finally {
    button.disabled = false;
  }
}
