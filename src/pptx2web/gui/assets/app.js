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

const TOTAL_STEPS = 6;

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
    layout: { sidebarSide: "left", panels: ["thumbnails"], defaultPanel: "thumbnails" },
    course: {},
    sections: [],
    pointer: { ...DEFAULT_POINTER },
    pen: { ...DEFAULT_PEN, colors: [...DEFAULT_PEN.colors] },
  },
  output: { scale: "2.0", quality: 82, format: "webp", zip: false, outDir: null },
};

let previewTimer = null;

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
  const path = await api().pick_pptx();
  if (path) loadDeck(path);
}

async function loadDeck(path) {
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
  renderInteractivity();
  syncCourseInputs();
  syncSideSeg();
  syncToolControls();

  goStep(1);
  refreshPreview();
}

function mergeExistingConfig(cfg) {
  state.config = {
    theme: cfg.theme || "default",
    colors: cfg.colors || {},
    layout: { sidebarSide: "left", panels: ["thumbnails"], defaultPanel: "thumbnails", ...(cfg.layout || {}) },
    course: cfg.course || {},
    sections: cfg.sections || [],
    pointer: { ...DEFAULT_POINTER, ...(cfg.pointer || {}) },
    pen: { ...DEFAULT_PEN, colors: [...DEFAULT_PEN.colors], ...(cfg.pen || {}) },
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

// ──────────────── paso 4: interactividad (solo lectura) ────────────────

function renderInteractivity() {
  const wrap = $("interactivity");
  wrap.innerHTML = "";
  const withStuff = state.deck.slides.filter((s) => s.quiz || (s.links && s.links.length));
  if (!withStuff.length) {
    wrap.innerHTML = `<div class="inter-empty">No se detectaron quizzes ni enlaces.<br>
      Los quizzes se definen en las <b>notas</b> de la lámina con un bloque <code>[quiz]</code>;
      los enlaces son los <b>hipervínculos</b> que pongas en PowerPoint.</div>`;
    return;
  }
  for (const s of withStuff) {
    const card = document.createElement("div");
    card.className = "inter-slide";
    let html = `<div class="inter-head">Lámina ${s.index} — ${escapeHtml(s.title)}</div>`;
    if (s.quiz) {
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
    }
    for (const lk of s.links || []) {
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
  const path = await api().pick_logo();
  if (path) {
    state.config.course.logo = path;
    syncCourseInputs();
    schedulePreview();
  }
}

// ───────────────────────── paso 5: publicar ─────────────────────────

async function convert() {
  $("convert-btn").disabled = true;
  $("result").hidden = true;
  $("progress-wrap").hidden = false;
  setProgress(4, "Iniciando…");
  await api().convert({
    config: state.config,
    scale: parseFloat(state.output.scale),
    quality: state.output.quality,
    format: state.output.format,
    zip: state.output.zip,
    outDir: state.output.outDir,
  });
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
    $("convert-btn").disabled = false;
  } else if (event === "error") {
    $("progress-wrap").hidden = true;
    $("convert-btn").disabled = false;
    alert("Error en la conversión:\n\n" + payload.message);
  }
};

function showResult(r) {
  state.lastResult = r;
  const mb = (r.imageBytes / 1024 / 1024).toFixed(1);
  let html = `<div>${r.slideCount} láminas · ${mb} MB${r.mediaCount ? ` · ${r.mediaCount} media` : ""}</div>`;
  html += `<div style="color:var(--muted);margin-top:4px">${r.outDir}</div>`;
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
    const d = await api().pick_output_dir();
    if (d) { state.output.outDir = d; $("out-name").textContent = d; }
  });
  $("convert-btn").addEventListener("click", convert);
  $("open-result").addEventListener("click", () => state.lastResult && api().open_url(state.lastResult.indexUrl));
  $("open-folder").addEventListener("click", () => state.lastResult && api().open_folder(state.lastResult.outDir));

  renderDots();
}

async function boot() {
  wire();
  state.themes = await api().list_themes();
  buildThemeCards();
}

window.addEventListener("pywebviewready", boot);
