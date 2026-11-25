# Registro de cambios

Los cambios notables de py-pdftools. Las versiones publicadas, con la
AppImage, el RPM, la rueda y el código fuente, están en
[Codeberg](https://codeberg.org/nivaca/py-pdftools/releases) y
[GitHub](https://github.com/nivaca/py-pdftools/releases).

## Sin publicar

- Archivo > Guardar una copia > Con las páginas como imágenes: una copia en
  la que las páginas elegidas (todas, o una lista como `2-5, 9, last`) son
  imágenes de sí mismas, a la resolución elegida (300 ppp por omisión), en
  PNG o JPEG, en color o en gris. Se ven igual, pero ya no tienen texto,
  fuentes, anotaciones ni campos de formulario (estos dos, dibujados en la
  imagen). Los marcadores, las etiquetas, los enlaces, las demás páginas y
  la protección se mantienen. En la línea de órdenes: `py-pdftools
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
