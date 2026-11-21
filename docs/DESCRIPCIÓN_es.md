# py-pdftools 1.6.0: descripción

## Análisis

py-pdftools edita documentos PDF: los anota, los censura, cambia sus etiquetas de página, sus encabezados, pies de página y marcas de agua y el orden de sus páginas, los impone para imprenta y lee el texto de sus páginas escaneadas. Fue desarrollado en noviembre de 2026 por Nicolas Vaughan, que reunió en él cinco programas suyos, cada uno de los cuales hacía una de esas cosas: py-annotate (las anotaciones), py-redact (la censura), py-foliation (las etiquetas de página, los encabezados y pies, las marcas de agua y el orden de las páginas), py-imposition (la imposición) y py-pdfocr (el OCR, en la línea de órdenes).

El requisito central era no perder nada de lo que cada programa ya hacía bien. Todos tenían sus pruebas, sus casos raros resueltos y sus decisiones tomadas; el programa nuevo debía conservarlos, no reescribirlos. Además, tenía que haber una sola ventana y una sola línea de órdenes, y el documento abierto tenía que ser uno, con sus anotaciones, su censura y sus cambios a la vista al mismo tiempo, y con un solo historial para deshacer.

Lo demás vino de las diferencias entre ellos. py-annotate guarda en el mismo documento; py-redact escribe siempre una copia nueva, porque censurar no tiene vuelta atrás; py-foliation guardaba sus cambios en memoria hasta guardar el archivo. Se decidió guardar en el documento todo menos la censura, que sigue escribiendo una copia, comprobada, como en py-redact. La ventana y la línea de órdenes tenían que estar en español y en inglés, y el programa debía instalarse en Linux, Windows y macOS.

## Diseño

El código de los cuatro programas se copió en un paquete nuevo, que no depende de ellos; los programas antiguos quedan como estaban. Sus motores están en cuatro subpaquetes, `annotate`, `redact`, `pages` e `impose`, y lo que compartían está en `core`: la traducción de la interfaz (`interface.py`, `locale/es.xml`), la configuración, el paso a PDF/A y PDF/X con pdf2iso, el dibujo de páginas en procesos propios y la lectura de listas de páginas. `cli/` reúne las dos líneas de órdenes, y `gui/` la ventana.

Se conservaron las dos bibliotecas. PyMuPDF dibuja las páginas, lee y escribe las anotaciones y censura; pikepdf cambia las etiquetas, los encabezados y pies (como capas que pueden quitarse), el orden de las páginas y la imposición. Cada una hace lo que ya hacía en su programa.

La ventana es la de py-annotate, con las páginas una debajo de otra, y una barra de modos encima: Leer, Censurar, Anotar, Foliar e Imponer. Cada modo guarda su propia disposición de la ventana (qué barras y paneles se ven y dónde, las miniaturas), que vuelve al elegirlo, también en la sesión siguiente. Cada modo trae sus barras de herramientas, sus paneles y sus menús, y dice qué anotaciones son suyas: las de los otros modos se ven, pero el ratón las atraviesa. En el modo Imponer, el espacio de trabajo de py-imposition ocupa el lugar de las páginas.

Los recuadros de censura son anotaciones de redacción del propio PDF (`/Redact`), que marcan lo que debe quitarse sin quitarlo: se dibujan, se mueven y se deshacen como cualquier anotación, se guardan en el documento sin aplicar, y solo la copia censurada elimina lo que hay debajo. Los cambios del documento mismo (etiquetas, orden de las páginas, capas, el resultado de una imposición) se hacen en el acto sobre una copia de trabajo, y Guardar la escribe como el documento.

La línea de órdenes, `py-pdftools`, tiene grupos: `labels`, `view`, `header-footer`, `watermark`, `pages`, `impose` (las treinta órdenes de py-imposition, juntas), `ocr`, `combine` y `from-images`.

### La ventana al trabajar

Las miniaturas admiten varias páginas a la vez, en cualquier modo, con el menú de páginas de Foliar; la casilla de la página muestra su etiqueta y acepta una etiqueta o un número. El OCR tiene su modo, entre Leer y Censurar, y un gestor de idiomas que descarga o quita los modelos mejores de tesseract. Una herramienta selecciona texto como un editor, también entre páginas. Puede seguir en segundo plano, con un icono en la bandeja, y una página de rendimiento fija la memoria y la calidad del dibujo. Archivo, Editar y Ver van en submenús, y las barras se configuran como en KDE: botones, texto, tamaño de los iconos, bloqueo.

### Moverse por el documento

Los marcadores son un panel común a todos los modos, y allí se editan. Los enlaces se siguen, y también las direcciones web y de correo escritas en el texto; cada salto queda en un historial (Alt+Izquierda, Alt+Derecha). La vista admite dos páginas lado a lado, más zooms, el giro sin tocar el archivo, colores de lectura y pantalla completa. Cada pestaña es una ventana entera dentro de otra, que puede mostrar dos a la vez. Un archivo que otro programa cambia se vuelve a abrir.

### Seguridad, formularios y archivos nuevos

Censurar busca texto solo cubierto (que sigue en el archivo bajo un recuadro, una imagen o una anotación) y quita también las capas apagadas. Archivo > Proteger con contraseñas cifra con AES-256; Firmas digitales firma con un ID digital (con pyHanko), crea uno propio y comprueba las firmas. El panel Formulario rellena los campos, con los formatos, comprobaciones y sumas de las funciones estándar hechos en Python, sin JavaScript, y lleva sus datos dentro y fuera (JSON, CSV, XFDF, FDF). Archivo combina PDF, hace uno de imágenes, guarda copias más pequeñas o con otra versión de PDF, y exporta páginas, imágenes y texto; Foliar divide también por marcadores y por tamaño; la herramienta Enlace dibuja enlaces.

## Implementación

Está escrito en Python 3.14 o superior, con PyMuPDF, pikepdf, reportlab y PySide6 (Qt 6). Son 151 archivos de Python, unas 41 700 líneas (una décima parte, comentarios), y 3028 textos de la interfaz traducidos al español.

### Del código antiguo al paquete nuevo

Un script copió los módulos de cada programa y reescribió sus importaciones. Dos módulos con el mismo nombre hacían cosas distintas: las listas de páginas de py-imposition rechazaban una página más allá de la última, y las de py-redact la dejaban fuera; el módulo común hace las dos cosas. Las cuatro traducciones se unieron en un archivo, y de 35 textos con dos traducciones se eligió una, salvo donde el sentido cambiaba (*izquierda* como alineación, *izquierdo* como margen). Las claves que los programas antiguos escriben en un PDF conservan su nombre, para que sus documentos se sigan leyendo.

### La línea de órdenes

Los dos analizadores de argumentos no se reescribieron: sus órdenes se injertaron en un árbol, que da la ayuda, el manual y los scripts de completado de bash, fish y zsh, ahora de dos niveles, y cada orden sigue ejecutándose donde lo hacía.

### Las copias de trabajo

Cada cambio del documento escribe primero el documento con sus anotaciones, hace el cambio con pikepdf y abre el resultado; las anotaciones van con sus páginas. El historial guarda, antes de cada cambio, el archivo, las anotaciones y la página, de modo que Deshacer recorre por igual los cambios de las anotaciones y los del documento.

Las copias están en el disco (`~/.cache/py-pdftools/work`), no en /tmp, que en Fedora está en la memoria; el historial guarda los diez últimos cambios del documento.

### Documentos con miles de anotaciones

Con 300 páginas y 3000 anotaciones, cambiar las etiquetas tardaba casi dos segundos: las anotaciones se leían dos veces. Ahora la ventana recuerda las del archivo que muestra, y PyMuPDF escribe las etiquetas al escribir las anotaciones, sin renumerar los objetos: el cambio tarda 0,3 segundos.

### pdf2iso, incluido

pdf2iso, el programa del autor que hace las copias PDF/A y PDF/X, era un programa aparte, que había que instalar y que se buscaba en el PATH. Ahora es un módulo del paquete (`core/pdf2iso.py`), que se ejecuta con el mismo Python en un proceso propio, y también una orden, `py-pdftools pdf2iso`. Solo Ghostscript sigue siendo un programa externo.

### Las etiquetas de página

El PyMuPDF de Fedora (1.28) lee el `/Type /PageLabel` de un intervalo como su prefijo, y mostraba «ageLabeli». La ventana y las exportaciones leen ahora las etiquetas con el motor de py-foliation.

### Documentos grandes

Del código de PDFCraft, un editor escrito en Rust, se tomaron cuatro ideas. Hay varios procesos de dibujo por carril, y una página que tarda más de 20 segundos, o hace caer su proceso, se muestra en gris con la causa. Solo se hacen las miniaturas cercanas a las que se ven, después de las páginas a la vista. Con mucho zoom, la página se dibuja entera a 2048 píxeles como máximo, y la parte que se ve, en teselas de 1024 píxeles a la escala completa.

### Una sola copia de cada cosa

Los cuatro programas traían copias de lo mismo: abrir un PDF, rectángulos y colores, las palabras bajo el ratón, las matrices de PDF (tres veces), la orden `interface`, los campos comunes de encabezados y marcas de agua, el campo de pdf2iso en tres diálogos de ajustes, un botón y un menú de colores. Se buscaron con pylint y comparando la sintaxis de cada función, y cada una quedó en un solo lugar (`core/pdfdoc.py`, `core/matrix.py`, `stamps.StampSettings`, `gui/conform_field.py`, entre otros).

### OCR

El OCR, el mismo de py-pdfocr, usa el programa tesseract del sistema, en varios procesos a la vez; de cada palabra lee el lugar y la confianza. Tiene su propio modo. El texto se escribe invisible en el documento, como un cambio que se deshace, después de revisar las palabras dudosas junto a su imagen. Las páginas de lado se giran antes, con el modelo osd.

## Validación

Hay 590 pruebas automáticas (`uv run pytest`): las de los cuatro programas, trasladadas al paquete nuevo (96 de anotaciones, 71 de censura, 115 de páginas, etiquetas y capas, 87 de imposición), y las de lo nuevo: la línea de órdenes entera y su completado en bash y fish, los modos de la ventana, los recuadros como marcas de redacción, las copias de trabajo con deshacer y rehacer, la navegación (marcadores, enlaces, historial, vistas, pestañas), la seguridad (texto solo cubierto, capas ocultas, contraseñas), las barras de herramientas, la combinación de archivos, los PDF de imágenes, las copias más pequeñas, los enlaces, los formularios, las firmas, los menús y las barras, las exportaciones, la partición y la versión de PDF, la interfaz en español (cada texto traducido y ninguno de sobra) y el empaquetado.

La ventana se prueba manejándola como lo haría un usuario, con eventos del ratón sobre las páginas, en cada modo. La copia censurada se escribe también en un proceso propio, como lo hace la ventana, y se comprueba que nada de lo que había debajo de los recuadros pueda leerse; la imposición ejecuta sus órdenes en otro proceso. Una prueba comprueba que el manual siga siendo la ayuda de la línea de órdenes.

Las ventanas se revisaron además a ojo, con capturas de cada modo en los dos idiomas. El RPM vuelve a correr todas las pruebas con los paquetes de Fedora; así apareció el fallo de las etiquetas de PyMuPDF 1.28. El instalador de Linux se probó en una carpeta personal hecha para la prueba.

Las pruebas corren también en GitHub, en Ubuntu y en Windows, contra el programa instalado. Allí fallaban desde el principio (faltaban qpdf y pdftotext; en Windows, además, no se puede borrar un archivo abierto ni existe `SIGALRM`), y se corrigió: el flujo instala las herramientas, las pruebas que las necesitan se saltan donde no están y las carpetas temporales se borran aunque quede un archivo abierto.

## Plataforma

Funciona en Linux, y debería funcionar en Windows y macOS, donde lo instalan los instaladores de `install/`; un flujo de trabajo de GitHub los prueba allí. Necesita Python 3.14 o superior, con PyMuPDF, pikepdf, reportlab y PySide6. La AppImage lleva su propio Python con todo eso, y el RPM es para Fedora. Para PDF/A y PDF/X hace falta Ghostscript (pdf2iso, otro programa del autor, viene incluido); para el OCR, el programa tesseract y los idiomas de los documentos. Las firmas digitales necesitan pyHanko, que se instala aparte (`pip install 'py-pdftools[signatures]'`); la AppImage y los instaladores ya lo traen, el RPM no, porque Fedora no lo empaqueta.

Es una aplicación de escritorio y no necesita internet, salvo para descargar, si se quiere, los modelos más precisos de Tesseract, y para pedir a un servidor un sello de tiempo al firmar, si se le indica uno; las firmas se comprueban sin conexión. Nada del usuario sale del equipo.

## Ambiente

Fue desarrollado en Fedora Linux 45 con KDE Plasma, con Python 3.14 y uv, y con git. El código está en repositorios de GitHub (https://github.com/nivaca/py-pdftools) y de Codeberg (https://codeberg.org/nivaca/py-pdftools), públicos. Un script (`tools/release.py`) corre las pruebas, hace la rueda, el paquete fuente, el ZIP, la AppImage y el RPM firmado, pone la etiqueta, publica en los dos sitios y manda el RPM fuente a Copr (https://copr.fedorainfracloud.org/coprs/nivaca/py-pdftools/), que lo construye para Fedora 45 y Rawhide.

En Fedora, `sudo dnf copr enable nivaca/py-pdftools` y `sudo dnf install py-pdftools` lo instalan con su entrada en el menú y su manual. Desde el código fuente, `uv sync` lo prepara; `uv run py-pdftools-gui` abre la ventana y `uv run py-pdftools` es la línea de órdenes. En Linux y macOS, `install/install.sh` lo instala para el usuario, con su entrada en el menú; en Windows, `install\install.bat`. Configuración tiene páginas para lo general, la apariencia (colores, tamaño, idioma, barras), los documentos (cómo se abren, los recientes), los colores, los atajos, las categorías y el rendimiento; con «Empezar con la sesión», arranca en la bandeja al iniciar la sesión. Queda en la carpeta de configuración del usuario (`~/.config/py-pdftools/config.toml` en Linux, o `$PY_PDFTOOLS_CONFIG`); en macOS, en `~/Library/Application Support/py-pdftools/`, y en Windows, en `%APPDATA%\py-pdftools\`.
