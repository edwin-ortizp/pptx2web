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

Hay dos formas: el **asistente gráfico** (recomendado para configurar secciones,
temas y colores) o la **CLI** (para automatizar).

### Asistente gráfico

```powershell
pip install -e .[gui]
pptx2web-gui            # o: python -m pptx2web.gui
```

Abre una ventana con un paso a paso: elegir `.pptx` → tema y colores (con
selector y previsualización en vivo) → editor de secciones (con validación) →
curso y logo → opciones de salida y publicación con barra de progreso. Guarda un
`<nombre>.config.json` junto al `.pptx` que la CLI reutiliza.

> El asistente es una **herramienta de administración**: nada de su interfaz se
> incluye en la carpeta exportada, que queda idéntica a la de la CLI.

### CLI

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
| `--format webp\|avif\|png` | Formato de los slides (default webp; avif comprime más pero codifica más lento) |
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

## Distribución para Windows (instalador + actualizaciones OTA)

La app se empaqueta como un ejecutable autónomo (PyInstaller, **no requiere que el
usuario instale Python ni dependencias**) y se entrega con un instalador
por-usuario (Inno Setup) que **no pide permisos de administrador**. El usuario
final solo necesita tener **Microsoft PowerPoint** instalado (la conversión lo usa
vía COM); WebView2, que mueve la interfaz, ya viene preinstalado en Windows 11.

### Compilar el distribuible

Requisitos del equipo de build: `pip install pyinstaller` y, opcionalmente,
[Inno Setup 6](https://jrsoftware.org/isdl.php) con `ISCC.exe` en el `PATH`.

```powershell
.\packaging\build.ps1
```

Produce:

- `dist\pptx2web-gui\` — carpeta ejecutable (`pptx2web-gui.exe` + `_internal\` +
  `player\` + `themes\`). Ya es funcional por sí sola.
- `dist\pptx2web-setup-<version>.exe` — instalador de un solo doble clic (si hay
  Inno Setup). Instala en `%LOCALAPPDATA%\pptx2web` y crea accesos directos.
- `dist\release-assets\` — `themes-manifest.json` + temas, para el canal OTA.

> Icono opcional: coloca `packaging\pptx2web.ico` antes de compilar.

La versión es única: se lee de `__version__` en `src/pptx2web/__init__.py`. Usa el
esquema por **fecha año-primero** `AÑO.MES.DÍA` (ej. `2026.06.15`) y crea el release
de GitHub con el tag **`v<version>`** (ej. `v2026.06.15`). El tag y `__version__`
deben coincidir; `build.ps1` te recuerda el tag exacto y avisa si el formato no
encaja. (No uses fechas día-primero como `15-06-2026`: el OTA las ordenaría mal y
no detectaría las actualizaciones.)

### Actualizaciones OTA

La app revisa actualizaciones al iniciar (en segundo plano, contra **GitHub
Releases**) en dos canales independientes — ver [`src/pptx2web/updater.py`](src/pptx2web/updater.py):

- **Temas** (lo más frecuente): sincroniza los `.json` de `themes\` desde el
  manifiesto del release. Los temas nuevos aparecen al reiniciar **sin reinstalar
  nada ni reconstruir el `.exe`**.
- **App**: si hay una versión mayor publicada, muestra un aviso; al aceptar,
  descarga el instalador y lo ejecuta en silencio (reemplaza archivos con la app
  cerrada y la relanza).

Configura el repo de distribución en las constantes `GITHUB_OWNER`/`GITHUB_REPO`
de `updater.py` (o, sin recompilar, vía `%LOCALAPPDATA%\pptx2web\update.json` o las
variables `PPTX2WEB_OTA_OWNER` / `PPTX2WEB_OTA_REPO` / `PPTX2WEB_OTA_TOKEN`).

> **Recomendación de seguridad:** usa un **repo de distribución público aparte**
> (solo instalador + temas; el código fuente sigue privado) para no embeber ningún
> token en el `.exe`. Si el repo es privado, necesitarás un token de solo lectura
> embebido, que es **extraíble** del binario.

### Publicar una actualización

- **Solo temas:** edita/añade `.json` en `themes\`, corre
  `.\packaging\make-themes-manifest.ps1` y sube `dist\release-assets\*` (manifiesto
  + temas) como assets de un release.
- **App completa (checklist):**
  1. Sube la fecha en `__version__` (`src/pptx2web/__init__.py`), ej. `"2026.07.01"`.
  2. `.\packaging\build.ps1` → genera `dist\pptx2web-setup-2026.07.01.exe` y los
     assets en `dist\release-assets\`. Anota el tag que imprime (`v2026.07.01`).
  3. Crea el release en GitHub con ese tag y sube **4 archivos**: el instalador +
     `themes-manifest.json` + cada tema (`default.json`, `certmind.json`, …).

## Limitaciones conocidas

- Solo Windows y solo PowerPoint de escritorio (decisión de diseño: máxima fidelidad).
- **SmartScreen:** el ejecutable no está firmado, así que la primera ejecución
  muestra "Windows protegió tu PC / editor desconocido". El usuario pulsa
  "Más información → Ejecutar de todos modos". Se elimina con un certificado de
  firma de código (OV/EV) a futuro.
- **WebView2:** preinstalado en Windows 11. En Windows 10 muy antiguos puede faltar;
  en ese caso instala el *Evergreen Bootstrapper* de Microsoft (gratuito).
- `.pptx` con contraseña no son convertibles (quita la contraseña primero).
- Animaciones intra-slide: se muestra el estado final del slide.
- Media enlazada a archivos externos al `.pptx` no se empaqueta.

## Diagnóstico de errores y bloqueos

La GUI guarda automáticamente logs locales en `%LOCALAPPDATA%\pptx2web\logs`.
Puedes abrirlos con **Abrir carpeta de diagnóstico**, junto a la vista previa,
o pegar esa ruta en el Explorador incluso si el programa no abre.
Si la carpeta no es escribible se usa `%TEMP%\pptx2web-diagnostics\logs`;
el botón muestra la ubicación efectiva si no consigue abrirla.

Cada ejecución tiene un identificador y archivos `session-*.log`, con fecha,
proceso, hilo y versiones del entorno. Se conservan diez sesiones, con un
máximo de 5 MB por archivo y dos respaldos `.1`/`.2` por sesión.
Se registran inicio, resultado y duración de operaciones, errores con sus
trazas, nombres/tamaños de archivos elegidos y las etapas de PowerPoint.
No se copian documentos ni configuraciones completas ni se envían logs
por Internet. Las trazas y los mensajes de error pueden contener rutas locales.

Cuando aparezca **No responde**, si es posible deja la aplicación abierta
unos 30 segundos antes de cerrarla. El supervisor registra las operaciones
pendientes y las pilas Python tras 15 segundos de falta de respuesta detectada,
con un máximo de una captura por minuto. Un selector abierto durante 30
segundos también genera una captura, marcada como espera que puede ser normal.
El supervisor consulta Windows sin esperar al hilo de la ventana y recibe
además una señal periódica de JavaScript. Registra la recuperación cuando ocurre.
Un bloqueo dentro de Windows/WebView2 puede requerir además un volcado nativo;
las capturas incluidas aquí muestran hilos Python.

Para reportar un fallo, indica la hora aproximada y lo que estabas haciendo,
y comparte el log de esa sesión junto con sus respaldos si existen.
La instrumentación permite investigar el bloqueo; no garantiza su corrección.

Validación automatizada: creación/retención/rotación, carpeta alternativa,
inicialización idempotente, resultados/cancelación/errores de selectores simulados,
tiempos y trazas, señales ausentes, recuperación y límites de capturas.
La repetición manual de aperturas/cancelaciones del selector nativo y la
validación del ejecutable sin consola deben realizarse en Windows con la
versión distribuida; los selectores simulados no sustituyen esa comprobación.

En la interfaz, **Ver logs** abre un panel con los registros de la sesión actual,
incluidos sus respaldos rotados. **Actualizar** vuelve a leerlos y **Copiar logs**
permite pegarlos en un mensaje a soporte. Si el portapapeles no está disponible,
se selecciona el texto para copiarlo con Ctrl+C. El panel muestra como máximo
los últimos 256 KB para mantener la interfaz ágil; **Abrir carpeta** permite
recuperar el historial completo. Los logs se muestran como texto literal.

## Protección y rendimiento de exportación

La GUI captura una copia de la ruta, configuración y opciones al iniciar una
conversión. Mientras se carga o convierte una presentación, el backend rechaza
otras cargas/conversiones; los botones de selección y publicación se restauran
al finalizar, fallar o rechazarse el inicio. La configuración se guarda junto
al PPTX original de esa conversión. Los errores capturados por el trabajador
terminan registrados como `status=error`, incluidos errores de guardado.

Los registros `image.result` separan lectura, codificación, generación de
miniatura y escritura/finalización, e incluyen índice, dimensiones, formato,
calidad y tamaño. La codificación se realiza en memoria para medirla aparte de
la escritura. Un error registra `image.error` con la lámina y fase afectada.

AVIF usa hasta dos trabajadores de imágenes. PowerPoint, WebP y PNG siguen
secuenciales; calidad, resolución, `speed=6` y parámetros de miniatura se
conservan. Los resultados y el progreso se entregan en orden. No se agrega caché.

Comparación del 9 de octubre de 2026: Python 3.13.15, Pillow 12.0.0, seis CPU
lógicas. Se usaron 20 láminas sintéticas de 1280×720, con una imagen de ruido
en la lámina 17, AVIF calidad 82. Tres ejecuciones por modo, intercaladas,
excluyendo generación/copia de entradas y comparación de resultados:

| Trabajadores | Ejecución 1 | Ejecución 2 | Ejecución 3 | Mediana |
|---|---:|---:|---:|---:|
| 1 | 17,365 s | 18,211 s | 19,643 s | 18,211 s |
| 2 | 9,302 s | 11,655 s | 10,047 s | 10,047 s |

La reducción de la mediana de procesamiento de imágenes fue **44,83 %**,
superior al umbral del 10 %. Todas las imágenes y miniaturas fueron idénticas
byte por byte, con el mismo orden. Esto no mide la exportación completa ni
confirma el rendimiento del PPTX original, que no se encontró en las ubicaciones
revisadas. La causa de su demora en la lámina 17 sigue pendiente de las nuevas
mediciones; no se realizó una exportación real con PowerPoint en esta validación.

Para repetir la comparación, usa una carpeta nueva:
`python tests/benchmark_images.py --out <carpeta-temporal-nueva>`.
El script genera las entradas, compara ambos modos tres veces y escribe
`result.json`; sus artefactos son datos de prueba y pueden borrarse después.
