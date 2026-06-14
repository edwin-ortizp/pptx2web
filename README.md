# pptx2web

Publicador local de PowerPoint a experiencia web. Convierte un `.pptx` en una
carpeta estática autocontenida con un player profesional: miniaturas, notas del
orador, búsqueda, transiciones, deep-linking y pantalla completa.

Alternativa local a iSpring Converter: sin nube, sin servicios, sin API.
La conversión usa **tu PowerPoint instalado** (vía COM), por lo que la fidelidad
visual es la del propio PowerPoint.

## Requisitos

- Windows con Microsoft PowerPoint (escritorio) instalado
- Python 3.11+
- `ffmpeg` (opcional: solo para transcodificar video/audio legacy WMV/WMA);
  puede ir en `bin\ffmpeg.exe` junto a la herramienta o en el `PATH`

## Instalación

```powershell
pip install -e .
```

## Uso

```powershell
pptx2web presentacion.pptx
# → crea .\presentacion-web\ lista para abrir o publicar

pptx2web presentacion.pptx -o salida\ --quality 82 --scale 2.0 --zip --open
```

| Opción | Descripción |
|---|---|
| `-o, --out DIR` | Carpeta de salida (default `./<nombre>-web/`) |
| `--scale FLOAT` | Resolución del render, 2.0 por defecto (máx 3.0) |
| `--quality INT` | Calidad WebP 1–100 (default 82) |
| `--format webp\|png` | Formato de los slides (default webp) |
| `--theme NAME` | Tema visual predefinido de `themes/` (ej. `certmind`) |
| `--config PATH` | Config del deck (default: autodetecta `<nombre>.config.json` junto al .pptx) |
| `--zip` | Genera además `<out>.zip` |
| `--open` | Abre `index.html` al terminar |
| `-q` / `-v` | Menos / más verbosidad |

Exit codes: `0` ok · `2` input inválido · `3` PowerPoint no disponible · `4` error de render.

> Durante la conversión puede aparecer brevemente una ventana de PowerPoint:
> no la cierres; es una instancia independiente que se cierra sola al terminar.

## El player

- **Navegación:** `←` `→` `Espacio` `PageUp/Down` `Home` `End`, flechas en
  pantalla, barra de progreso clicable y gestos swipe en móvil.
- **Miniaturas:** tecla `T` o botón; carga perezosa (solo las visibles).
- **Notas del orador:** tecla `N`.
- **Búsqueda** en títulos y contenido de los slides, insensible a tildes
  ("informatica" encuentra "Informática").
- **Panel de secciones (breadcrumbs):** logo, nombre del curso, secciones con
  rango de láminas, sección activa resaltada, progreso por sección y global.
- **Links clicables:** los hipervínculos del PPT (sobre shapes o texto) se
  vuelven zonas clicables sobre la lámina; los internos navegan dentro del
  player.
- **Quizzes:** láminas de pregunta con opciones interactivas y feedback
  inmediato, definidas en las notas del slide o en el config.
- **Puntero láser:** tecla `L` o botón; un punto luminoso sigue el cursor (o el
  dedo en táctil) para señalar sobre la lámina, como el modo presentador de
  PowerPoint. Está apagado por defecto; tamaño y color configurables.
- **Anotaciones temporales:** tecla `D` o botón del lápiz; permite rayar sobre
  la lámina con lápiz, resaltador y borrador. **No se guardan**: viven solo en
  memoria y desaparecen al recargar.
- **Pantalla completa:** tecla `F`.
- **Deep-linking:** `index.html#slide=7` abre directamente el slide 7.
- **Rendimiento:** carga inicial mínima (HTML + CSS + JS + slide 1); precarga
  de slides adyacentes; caché LRU en memoria. Funciona fluido con decks de
  300+ slides.
- **Protección del contenido:** los slides son imágenes rasterizadas, sin capa
  de texto; selección, arrastre y menú contextual deshabilitados. *Es una
  medida disuasoria, no DRM: las capturas de pantalla siempre son posibles.*

### Qué se conserva y qué no

| | |
|---|---|
| ✅ Fidelidad visual exacta (fuentes, SmartArt, charts) | Render del propio PowerPoint |
| ✅ Transiciones entre slides | fade / push / wipe / split / cut (otras degradan a fade) |
| ✅ Notas, títulos, texto buscable | |
| ✅ Video y audio embebidos | WMV/WMA se transcodifican a MP4/MP3 con ffmpeg |
| ❌ Animaciones dentro del slide | Se renderiza el estado final |
| ❌ Selección/copiado de texto | Decisión de diseño (protección) |

## Personalización: temas, layout y secciones

Crea un `<nombre>.config.json` junto al `.pptx` (se detecta solo) o pásalo con
`--config`. Todo es opcional:

```json
{
  "theme": "certmind",
  "course": { "title": "ITIL 4 Fundamentos", "logo": "logo.png" },
  "colors": { "--accent": "#e91e8c", "--panel": "#000000" },
  "layout": {
    "sidebarSide": "right",
    "panels": ["sections", "thumbnails"],
    "defaultPanel": "sections"
  },
  "sections": [
    { "title": "Introducción", "from": 1, "to": 4 },
    { "title": "¿Qué es ITIL 4?", "from": 5, "to": 18 }
  ]
}
```

- **`theme`**: nombre de un JSON en `themes/` (incluidos: `default`, `certmind`).
  Para crear uno propio, copia `themes/default.json` y ajusta las variables.
  `--theme` en la CLI tiene prioridad sobre el config.
- **`colors`**: variables CSS que sobrescriben al tema (fondo `--bg`, panel
  lateral `--panel`, acento `--accent`, texto `--ink`…).
- **`layout.sidebarSide`**: `left` o `right` (estilo iSpring).
- **`layout.panels`**: qué paneles existen (`sections`, `thumbnails`); con ambos
  aparecen pestañas Contenido ⇄ Láminas. `defaultPanel` decide cuál abre.
- **`sections`**: breadcrumbs del curso; `from`/`to` son números de lámina
  (1-based, inclusive). El CLI avisa si hay solapamientos o láminas sin sección.
- **`course.logo`**: ruta relativa al config; se copia a la salida con hash.

### Links

Los hipervínculos que pongas en PowerPoint se extraen solos al convertir:

- **Sobre un shape/imagen/botón completo:** la zona clicable es exacta.
- **Dentro de un texto:** la zona clicable es la caja completa que contiene el
  texto (PowerPoint no guarda el rectángulo de la palabra); el player muestra
  un indicador sutil (ícono ↗) para que sea descubrible.
- **A otra lámina del mismo deck** (Insertar → Vínculo → Lugar de este
  documento): navegan dentro del player.

También puedes definir links manuales en el config (se suman a los del PPT y
puedes agregarlos editando el `config.json` exportado, sin reconvertir):

```json
"links": [
  { "slide": 7, "rect": { "x": 0.6, "y": 0.85, "w": 0.3, "h": 0.1 },
    "href": "https://ejemplo.com", "tooltip": "Ver recurso" },
  { "slide": 9, "rect": { "x": 0.1, "y": 0.1, "w": 0.2, "h": 0.1 }, "to": 2 }
]
```

`slide` = lámina donde vive la zona clicable; `rect` en fracciones 0..1 del
lienzo; `href` para URL externa o `to` para saltar a otra lámina.

### Quizzes

Para volver interactiva una lámina de pregunta, escribe en sus **notas del
orador** un bloque `[quiz]` (la lámina sigue siendo el fondo visual; el player
superpone una tarjeta con las opciones):

```
[quiz]
¿Cuál es la 4a revolución industrial?
- Mecanización
+ Digitalización
- Electricidad
ok: ¡Correcto! La 4a revolución es la digital.
no: Revisa la sección "¿Qué es ITIL 4?".
```

- `+` marca la opción correcta (exactamente una), `-` las demás.
- La pregunta es opcional (si la lámina ya la muestra, puedes omitirla).
- `ok:` / `no:` son los mensajes de feedback, opcionales.
- Esas notas no se publican como notas normales.
- En la lámina de quiz aparece un botón flotante ("Responder pregunta"); al
  pulsarlo se abre la pregunta en un panel centrado (no es invasivo: la lámina
  se ve completa hasta que el estudiante decide responder).
- Al responder: la correcta se marca en verde, la elegida incorrecta en rojo,
  y se muestra el feedback. Se cierra con `Esc`, la ✕ o clic fuera; al volver,
  el botón dice "Ver respuesta" y conserva lo respondido. Si el bloque está
  malformado, el CLI avisa y la lámina queda normal.

Alternativa en el config (reemplaza al quiz de notas de esa lámina):

```json
"quizzes": [
  { "slide": 12, "question": "¿…?", "feedbackOk": "¡Bien!", "feedbackKo": "Repasa.",
    "options": [ { "text": "A" }, { "text": "B", "correct": true } ] }
]
```

### Puntero láser

Se activa con la tecla `L` o el botón de la barra (apagado por defecto). El
tamaño y color se configuran:

```json
"pointer": { "size": 24, "color": "#ff3b30" }
```

`size` es el diámetro en px (8–80). También puede fijarse por tema en
`themes/*.json`.

### Anotaciones temporales (lápiz / resaltador / borrador)

Con la tecla `D` o el botón del lápiz se abre la barra de anotación para rayar
sobre la lámina durante una explicación. Hay **lápiz**, **resaltador** y
**borrador**, un selector de color y un botón para limpiar la lámina.

- **No se guardan en ningún lado.** Los trazos viven solo en memoria: cada
  lámina recuerda los suyos mientras la página esté abierta (al volver a una
  lámina siguen ahí), pero **todo desaparece al recargar**. La propia barra lo
  indica ("Anotaciones temporales — se borran al recargar").
- El láser y el modo dibujo son mutuamente excluyentes; `Esc` sale del modo.

La paleta y los grosores se configuran (con valores por defecto razonables):

```json
"pen": {
  "colors": ["#e3342f", "#ffd60a", "#39b54a", "#2f6fed", "#ffffff"],
  "penSize": 3, "highlighterSize": 18, "eraserSize": 28
}
```

**Editable después de publicar:** la salida incluye un `config.json` en la
raíz. Si el material se sirve por HTTP, el player lo lee al cargar y aplica
los cambios (colores, secciones, layout, links, quizzes, puntero, lápiz) **sin
reconvertir el .pptx**. Vía `file://` se usa la config embebida en `index.html`.

## Despliegue

La carpeta de salida es 100 % estática y autocontenida. Opciones:

**Carpeta local / USB / intranet:** abre `index.html` directamente en el
navegador (funciona vía `file://`).

**Cualquier hosting estático** (S3, Netlify, GitHub Pages, nginx, Apache…):
sube la carpeta tal cual.

### Caché: por qué nunca verás una versión vieja

1. Todos los assets (slides, miniaturas, media, JS, CSS) llevan un
   *content-hash* en el nombre: si cambian, cambia su URL. Si no cambian entre
   re-publicaciones, conservan la URL y el caché del navegador se reutiliza.
2. El manifest viaja **embebido** dentro de `index.html`: el único archivo
   mutable del sistema es el HTML.
3. `index.html` declara `Cache-Control: no-cache` vía `<meta>`. Si tu hosting
   lo permite, configura además los headers (recomendado):

   ```
   index.html                         → Cache-Control: no-cache
   *.webp *.js *.css *.mp4 *.mp3      → Cache-Control: max-age=31536000, immutable
   ```

   Apache (`.htaccess` en la carpeta publicada):

   ```apache
   <Files "index.html">
     Header set Cache-Control "no-cache"
   </Files>
   <FilesMatch "\.(webp|png|js|css|mp4|mp3)$">
     Header set Cache-Control "max-age=31536000, immutable"
   </FilesMatch>
   ```

   nginx:

   ```nginx
   location = /index.html { add_header Cache-Control "no-cache"; }
   location ~* \.(webp|png|js|css|mp4|mp3)$ {
     add_header Cache-Control "max-age=31536000, immutable";
   }
   ```

   S3 + CloudFront: sube `index.html` con metadato `Cache-Control: no-cache`
   y el resto con `max-age=31536000, immutable`.

   Aun sin configurar headers, el peor caso es ver un `index.html` viejo que
   referencia assets viejos **consistentes entre sí** — nunca una mezcla — y
   un hard-refresh (Ctrl+F5) lo resuelve.

El `buildId` (visible en `manifest.json` y como comentario al inicio del HTML)
identifica qué versión está sirviendo el navegador.

## Desarrollo

```powershell
pip install -e . pytest
pytest            # los tests no requieren PowerPoint (corren en CI)
```

Estructura: `src/pptx2web/` (conversor), `player/` (estático, sin build),
`tests/` (fixtures generados con python-pptx).

## Limitaciones conocidas

- Solo Windows y solo PowerPoint de escritorio (decisión de diseño: máxima fidelidad).
- `.pptx` con contraseña no son convertibles (quita la contraseña primero).
- Animaciones intra-slide: se muestra el estado final del slide.
- Media enlazada a archivos externos al `.pptx` no se empaqueta.
