# Registro de cambios

Los cambios notables de py-pdftools. Las versiones publicadas, con la
AppImage, el RPM, la rueda y el código fuente, están en
[Codeberg](https://codeberg.org/nivaca/py-pdftools/releases) y
[GitHub](https://github.com/nivaca/py-pdftools/releases).

## Sin publicar

- Las anotaciones de un documento pueden guardarse fuera del PDF, en un
  archivo propio junto a él: para libro.pdf, libro.pdf.pdfnotes (XML). El
  PDF queda entonces exactamente como estaba. Archivo > Anotaciones en un
  archivo aparte pasa un documento de una manera a la otra y guarda
  enseguida; al pasar al archivo aparte pregunta si las anotaciones propias
  del PDF se quedan en él o se le quitan. Nada se pierde: las que venían
  del PDF también se editan, y al volver se cambian donde están; de las que
  se quitaron se guarda una copia exacta de sus objetos, que vuelve tal
  cual, con las claves y el aspecto que les dieron otros programas.
- Configuración > Documentos > Guardar las anotaciones: en el PDF mismo
  (como antes) o en un archivo aparte, para los documentos que aún no lo
  tienen.
- Archivo > Guardar una copia > Con las anotaciones en el PDF, para un
  documento que las guarda aparte.
- Archivo > Importar anotaciones > De las notas de Skim (.skim): las notas
  de Skim, el lector de PDF del Mac, en sus dos formas.
- Corregido: un movimiento rápido de la goma dejaba sin borrar lo que
  cruzaba entre dos posiciones del ratón; ahora borra en todo el camino.
- Con las páginas dibujadas por la tarjeta gráfica, los resaltados, las
  áreas y el marcador se dibujan translúcidos en vez de multiplicados, lo
  que el pintor de OpenGL no sabe hacer: escribía «Unsupported composition
  mode» por cada uno.
- Los mensajes de las bibliotecas de KDE (`kf.*`, del diálogo de archivos
  de Plasma) ya no llenan la terminal; `QT_LOGGING_RULES` sigue mandando.
- Corregido: guardar, un cambio del documento mismo que deja sus páginas
  como estaban (las etiquetas de página, en Foliar), y deshacerlo o
  rehacerlo llevaban la vista al principio de la página visible; ahora se
  queda exactamente donde estaba.
- El panel de anotaciones ya no se abre solo con el modo Anotar; F4 lo
  muestra. Configuración > Aspecto > Mostrar el panel de anotaciones al
  elegir el modo Anotar (desactivado al principio) devuelve lo de antes.
- Archivo > Abrir reciente abre el documento en una pestaña nueva junto a
  la visible, en vez de reemplazarlo; en una ventana sin documento se abre
  ahí, y uno ya abierto solo pasa al frente.
- Archivo > Exportar tiene Texto (Markdown)… y Texto (simple, UTF-8)…,
  cada diálogo con su tipo elegido al principio (HTML sigue en los dos), y
  Archivo > Exportar > Anotaciones tiene Como informe (texto simple,
  UTF-8)…, el informe sin las marcas de Markdown (títulos subrayados, el
  texto marcado entre comillas).
- Salir con más de un documento abierto, o cerrar una ventana de pestañas
  que tiene varios, pregunta antes. Configuración > General > Avisar antes
  de cerrar varios documentos a la vez (activado al principio) lo apaga, y
  también desmarcar «Volver a avisarme la próxima vez» en la pregunta.
- El instalador para Windows se puede firmar con Authenticode por SignPath
  (firma de código gratuita para proyectos de código abierto, con el
  certificado de SignPath Foundation), desde
  `.github/workflows/installers.yml` en cada etiqueta de versión, una vez
  que el proyecto sea aceptado allí; `CODE_SIGNING_POLICY.md` es su
  política, y el instalador dice ahora el nombre y la versión del producto.
- Corregido: con «Dibujar las páginas con la tarjeta gráfica (OpenGL)»
  activado (Configuración > Rendimiento), el texto de las páginas se veía
  borroso a cualquier zoom. La página cae a menudo entre dos píxeles de la
  pantalla, y OpenGL suavizaba allí su imagen; ahora una página mostrada a
  su propio tamaño se dibuja sobre píxeles enteros, tan nítida como sin la
  tarjeta gráfica.
- Los procesos que dibujan las páginas arrancan con el programa, mientras
  se construye su ventana, así que la primera página llega una décima de
  segundo antes; el que muere con una página se reemplaza enseguida.
- Las miniaturas se dibujan con menos prioridad que las páginas a la vista
  y la ventana, que reciben primero el procesador cuando el equipo está
  ocupado.
- Corregido: tras un cambio del documento mismo (etiquetas, páginas giradas
  o movidas, OCR, enlaces, marcadores...), la vista podía saltar a otra
  página, de la 40 a la 19: la lista de miniaturas, hecha de nuevo, se
  tomaba por un clic en una de ellas.
- Tras un cambio del documento mismo, al deshacerlo o al guardar, las
  páginas y miniaturas que el cambio no tocó se muestran enseguida tal como
  estaban dibujadas, vayan donde vayan, en lugar de dibujarse otra vez;
  solo se dibujan las que cambiaron. En un diccionario escaneado, las
  páginas a la vista volvieron en 0,1 s en lugar de 0,5 a 0,8.
- Las palabras de una página a la vista las lee el proceso que la dibuja, la
  primera vez, y llegan con ella: seleccionar texto, el cursor sobre el
  texto y los enlaces del texto ya no detienen la ventana un momento en una
  página densa (de 5 a 15 ms, a veces 90). Las de una página se leen una
  vez para todo, no dos.
- Configuración > Rendimiento > Guardar las miniaturas en el disco
  (desactivado al principio): un documento escaneado que se abre de nuevo
  muestra sus miniaturas enseguida (en una prueba, 0,1 s en lugar de 0,4).
  Se guardan según lo que dibuja cada página, hasta 200 MB, y se borran
  todas al escribir una copia censurada o al desactivar el ajuste.
- Las páginas que se guardan dibujadas se limitan por la memoria que
  ocupan (64, 256 o 768 MB, según el ajuste de memoria), no por su número:
  a un zoom bajo se guardan más, y a uno alto dieciséis páginas grandes ya
  no ocupan un gigabyte.
- Corregido: en Windows, y en Linux sin los ajustes de un escritorio, Salir
  había perdido Ctrl+Q en 1.18.0 (Qt no da allí una tecla estándar para
  ello): Ctrl+Q y Ctrl+W se nombran ahora de forma explícita, además de las
  teclas de la plataforma.
- Ctrl+W es ahora Archivo > Cerrar el documento: cierra solo este
  documento, su pestaña o su ventana, y el programa sigue abierto; tras el
  último documento queda una ventana vacía (era Cerrar la ventana, que con
  la última terminaba el programa). Alt+F4 ahora también sale, como Ctrl+Q.
- Corregido: Archivo > Guardar una copia > Con tamaño reducido (y
  `py-pdftools reduce`) podía volver negra una forma blanca, como el
  recuadro detrás del logo de un membrete. La función de MuPDF que vuelve a
  dibujar las imágenes pasaba cada página por un filtro que perdía un color
  de relleno dado sin espacio de color (algo válido en PDF). Ahora
  py-pdftools vuelve a dibujar las imágenes él mismo, objeto por objeto, y
  el contenido de las páginas nunca se reescribe: solo se comprime otra
  vez, byte a byte. Las imágenes en blanco y negro (de un bit) se dejan
  como están. Las páginas como imágenes tampoco reescriben ya el contenido
  de las páginas que no convierten.
- Ayuda > Restablecer todos los ajustes: después de preguntar, se cierran
  todas las ventanas (cada una pregunta por sus cambios sin guardar),
  `config.toml` se aparta como copia fechada
  (`config-AAAA-MM-DD-HHMMSS.toml`, a su lado) y el programa termina, para
  volver a empezar con los valores habituales. Los sellos, las firmas, los
  ID digitales, los certificados de confianza, las recetas y los perfiles
  no se tocan.

- La parte Crítica textual de las propiedades de una anotación está
  plegada: una línea muestra la entrada como en un aparato (`Conjetura:
  lema ] lectura A`), y una flecha despliega sus campos. Marcar la parte
  los despliega. El diálogo queda unos 250 píxeles más bajo.

- Archivo > Guardar una copia > Con las páginas como imágenes: una copia en
  la que las páginas elegidas (todas, o una lista como `2-5, 9, last`) son
  imágenes de sí mismas, a la resolución elegida (300 ppp por omisión), en
  PNG o JPEG, en color o en gris. Se ven igual, pero ya no tienen texto,
  fuentes, anotaciones ni campos de formulario (estos dos, dibujados en la
  imagen). Los marcadores, las etiquetas, los enlaces, las demás páginas y
  la protección se mantienen. La copia se abre en una pestaña nueva. En la línea de órdenes: `py-pdftools
  rasterize ARCHIVO -o SALIDA [--pages] [--dpi] [--format] [--quality]
  [--gray]`.

- `tools/zenodo.py`: la descripción del depósito es ahora el README entero
  de la etiqueta, en HTML. El borrador recibe además el colaborador (el
  director del proyecto), los idiomas, el copyright, el repositorio en
  GitHub, el lenguaje de programación y el estado del desarrollo; estos
  últimos, por la API de registros de Zenodo, porque la de depósitos no los
  admite. El token puede guardarse en el llavero del escritorio
  (`secret-tool store --label="Zenodo token" service zenodo`) en vez de en
  `$ZENODO_TOKEN`; `tools/zenodo.py check-token` dice si hay uno.

- `tools/zenodo.py` prepara el depósito de una versión en Zenodo. `collect`
  deja en `dist/zenodo/` el árbol de la etiqueta como
  `py-pdftools-VERSIÓN-source.tar.gz`, con su firma, un `SHA256SUMS` del
  depósito, firmado, y la clave pública, y comprueba cada firma con solo esa
  clave (`--packages` añade los archivos de la versión). `upload` lo sube a
  Zenodo como borrador, versión nueva del depósito si ya lo hay, y nunca lo
  publica. `tools/release.py` reúne ahora el depósito después de la etiqueta
  y lo sube como borrador, salvo con `--no-zenodo`. Los metadatos están en
  `.zenodo.json`.
- `tools/release.py` publica ahora cada versión en Zenodo
  (`tools/zenodo.py upload --publish`), en vez de dejar un borrador;
  `--zenodo-draft` todavía lo deja. `tools/zenodo.py publish` publica un
  borrador que ya está allí (por omisión, el que espera con el título del
  proyecto).

## 1.2.0 — 2026-11-20

- **Redact > Find text only covered** (Censurar > Buscar texto solo
  cubierto): texto que sigue en el archivo debajo de un recuadro, una
  imagen o una anotación dibujados encima, de modo que parece censurado
  pero puede copiarse o encontrarse. Se muestra junto con lo que lo
  cubre, y se le pueden poner recuadros encima para que la copia
  censurada lo saque.
- **Las capas ocultas se eliminan** al sanear (una clase propia en
  Remove hidden information, Quitar información oculta) y al limpiar la
  copia censurada: lo que contienen las capas desactivadas se saca de las
  páginas, y también las capas mismas, con sus nombres.
- **File > Protect with passwords** (Archivo > Proteger con
  contraseñas): una contraseña para abrir el documento (AES-256), otra
  para sus permisos (imprimir, copiar, comentarios y formularios,
  páginas, otros cambios), o las dos. Un archivo protegido solo en sus
  permisos sigue así ahora cuando se guardan sus anotaciones, y en las
  copias censuradas y saneadas.
- Las barras de herramientas pueden cambiarse (Settings > Customize the
  toolbars, Configuración > Personalizar las barras de herramientas, o
  un clic derecho en una barra): sus botones y su orden, con todas las
  acciones de los menús, las herramientas y los modos; pueden añadirse y
  quitarse barras propias.
- Iconos en los botones de los modos, de la barra de OCR y del panel
  Impose.

## 1.1.0 — 2026-11-20

Moverse por un documento, en todos los modos. Esta versión trae también
los cambios de la 1.0.0, que no se etiquetó ni se publicó por separado.

- **Marcadores** (View > Bookmarks, Ver > Marcadores, F5): un panel con
  los marcadores del documento en forma de árbol, con un filtro. Su menú
  del clic derecho añade un marcador en el lugar que se muestra, y
  renombra, mueve, sangra, da estilo o borra marcadores, o los crea a
  partir de los títulos del texto.
- **Los enlaces** se siguen con un clic (Ctrl+clic con Select text): a
  su lugar en el documento, a otro PDF o, después de preguntar, a una
  dirección web o de correo. Las direcciones escritas en el texto también
  son enlaces. Los enlaces que inician un programa no se siguen.
- **Previous view y Next view** (Vista anterior y Vista siguiente,
  Alt+Izquierda, Alt+Derecha) recorren los lugares a los que se saltó con
  enlaces, marcadores, la casilla de página y Find.
- **Abrir en un lugar**: `book.pdf#page=12` o `#nameddest=intro`; cada
  archivo se abre donde se dejó, o como él mismo lo pide; y, si la
  configuración lo indica, los documentos abiertos al final de la última
  sesión vuelven a abrirse.
- **Dos páginas lado a lado** (Ctrl+Shift+2), con la primera página sola
  como portada si se quiere.
- Más zooms: ajustar a la altura (Ctrl+8), ajustar al área impresa
  (Ctrl+7), tamaño real (Ctrl+Shift+0), un porcentaje escrito en la
  casilla del zoom y la herramienta Zoom to area (Ampliar una zona, Z).
- Girar la vista (Ctrl+], Ctrl+[) sin cambiar el archivo.
- Colores de lectura (View > Reading colours, Ver > Colores de lectura):
  blanco, amarillo o verde sobre negro, claro sobre gris oscuro, o
  colores propios.
- Pantalla completa como presentación (F11); las páginas con un tiempo
  de visualización pasan solas, y las que tienen una transición aparecen
  con un fundido.
- **Pestañas y vista dividida**: File > Open in a new tab (Archivo >
  Abrir en una pestaña nueva, Ctrl+T), o todos los documentos así; View >
  Split the view (Ver > Dividir la vista, `Ctrl+\`) muestra dos
  documentos lado a lado.
- Un documento que otro programa cambia en el disco se vuelve a abrir en
  el mismo lugar (después de preguntar, si hay algo sin guardar).
- Los detalles de una página (etiqueta, tamaño, papel, orientación,
  anotaciones) al pasar el puntero sobre su miniatura.
- Mantener pulsado el espacio convierte cualquier herramienta en Hand
  (Mano); el botón central desplaza solo; los espacios entre las páginas
  pueden ocultarse.
- 466 pruebas.

## 1.0.0 — 2026-11-20

Sin etiqueta; sus cambios se publicaron con la 1.1.0.

- **El modo OCR**, entre Read (Leer) y Redact (Censurar) (Ctrl+2): su
  panel elige las páginas, ordena los idiomas, endereza las páginas que
  están de lado y fija por debajo de qué confianza una palabra es dudosa.
- **Select text** (Seleccionar texto, X), junto a Hand en todos los
  modos: arrastrar sobre el texto, también de una página a otra;
  Alt+arrastrar selecciona una columna; doble clic en una palabra, triple
  clic en una línea. Ctrl+C lo copia, y un clic derecho lo resalta, lo
  subraya, lo tacha, lo marca para censurarlo o lo busca.
- **Ejecución en segundo plano** (Settings > General): cuando se cierra
  la última ventana, el programa sigue corriendo con un icono en la
  bandeja del sistema, y `py-pdftools-gui`, si se inicia de nuevo, le
  pasa sus archivos, que abre enseguida. File > Quit (Archivo > Salir) lo
  termina.
- Settings > Performance (Configuración > Rendimiento): un perfil de
  memoria (bajo, normal, alto o todas las páginas) fija cuántas páginas,
  teselas y miniaturas se guardan y cuántos procesos las dibujan;
  selecciones con transparencia o como contornos; el suavizado del texto
  y de los gráficos.
- El menú de páginas está organizado en grupos, con un título que nombra
  las páginas elegidas, y en submenús.

## 0.5.0 — 2026-11-20

- **Varias miniaturas a la vez**: Ctrl+clic y Shift+clic eligen páginas
  sin ir a ellas, en cualquier modo, y un clic derecho da el menú de
  páginas para ellas. Son también las páginas elegidas de Foliate
  (Foliar).
- La casilla de página muestra la etiqueta de la página visible y acepta
  una etiqueta, (n) para la página n, o un número.
- Un gestor de idiomas de OCR, en la configuración, enumera todos los
  idiomas que tesseract puede leer y descarga, actualiza o elimina sus
  modelos más precisos.

## 0.4.0 — 2026-11-20

- **OCR**: Edit > Recognise text (OCR) (Editar > Reconocer el texto
  (OCR), Ctrl+Shift+O) lee las páginas escaneadas con el programa
  tesseract y escribe su texto, invisible, en el documento, como un solo
  cambio que puede deshacerse. Las páginas que están de lado pueden
  enderezarse antes, y las palabras dudosas se muestran junto a su imagen
  para corregirlas.
- La copia con texto buscable usa el mismo motor, con varias páginas a
  la vez.
- `py-pdftools ocr` hace lo mismo desde la línea de órdenes (`--lang`,
  `--pages`, `--rotate`, `--report`, `--languages`, `--download`).
- La indicación de cada modo aparece sobre las páginas unos segundos, y
  de nuevo con Help > Tips for this mode (Ayuda > Consejos de este modo,
  F1).
- Las pruebas dibujan sus ventanas en un servidor X propio (Xvfb) cuando
  está instalado, no en la pantalla del usuario.

## 0.3.0 — 2026-11-20

Documentos grandes.

- **Copias de trabajo en el disco**, en `~/.cache/py-pdftools/work`, no
  en la carpeta temporal, que en Fedora está en la memoria: cada cambio
  de un documento grande ocupaba tanta RAM como el documento. El
  historial guarda los últimos diez cambios del documento.
- Una página que tarda más de 20 segundos en dibujarse, o hace morir su
  proceso, se muestra en gris con el motivo y no se vuelve a intentar.
- Solo se hacen las miniaturas cercanas a las visibles, y se guardan 400
  como máximo: las de 200 páginas escaneadas tardan 0,9 s en lugar de
  30 s.
- **Zoom profundo por teselas**: una página grande se dibuja entera a
  menor resolución, y la parte visible en teselas nítidas de 1024
  píxeles.
- 416 pruebas.

## 0.2.0 — 2026-11-19

- **Cinco modos**, en el orden del trabajo sobre un documento: Read,
  Redact, Annotate, Foliate (el antiguo modo Pages) e Impose (Leer,
  Censurar, Anotar, Foliar e Imponer; Ctrl+1 a Ctrl+5). Cada modo
  conserva su propia disposición de la ventana, también en la sesión
  siguiente.
- **pdf2iso viene incluido** (`core/pdf2iso.py`, de pdf2iso 2.1): las
  copias PDF/A y PDF/X solo necesitan Ghostscript. La línea de órdenes
  tiene `py-pdftools pdf2iso`.
- Correcciones: las partes que hacen `pages --split-every` y
  `--split-at` conservan la protección del original y obedecen a
  `--conform`; un comentario más largo que una página ya no rompe el
  resumen de los comentarios; Save ya no falla con un TypeError después
  de deshacer un cambio del documento mismo; cambiar el idioma de la
  interfaz conserva los cambios sin guardar; una página dibujada sin sus
  anotaciones ya no las pierde la vez siguiente.
- El código que los cuatro programas tenían en varias copias está ahora
  en un solo lugar cada uno (`core/pdfdoc.py`, `core/matrix.py` y
  otros). Unos 1900 comentarios en el código.
- Las pruebas pasan en Linux y Windows (407 pruebas). Páginas de manual.

## 0.1.0 — 2026-11-19

- Primera versión: py-annotate, py-redact, py-foliation y py-imposition
  en una sola ventana y una sola línea de órdenes, en inglés y en
  español.
- La ventana tiene cuatro modos: Annotate, Redact (de py-redact), Pages
  (de py-foliation: etiquetas de página, encabezados y pies, marcas de
  agua, el orden de las páginas) e Impose (de py-imposition). Los cambios
  del documento mismo se hacen sobre una copia de trabajo y se deshacen
  junto con las anotaciones, en un solo historial.
- La línea de órdenes, `py-pdftools`, tiene `labels`, `view`,
  `header-footer`, `watermark`, `pages` e `impose`.
- Paquetes: una AppImage, un RPM firmado para Fedora (también en Copr,
  `nivaca/py-pdftools`) e instaladores para Linux, macOS y Windows.
