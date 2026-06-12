/* pptx2web player — ES2020, sin frameworks, sin build.
   El manifest viaja embebido en el HTML (estrategia de caché D7). */
"use strict";

(() => {
  // ───────────────────────── estado ─────────────────────────

  const manifest = JSON.parse(document.getElementById("manifest").textContent);
  const slides = manifest.slides;
  const total = manifest.slideCount;
  const ratio = manifest.slideSize.width / manifest.slideSize.height;

  const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const isMobile = () => matchMedia("(max-width: 768px)").matches;

  let current = 0; // índice 0-based del slide visible
  let frontIsA = true;

  const $ = (id) => document.getElementById(id);
  const app = $("app");
  const stage = $("stage");
  const slideBox = $("slide-box");
  const bufA = $("buf-a");
  const bufB = $("buf-b");
  const mediaLayer = $("media-layer");
  const notesPanel = $("notes");
  const notesBody = $("notes-body");
  const thumbList = $("thumb-list");
  const counter = $("counter");
  const progressFill = $("progress-fill");

  document.documentElement.style.setProperty("--slide-ratio", `${manifest.slideSize.width}/${manifest.slideSize.height}`);
  document.title = manifest.title;
  $("deck-title").textContent = manifest.title;
  $("deck-count").textContent = `${total} diapositivas`;

  // ─────────────── configuración: tema, layout, curso, secciones ───────────────

  let config = {};
  try {
    config = JSON.parse(document.getElementById("config").textContent) || {};
  } catch (e) { /* sin config embebida: defaults */ }

  let activePanel = null;

  function applyConfig(cfg) {
    config = cfg || {};
    const root = document.documentElement;
    for (const [key, value] of Object.entries(config.colors || {})) {
      if (key.startsWith("--")) root.style.setProperty(key, value);
    }

    const layout = config.layout || {};
    app.classList.toggle("side-right", layout.sidebarSide === "right");

    const course = config.course || {};
    $("deck-title").textContent = course.title || manifest.title;
    document.title = course.title || manifest.title;
    const logo = $("course-logo");
    if (course.logo) {
      logo.src = course.logo;
      logo.hidden = false;
    } else {
      logo.hidden = true;
      logo.removeAttribute("src");
    }

    const sections = config.sections || [];
    const panels = (layout.panels || ["thumbnails"]).filter(
      (p) => p === "thumbnails" || (p === "sections" && sections.length)
    );
    buildSections(sections);
    $("panel-tabs").hidden = panels.length < 2;
    if (!activePanel || !panels.includes(activePanel)) {
      activePanel = panels.includes(layout.defaultPanel)
        ? layout.defaultPanel
        : panels[0] || "thumbnails";
    }
    setPanel(activePanel);
    renderLinks(current);
    renderQuiz(current);
    updateChrome();
    fitSlideBox();
  }

  function setPanel(name) {
    activePanel = name;
    $("section-list").hidden = name !== "sections";
    $("thumb-list").hidden = name !== "thumbnails";
    $("tab-sections").classList.toggle("active", name === "sections");
    $("tab-thumbnails").classList.toggle("active", name === "thumbnails");
  }

  function buildSections(sections) {
    const list = $("section-list");
    list.innerHTML = "";
    const frag = document.createDocumentFragment();
    for (const sec of sections) {
      const btn = document.createElement("button");
      btn.className = "section-item";
      btn.dataset.from = sec.from;
      btn.dataset.to = sec.to;

      const title = document.createElement("div");
      title.className = "section-title";
      title.textContent = sec.title;

      const meta = document.createElement("div");
      meta.className = "section-meta";
      const bar = document.createElement("div");
      bar.className = "section-bar";
      const fill = document.createElement("div");
      fill.className = "section-bar-fill";
      bar.appendChild(fill);
      const count = document.createElement("span");
      count.className = "section-count";
      meta.append(bar, count);

      btn.append(title, meta);
      btn.addEventListener("click", () => {
        show(sec.from - 1);
        if (isMobile()) toggleThumbs(false);
      });
      frag.appendChild(btn);
    }
    list.appendChild(frag);
  }

  // ─────────────────── caché de imágenes (LRU, máx 30) ───────────────────

  const CACHE_MAX = 30;
  const imgCache = new Map(); // index -> HTMLImageElement (orden = LRU)

  function loadSlide(i) {
    if (i < 0 || i >= total) return null;
    if (imgCache.has(i)) {
      const img = imgCache.get(i);
      imgCache.delete(i);
      imgCache.set(i, img); // refrescar posición LRU
      return img;
    }
    const img = new Image();
    img.src = slides[i].src;
    imgCache.set(i, img);
    if (imgCache.size > CACHE_MAX) {
      const oldest = imgCache.keys().next().value;
      imgCache.delete(oldest);
    }
    return img;
  }

  // precarga adyacente: n±1 inmediato; n+2..n+4 en idle. Nunca todo el deck.
  function preloadAround(i) {
    loadSlide(i + 1);
    loadSlide(i - 1);
    const idle = window.requestIdleCallback || ((fn) => setTimeout(fn, 300));
    idle(() => {
      for (let k = i + 2; k <= i + 4; k++) loadSlide(k);
    });
  }

  // ─────────────────── dimensionado del slide-box ───────────────────

  function fitSlideBox() {
    const pad = isMobile() ? 0 : 0; // el padding ya lo aporta .stage
    const w = stage.clientWidth - pad;
    const h = stage.clientHeight - pad;
    // restar el padding real del stage
    const cs = getComputedStyle(stage);
    const availW = w - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
    const availH = h - parseFloat(cs.paddingTop) - parseFloat(cs.paddingBottom);
    let bw = availW;
    let bh = bw / ratio;
    if (bh > availH) {
      bh = availH;
      bw = bh * ratio;
    }
    slideBox.style.width = `${Math.floor(bw)}px`;
    slideBox.style.height = `${Math.floor(bh)}px`;
  }

  new ResizeObserver(fitSlideBox).observe(stage);

  // ─────────────────── navegación + transiciones ───────────────────

  const TRANSITION_CLASSES = ["t-fade", "t-push-fwd", "t-push-back", "t-wipe", "t-split"];

  function show(i, { animate = true } = {}) {
    i = Math.max(0, Math.min(total - 1, i));
    const forward = i > current;
    const first = bufA.src === "" && bufB.src === "";
    const incoming = frontIsA ? bufB : bufA;
    const outgoing = frontIsA ? bufA : bufB;

    const img = loadSlide(i);
    incoming.src = img.src;
    incoming.alt = slides[i].title;

    const trans = slides[i].transition || { type: "cut", duration: 0 };
    const type = reducedMotion || !animate || first ? "cut" : trans.type;

    incoming.classList.remove(...TRANSITION_CLASSES);
    outgoing.classList.remove(...TRANSITION_CLASSES);
    incoming.classList.add("front");
    incoming.classList.remove("back");
    outgoing.classList.add("back");
    outgoing.classList.remove("front");

    if (type !== "cut" && trans.duration > 0) {
      incoming.style.setProperty("--t-dur", `${trans.duration}ms`);
      const cls = {
        fade: "t-fade",
        push: forward ? "t-push-fwd" : "t-push-back",
        wipe: "t-wipe",
        split: "t-split",
      }[type] || "t-fade";
      // reiniciar la animación aunque se repita la clase
      void incoming.offsetWidth;
      incoming.classList.add(cls);
    }

    frontIsA = !frontIsA;
    current = i;

    renderMedia(i);
    renderLinks(i);
    renderQuiz(i);
    updateChrome();
    preloadAround(i);
    history.replaceState(null, "", `#slide=${i + 1}`);
  }

  const next = () => show(current + 1);
  const prev = () => show(current - 1);

  function updateChrome() {
    counter.textContent = `${current + 1} / ${total}`;
    progressFill.style.width = `${((current + 1) / total) * 100}%`;
    $("nav-prev").disabled = current === 0;
    $("nav-next").disabled = current === total - 1;

    // sidebar
    const items = thumbList.children;
    for (let k = 0; k < items.length; k++) {
      items[k].classList.toggle("active", k === current);
    }
    const active = items[current];
    if (active) active.scrollIntoView({ block: "nearest", behavior: reducedMotion ? "auto" : "smooth" });

    // notas
    const notes = slides[current].notes;
    notesBody.innerHTML = notes || '<p class="notes-empty">Esta diapositiva no tiene notas.</p>';

    // panel de secciones + progreso global
    const n = current + 1;
    $("global-progress").textContent = `Lámina ${n} de ${total}`;
    $("global-fill").style.width = `${(n / total) * 100}%`;
    let activeSection = null;
    document.querySelectorAll(".section-item").forEach((el) => {
      const from = +el.dataset.from;
      const to = +el.dataset.to;
      const count = to - from + 1;
      const inSection = n >= from && n <= to;
      const viewed = Math.min(Math.max(n - from + 1, 0), count);
      el.classList.toggle("active", inSection);
      el.classList.toggle("done", n > to);
      el.querySelector(".section-bar-fill").style.width = `${(viewed / count) * 100}%`;
      el.querySelector(".section-count").textContent =
        inSection ? `${viewed} / ${count}` : `${count} láminas`;
      if (inSection) activeSection = el;
    });
    if (activeSection && activePanel === "sections") {
      activeSection.scrollIntoView({ block: "nearest", behavior: reducedMotion ? "auto" : "smooth" });
    }
  }

  // ─────────────────── overlays de media ───────────────────

  function renderMedia(i) {
    // detener cualquier reproducción del slide anterior
    mediaLayer.querySelectorAll("video,audio").forEach((el) => el.pause());
    mediaLayer.innerHTML = "";
    for (const m of slides[i].media || []) {
      const el = document.createElement(m.type === "video" ? "video" : "audio");
      el.src = m.src;
      el.controls = true;
      el.preload = "metadata";
      if (m.autoplay) {
        el.autoplay = true;
        el.muted = m.type === "video"; // autoplay con sonido lo bloquea el navegador
      }
      el.style.left = `${m.rect.x * 100}%`;
      el.style.top = `${m.rect.y * 100}%`;
      el.style.width = `${m.rect.w * 100}%`;
      if (m.type === "video") {
        el.style.height = `${m.rect.h * 100}%`;
      } else {
        // un control de audio nativo es bajo: anclarlo al rect sin estirarlo
        el.style.maxWidth = "100%";
      }
      el.addEventListener("contextmenu", (e) => e.preventDefault());
      mediaLayer.appendChild(el);
    }
  }

  // ─────────────────── hotspots de links ───────────────────

  function positionByRect(el, rect) {
    el.style.left = `${rect.x * 100}%`;
    el.style.top = `${rect.y * 100}%`;
    el.style.width = `${rect.w * 100}%`;
    el.style.height = `${rect.h * 100}%`;
  }

  function renderLinks(i) {
    const layer = $("link-layer");
    layer.innerHTML = "";
    const auto = slides[i].links || [];
    // links manuales del config para esta lámina (el campo destino es "to")
    const manual = (config.links || []).filter((l) => l.slide === i + 1);
    for (const link of [...auto, ...manual]) {
      // destino interno: en links del manifest viene en "slide";
      // en links manuales del config, "slide" es la lámina anfitriona y
      // el destino viene en "to"
      const target = link.href ? null : (link.kind === "manual" ? link.to : link.slide);
      const a = document.createElement("a");
      a.className = "link-hotspot";
      positionByRect(a, link.rect);
      if (link.href) {
        a.href = link.href;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        a.title = link.tooltip || link.href;
      } else if (target) {
        a.classList.add("internal");
        a.href = `#slide=${target}`;
        a.title = link.tooltip || `Ir a la lámina ${target}`;
        a.addEventListener("click", (e) => {
          e.preventDefault();
          show(target - 1);
        });
      } else {
        continue;
      }
      a.draggable = false;
      layer.appendChild(a);
    }
  }

  // ─────────────────── quiz semi-interactivo ───────────────────

  // respuesta por sesión: índice de slide → índice de opción elegida
  const quizAnswers = new Map();

  function quizFor(i) {
    const fromConfig = (config.quizzes || []).find((q) => q.slide === i + 1);
    return fromConfig || slides[i].quiz || null;
  }

  function renderQuiz(i) {
    const layer = $("quiz-layer");
    layer.innerHTML = "";
    const quiz = quizFor(i);
    layer.hidden = !quiz;
    if (!quiz) return;

    const card = document.createElement("div");
    card.className = "quiz-card";

    if (quiz.question) {
      const q = document.createElement("div");
      q.className = "quiz-question";
      q.textContent = quiz.question;
      card.appendChild(q);
    }

    const opts = document.createElement("div");
    opts.className = "quiz-options";
    const answered = quizAnswers.has(i);

    quiz.options.forEach((opt, k) => {
      const btn = document.createElement("button");
      btn.className = "quiz-option";
      btn.type = "button";
      const dot = document.createElement("span");
      dot.className = "quiz-dot";
      const label = document.createElement("span");
      label.textContent = opt.text;
      btn.append(dot, label);
      if (!answered) {
        btn.addEventListener("click", () => {
          quizAnswers.set(i, k);
          renderQuiz(i);
        });
      }
      opts.appendChild(btn);
    });
    card.appendChild(opts);

    if (answered) {
      const chosen = quizAnswers.get(i);
      const ok = quiz.options[chosen].correct;
      opts.querySelectorAll(".quiz-option").forEach((btn, k) => {
        btn.disabled = true;
        if (quiz.options[k].correct) {
          btn.classList.add("correct");
          btn.querySelector(".quiz-dot").textContent = "✓";
        } else if (k === chosen) {
          btn.classList.add("wrong");
          btn.querySelector(".quiz-dot").textContent = "✕";
        }
      });
      const fbText = ok ? quiz.feedbackOk : quiz.feedbackKo;
      const fb = document.createElement("div");
      fb.className = `quiz-feedback ${ok ? "ok" : "ko"}`;
      fb.textContent = fbText || (ok ? "¡Correcto!" : "Respuesta incorrecta.");
      card.appendChild(fb);
    }

    // colapsable: ver la lámina completa sin la tarjeta
    const toggle = document.createElement("button");
    toggle.className = "quiz-toggle";
    toggle.type = "button";
    toggle.hidden = true;
    toggle.textContent = answered ? "Ver respuesta" : "Responder pregunta";
    toggle.addEventListener("click", () => {
      card.style.display = "";
      toggle.hidden = true;
    });
    const collapse = document.createElement("button");
    collapse.className = "tb-btn quiz-collapse";
    collapse.type = "button";
    collapse.title = "Ocultar la pregunta";
    collapse.setAttribute("aria-label", "Ocultar la pregunta");
    collapse.innerHTML = "&#x2715;";
    collapse.style.cssText = "position:absolute;top:6px;right:6px;width:26px;height:26px;font-size:11px;";
    collapse.addEventListener("click", () => {
      card.style.display = "none";
      toggle.hidden = false;
    });
    card.style.position = "relative";
    card.appendChild(collapse);

    layer.append(card, toggle);
  }

  // ─────────────────── sidebar de miniaturas ───────────────────

  // loading="lazy" + IntersectionObserver: solo se piden las visibles
  const thumbIO = new IntersectionObserver(
    (entries) => {
      for (const e of entries) {
        if (e.isIntersecting) {
          const img = e.target;
          if (!img.src) img.src = img.dataset.src;
          thumbIO.unobserve(img);
        }
      }
    },
    { root: thumbList, rootMargin: "300px" }
  );

  function buildSidebar() {
    const frag = document.createDocumentFragment();
    slides.forEach((s, k) => {
      const li = document.createElement("li");
      li.className = "thumb-item";
      li.title = s.title;

      const num = document.createElement("span");
      num.className = "thumb-num";
      num.textContent = s.index;

      const img = document.createElement("img");
      img.className = "thumb-img";
      img.alt = s.title;
      img.loading = "lazy";
      img.draggable = false;
      img.dataset.src = s.thumb;
      thumbIO.observe(img);

      li.append(num, img);
      li.addEventListener("click", () => {
        show(k);
        if (isMobile()) toggleThumbs(false);
      });
      frag.appendChild(li);
    });
    thumbList.appendChild(frag);
  }

  function toggleThumbs(force) {
    if (isMobile()) {
      const show_ = force !== undefined ? force : !app.classList.contains("thumbs-shown");
      app.classList.toggle("thumbs-shown", show_);
    } else {
      const hide = force !== undefined ? !force : !app.classList.contains("thumbs-hidden");
      app.classList.toggle("thumbs-hidden", hide);
    }
    $("btn-thumbs").classList.toggle("on", isMobile()
      ? app.classList.contains("thumbs-shown")
      : !app.classList.contains("thumbs-hidden"));
    // el grid cambia de ancho: reencajar el slide tras la transición
    setTimeout(fitSlideBox, 300);
  }

  // ─────────────────── notas ───────────────────

  function toggleNotes(force) {
    const showNotes = force !== undefined ? force : notesPanel.hidden;
    notesPanel.hidden = !showNotes;
    $("btn-notes").classList.toggle("on", showNotes);
    fitSlideBox();
  }

  // ─────────────────── búsqueda ───────────────────

  const searchOverlay = $("search-overlay");
  const searchInput = $("search-input");
  const searchResults = $("search-results");
  let hits = [];
  let selectedHit = -1;

  function openSearch() {
    searchOverlay.hidden = false;
    searchInput.value = "";
    runSearch("");
    searchInput.focus();
  }

  function closeSearch() {
    searchOverlay.hidden = true;
  }

  // Normaliza carácter a carácter (sin tildes, minúsculas) preservando la
  // longitud 1:1 con el original, para que los índices del snippet sigan
  // siendo válidos sobre el texto sin normalizar.
  function norm(s) {
    return Array.from(s, (c) => c.normalize("NFD")[0].toLowerCase()).join("");
  }

  function runSearch(query) {
    const q = norm(query.trim());
    hits = [];
    selectedHit = -1;
    searchResults.innerHTML = "";
    if (!q) {
      searchResults.innerHTML = '<li class="search-empty">Escribe para buscar en títulos y contenido.</li>';
      return;
    }
    for (const s of slides) {
      const hay = norm(`${s.title} ${s.text || ""}`);
      if (hay.includes(q)) hits.push(s);
    }
    if (!hits.length) {
      searchResults.innerHTML = '<li class="search-empty">Sin coincidencias.</li>';
      return;
    }
    const frag = document.createDocumentFragment();
    hits.forEach((s, k) => {
      const li = document.createElement("li");
      li.className = "search-hit";

      const img = document.createElement("img");
      img.src = s.thumb;
      img.alt = "";
      img.loading = "lazy";
      img.draggable = false;

      const txt = document.createElement("div");
      const title = document.createElement("div");
      title.className = "search-hit-title";
      title.textContent = `${s.index}. ${s.title}`;
      const snippet = document.createElement("div");
      snippet.className = "search-hit-snippet";
      snippet.innerHTML = makeSnippet(s.text || "", q);
      txt.append(title, snippet);

      li.append(img, txt);
      li.addEventListener("click", () => {
        closeSearch();
        show(s.index - 1);
      });
      li.addEventListener("mousemove", () => selectHit(k));
      frag.appendChild(li);
    });
    searchResults.appendChild(frag);
    selectHit(0);
  }

  function makeSnippet(text, q) {
    const idx = norm(text).indexOf(q);
    if (idx < 0) return escapeHtml(text.slice(0, 110));
    const start = Math.max(0, idx - 40);
    const before = escapeHtml(text.slice(start, idx));
    const match = escapeHtml(text.slice(idx, idx + q.length));
    const after = escapeHtml(text.slice(idx + q.length, idx + q.length + 70));
    return `${start > 0 ? "…" : ""}${before}<mark>${match}</mark>${after}`;
  }

  function escapeHtml(s) {
    return s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  }

  function selectHit(k) {
    selectedHit = k;
    searchResults.querySelectorAll(".search-hit").forEach((el, j) => {
      el.classList.toggle("selected", j === k);
    });
  }

  searchInput.addEventListener("input", () => runSearch(searchInput.value));
  searchInput.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); if (hits.length) selectHit(Math.min(selectedHit + 1, hits.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); if (hits.length) selectHit(Math.max(selectedHit - 1, 0)); }
    else if (e.key === "Enter" && selectedHit >= 0) {
      const s = hits[selectedHit];
      closeSearch();
      show(s.index - 1);
    }
  });
  searchOverlay.addEventListener("click", (e) => {
    if (e.target === searchOverlay) closeSearch();
  });

  // ─────────────────── fullscreen ───────────────────

  function toggleFullscreen() {
    if (document.fullscreenElement) document.exitFullscreen();
    else document.documentElement.requestFullscreen().catch(() => {});
  }

  document.addEventListener("fullscreenchange", () => {
    $("btn-fs").classList.toggle("on", !!document.fullscreenElement);
    fitSlideBox();
  });

  // ─────────────────── teclado ───────────────────

  document.addEventListener("keydown", (e) => {
    if (!searchOverlay.hidden) {
      if (e.key === "Escape") closeSearch();
      return; // el resto lo gestiona el input
    }
    if (e.target instanceof HTMLInputElement) return;
    // Space sobre un botón enfocado (ej. opción de quiz) activa el botón,
    // no avanza de lámina
    if (e.key === " " && e.target instanceof HTMLButtonElement) return;
    switch (e.key) {
      case "ArrowRight": case " ": case "PageDown": e.preventDefault(); next(); break;
      case "ArrowLeft": case "PageUp": e.preventDefault(); prev(); break;
      case "Home": e.preventDefault(); show(0); break;
      case "End": e.preventDefault(); show(total - 1); break;
      case "f": case "F": toggleFullscreen(); break;
      case "n": case "N": toggleNotes(); break;
      case "t": case "T": toggleThumbs(); break;
      case "Escape":
        if (document.fullscreenElement) document.exitFullscreen();
        else if (!notesPanel.hidden) toggleNotes(false);
        break;
    }
  });

  // ─────────────────── gestos táctiles (swipe) ───────────────────

  let touchX = null;
  let touchY = null;
  stage.addEventListener("touchstart", (e) => {
    touchX = e.changedTouches[0].clientX;
    touchY = e.changedTouches[0].clientY;
  }, { passive: true });
  stage.addEventListener("touchend", (e) => {
    if (touchX === null) return;
    const dx = e.changedTouches[0].clientX - touchX;
    const dy = e.changedTouches[0].clientY - touchY;
    touchX = touchY = null;
    if (Math.abs(dx) > 40 && Math.abs(dx) > Math.abs(dy)) {
      dx < 0 ? next() : prev();
    }
  }, { passive: true });

  // ─────────────────── barra de progreso (seek) ───────────────────

  $("progress").addEventListener("click", (e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const frac = (e.clientX - rect.left) / rect.width;
    show(Math.round(frac * (total - 1)));
  });

  // ─────────────────── protección (D3, disuasoria) ───────────────────

  // Medida disuasoria, no DRM: dificulta el copiado casual, no impide capturas.
  for (const el of [stage, thumbList]) {
    el.addEventListener("contextmenu", (e) => e.preventDefault());
  }
  document.addEventListener("dragstart", (e) => {
    if (e.target instanceof HTMLImageElement) e.preventDefault();
  });

  // ─────────────────── deep-linking ───────────────────

  function slideFromHash() {
    const m = location.hash.match(/slide=(\d+)/);
    if (!m) return 0;
    return Math.max(0, Math.min(total - 1, parseInt(m[1], 10) - 1));
  }

  window.addEventListener("hashchange", () => {
    const i = slideFromHash();
    if (i !== current) show(i);
  });

  // ─────────────────── botones ───────────────────

  $("btn-prev").addEventListener("click", prev);
  $("btn-next").addEventListener("click", next);
  $("nav-prev").addEventListener("click", prev);
  $("nav-next").addEventListener("click", next);
  $("btn-fs").addEventListener("click", toggleFullscreen);
  $("btn-notes").addEventListener("click", () => toggleNotes());
  $("btn-thumbs").addEventListener("click", () => toggleThumbs());
  $("btn-search").addEventListener("click", openSearch);
  $("tab-sections").addEventListener("click", () => setPanel("sections"));
  $("tab-thumbnails").addEventListener("click", () => setPanel("thumbnails"));

  // ─────────────────── arranque ───────────────────

  buildSidebar();
  applyConfig(config);
  $("btn-thumbs").classList.toggle("on", !isMobile());
  show(slideFromHash(), { animate: false });

  // config.json en la raíz: override editable post-export. Solo funciona
  // servido por HTTP; en file:// el fetch falla y se ignora en silencio.
  fetch("config.json", { cache: "no-store" })
    .then((r) => (r.ok ? r.json() : null))
    .then((c) => {
      if (c && JSON.stringify(c) !== JSON.stringify(config)) applyConfig(c);
    })
    .catch(() => {});
})();
