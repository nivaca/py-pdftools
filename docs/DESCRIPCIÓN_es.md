# py-pdftools 1.13.0: descripción

## Análisis

py-pdftools edita documentos PDF: los anota, los censura, cambia sus etiquetas de página, sus encabezados, pies de página y marcas de agua y el orden de sus páginas, los impone para imprenta y lee el texto de sus páginas escaneadas. Fue desarrollado en noviembre de 2026 por Nicolas Vaughan, que reunió en él seis programas suyos, cada uno de los cuales hacía una de esas cosas: py-annotate (las anotaciones), py-redact (la censura), py-foliation (las etiquetas de página, los encabezados y pies, las marcas de agua y el orden de las páginas), py-imposition (la imposición), py-pdfocr (el OCR, en la línea de órdenes) y pdf-word-finder (las páginas en que aparece cada palabra de una lista, para un índice).

El requisito central era no perder nada de lo que cada programa ya hacía bien. Todos tenían sus pruebas, sus casos raros resueltos y sus decisiones tomadas; el programa nuevo debía conservarlos, no reescribirlos. Además, tenía que haber una sola ventana y una sola línea de órdenes, y el documento abierto tenía que ser uno, con sus anotaciones, su censura y sus cambios a la vista al mismo tiempo, y con un solo historial para deshacer.

Lo demás vino de las diferencias entre ellos. py-annotate guarda en el mismo documento; py-redact escribe siempre una copia nueva, porque censurar no tiene vuelta atrás; py-foliation guardaba sus cambios en memoria hasta guardar el archivo. Se decidió guardar en el documento todo menos la censura, que sigue escribiendo una copia, comprobada, como en py-redact. La ventana y la línea de órdenes tenían que estar en español y en inglés, y el programa debía instalarse en Linux, Windows y macOS.

El uso diario trajo más requisitos, tomados de otros visores de PDF: una barra para ir a la primera, la anterior, la siguiente y la última página, con la casilla de la página, que se pudiera editar como las demás; una ventana con las propiedades del PDF (sus metadatos, su archivo, su contenido, su seguridad y sus fuentes); y menos ayudas a la vista: los consejos de los modos y las ayudas emergentes quedaron desactivados al principio, y se activan en Configuración > Aspecto. Después, la barra de las pestañas quedó oculta con un solo documento (salvo que una opción la pida), los botones de página anterior y siguiente quedaron solo en la barra de páginas, y la configuración dejó de pedir otro pdf2iso, que ya forma parte del programa; sus pestañas se desplazan cuando la ventana es pequeña, en vez de apretar sus filas. El panel de los marcadores, por último, dejó de abrirse solo: aunque el documento lo pida (`/PageMode /UseOutlines`) o la disposición guardada de un modo lo traiga, está oculto hasta que el usuario lo abre con F5. Las ayudas emergentes de las barras de herramientas, en cambio, se ven siempre, aunque el ajuste que las demás obedecen esté apagado. Y para buscar una palabra sin abrir el diálogo de búsqueda se añadió Buscar mientras se escribe (`gui/findbar.py`, Ctrl+F). Las barras se agruparon por clases de trabajo, y pueden restablecerse. Las miniaturas, por último, quedaron en el centro de su panel, por ancho que sea, y muestran la etiqueta de cada página o, si no la tiene, su número, nunca los dos. Configuración > General tiene además una revisión de la configuración (`core/health.py`, `gui/health_dialog.py`): lo que el programa necesita y si lo tiene, los ajustes del archivo que no valen y los atajos repetidos, cada cosa con lo que hay que hacer.

Por último se incorporó pdf-word-finder, otro programa del autor: dada una lista de palabras, frases o expresiones regulares, dice en qué páginas aparece cada una, según el número impreso en ellas (sus etiquetas), en renglones listos para el índice de un libro. Su búsqueda y su informe se copiaron sin cambiar sus reglas en `pages/wordfinder.py`; el texto lo lee ahora PyMuPDF, y las etiquetas, el mismo lector que el resto del programa. Su ventana pasó a ser Editar > Índice de palabras, y su línea de órdenes, `py-pdftools find-words`.

## Diseño

El código de los cuatro programas se copió en un paquete nuevo, que no depende de ellos; los programas antiguos quedan como estaban. Sus motores están en cuatro subpaquetes, `annotate`, `redact`, `pages` e `impose`, y lo que compartían está en `core`: la traducción de la interfaz (`interface.py`, `locale/es.xml`), la configuración, el paso a PDF/A y PDF/X con pdf2iso, el dibujo de páginas en procesos propios y la lectura de listas de páginas. `cli/` reúne las dos líneas de órdenes, y `gui/` la ventana.

Se conservaron las dos bibliotecas. PyMuPDF dibuja las páginas, lee y escribe las anotaciones y censura; pikepdf cambia las etiquetas, los encabezados y pies (como capas que pueden quitarse), el orden de las páginas y la imposición.

La ventana es la de py-annotate, con las páginas una debajo de otra y una barra de modos: Leer, Censurar, Anotar, Foliar e Imponer. Cada modo guarda su disposición de la ventana (barras, paneles, miniaturas), que vuelve al elegirlo, también en la sesión siguiente. Cada modo trae sus barras de herramientas, sus paneles y sus menús, y dice qué anotaciones son suyas: las de los otros modos se ven, pero el ratón las atraviesa. En el modo Imponer, el espacio de trabajo de py-imposition ocupa el lugar de las páginas.

Los recuadros de censura son anotaciones de redacción del propio PDF (`/Redact`), que marcan lo que debe quitarse sin quitarlo: se dibujan, se mueven y se deshacen como cualquier anotación, se guardan en el documento sin aplicar, y solo la copia censurada elimina lo que hay debajo. Los cambios del documento mismo (etiquetas, orden de las páginas, capas, el resultado de una imposición) se hacen en el acto sobre una copia de trabajo, y Guardar la escribe como el documento.

### La ventana al trabajar

Las miniaturas admiten varias páginas a la vez, en cualquier modo, con el menú de páginas de Foliar; la casilla de la página muestra su etiqueta y acepta una etiqueta o un número. El OCR tiene su modo, entre Leer y Censurar, y un gestor de idiomas que descarga o quita los modelos mejores de tesseract. Una herramienta selecciona texto como un editor, también entre páginas, un panel (F8) da todos los lugares de un texto y otro (F9) los archivos adjuntos. Puede seguir en segundo plano, con un icono en la bandeja. Archivo, Editar y Ver van en submenús, una paleta (Ctrl+Alt+I) busca cualquier orden por su nombre, y las barras se configuran como en KDE: botones, texto, tamaño de los iconos, bloqueo.

### Moverse por el documento

Los marcadores son un panel común a todos los modos, y allí se editan; Ctrl+B añade uno, y Ver > Ir a lleva al siguiente o al anterior. Se siguen los enlaces y las direcciones escritas en el texto; cada salto queda en un historial (Alt+Izquierda, Alt+Derecha). La vista admite dos páginas lado a lado, más zooms, una lupa que vuelve a dibujar la página bajo el puntero (`gui/magnifier.py`), el giro sin tocar el archivo, colores de lectura, márgenes recortados y pantalla completa. Las pestañas pueden verse dos a la vez. Un archivo que otro programa cambia se vuelve a abrir. Las teclas son las de Okular donde hacen lo mismo: F7, F3, /, Ctrl+Mayús+C, Ctrl+Mayús+T, Alt+Mayús+1 a 9, Ctrl+Mayús+P y, en la presentación, B.

### Seguridad, formularios y archivos nuevos

Censurar busca texto solo cubierto (bajo un recuadro, una imagen o una anotación) y quita también las capas apagadas. Archivo > Seguridad > Proteger con contraseñas cifra con AES-256; Firmar digitalmente usa un ID digital (pyHanko), lo crea, puede mostrar una de las firmas a mano y valida. El panel Campos de formulario rellena los campos, con las funciones estándar de formato y cálculo hechas en Python, sin JavaScript, y lleva sus datos dentro y fuera. Archivo combina PDF, hace uno de imágenes, lo compara a la vista con otro PDF, guarda copias más pequeñas o con otra versión de PDF, y exporta páginas, imágenes y texto; Foliar divide también por marcadores y por tamaño; la herramienta Enlace dibuja enlaces.

## Implementación

Está escrito en Python 3.14 o superior, con PyMuPDF, pikepdf, reportlab y PySide6 (Qt 6). Son 158 archivos de Python, unas 43 500 líneas (una décima parte, comentarios), y 3197 textos de la interfaz traducidos al español.

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

Del código de PDFCraft, un editor escrito en Rust, se tomaron cuatro ideas. Hay varios procesos de dibujo por carril, y una página que tarda más de 20 segundos, o hace caer su proceso, se muestra en gris con la causa. Solo se hacen las miniaturas cercanas a las que se ven, después de las páginas a la vista. Con mucho zoom (hasta 10000 %), la página se dibuja entera a 2048 píxeles a lo más, y la parte que se ve, en teselas de 1024 píxeles a escala completa.

### Una sola copia de cada cosa

Los cuatro programas traían copias de lo mismo: abrir un PDF, rectángulos y colores, las palabras bajo el ratón, las matrices de PDF (tres veces), la orden `interface`, los campos comunes de encabezados y marcas de agua, el campo de pdf2iso en tres diálogos de ajustes, un botón y un menú de colores. Se buscaron con pylint y comparando la sintaxis de cada función, y cada una quedó en un solo lugar (`core/pdfdoc.py`, `core/matrix.py`, `stamps.StampSettings`, `gui/conform_field.py`, entre otros).

### OCR

El OCR, el mismo de py-pdfocr, usa el programa tesseract del sistema, en varios procesos a la vez; de cada palabra lee el lugar y la confianza. Tiene su propio modo. El texto se escribe invisible en el documento, como un cambio que se deshace, después de revisar las palabras dudosas junto a su imagen. Las páginas de lado se giran antes, con el modelo osd.

## Validación

Hay 772 pruebas automáticas (`tools/test.py` las corre a la vez, unos 20 s): las de los cuatro programas, trasladadas al paquete nuevo (96 de anotaciones, 71 de censura, 115 de páginas, etiquetas y capas, 87 de imposición), y las de lo nuevo: la línea de órdenes entera y su completado en bash y fish, los modos de la ventana, los recuadros como marcas de redacción, las copias de trabajo con deshacer y rehacer, la navegación (marcadores, enlaces, historial, vistas, pestañas), la seguridad (texto solo cubierto, capas ocultas, contraseñas), las barras de herramientas, la combinación de archivos, los PDF de imágenes, las copias más pequeñas, los enlaces, los formularios, las firmas, los menús y las barras, las exportaciones, la partición y la versión de PDF, la interfaz en español (cada texto traducido y ninguno de sobra) y el empaquetado.

Las pruebas de pdf-word-finder vinieron con él, sobre un documento hecho con PyMuPDF. La ventana se prueba manejándola como lo haría un usuario, con eventos del ratón sobre las páginas, en cada modo. La copia censurada se escribe también en un proceso propio, como lo hace la ventana, y se comprueba que nada de lo que había debajo de los recuadros pueda leerse; la imposición ejecuta sus órdenes en otro proceso. Una prueba comprueba que el manual siga siendo la ayuda de la línea de órdenes.

Otras pruebas abren un documento de 600 páginas y comprueban que lo que se hace a cada paso (ajustar el zoom al cambiar el tamaño de la ventana, hallar la página a la vista al desplazarse) no recorra todas las páginas, y que el atajo dé lo mismo que el cálculo largo; también que el zoom animado deje bajo el puntero lo que estaba bajo él. Los tiempos se midieron antes y después en un documento de 2000 páginas: ajustar el zoom bajó de 300 ms a 7.

El arranque se midió por partes, sin documento, y pasó de unos 330 a 240 ms: el espacio de trabajo de Imponer se construye la primera vez que se entra en el modo, Tesseract se busca en otro hilo mientras se carga lo demás, y Ghostscript solo cuando se abre Guardar como. La nueva lectura de los enlaces, que ya no recorre por cada enlace las anotaciones de su página, se comparó con la anterior en los 21 PDF del equipo, con más de doce mil enlaces: dieron lo mismo, salvo unos pocos con direcciones que PyMuPDF no reconoce, que antes no mostraban nada. En el manual, con 590 enlaces, leer las anotaciones pasó de 55 a 18 ms.

Los nombres de menús y herramientas se cotejaron con los de PDFCraft; unos noventa cambiaron. Las ventanas se revisaron además a ojo, con capturas de cada modo en los dos idiomas, y el manual de usuario se cotejó frase por frase con los menús, las teclas y los diálogos del programa; así apareció un error viejo de los README, que aún decían que el clic derecho sobre una barra cambia solo esa. El RPM vuelve a correr todas las pruebas con los paquetes de Fedora; así apareció el fallo de las etiquetas de PyMuPDF 1.28. El instalador de Linux se probó en una carpeta personal hecha para la prueba.

Las pruebas corren también en GitHub, en Ubuntu y en Windows, contra el programa instalado; en la versión 1.8.3 volvieron a pasar en ambos, tras corregir dos fallos del programa que solo Windows mostraba (los CSV de formularios con renglones vacíos, y proteger con contraseñas un documento abierto). Allí fallaban desde el principio (faltaban qpdf y pdftotext; en Windows, además, no se puede borrar un archivo abierto ni existe `SIGALRM`), y se corrigió: el flujo instala las herramientas, las pruebas que las necesitan se saltan donde no están y las carpetas temporales se borran aunque quede un archivo abierto. En la 1.8.13 todas pasaron y Python se rompió al terminar, en GitHub y en Copr, de modo que esa versión no llegó a Fedora: una prueba metía en una pestaña una ventana mostrada antes como ventana propia, y la pantalla offscreen de las pruebas fallaba al destruirla. Solo ocurría con el programa instalado como lo instalan los instaladores, no con uv.

## Plataforma

Funciona en Linux, y debería funcionar en Windows y macOS, donde lo instalan los instaladores de `install/`; un flujo de trabajo de GitHub los prueba allí. Cada sistema tiene su manera de seguir en segundo plano y de arrancar con la sesión: en Linux, un archivo `.desktop` en la carpeta de arranque automático; en Windows, un valor de la clave Run del registro del usuario, que no muestra ninguna consola al entrar; en macOS, un agente de arranque, con el icono en negro en la barra de menús. Allí los documentos del Finder no llegan como argumentos, sino como eventos al programa que ya corre, y la aplicación que hace el instalador declara que abre PDF. Necesita Python 3.14 o superior, con PyMuPDF, pikepdf, reportlab y PySide6. La AppImage lleva su propio Python con todo eso; el paquete `.deb`, para Debian 12, Ubuntu 22.04 y posteriores, se hace de la AppImage y deja ese Python en `/opt/py-pdftools`, porque esos sistemas no tienen Python 3.14. El RPM es para Fedora. Para PDF/A y PDF/X hace falta Ghostscript (pdf2iso, otro programa del autor, viene incluido); para el OCR, el programa tesseract y los idiomas de los documentos. Las firmas digitales necesitan pyHanko, que se instala aparte (`pip install 'py-pdftools[signatures]'`); la AppImage y los instaladores ya lo traen; el RPM no, porque Fedora no lo empaqueta, pero lo halla si se instala con `pip install --user`, aunque arranque Python con `-s`. Puede dibujar las páginas con la tarjeta gráfica, por OpenGL (Configuración > Rendimiento, desactivado al principio); donde OpenGL no funciona (pantallas remotas, sin servidor X), las dibuja como siempre.

Es una aplicación de escritorio y no necesita internet, salvo para descargar, si se quiere, los modelos más precisos de Tesseract (uno o varios a la vez, de una lista que el usuario marca), para pedir a un servidor un sello de tiempo al firmar, si se le indica uno, y para preguntar a GitHub por la última versión, cuando el usuario lo pide en Ayuda > Buscar actualizaciones; las firmas se comprueban sin conexión. Nada del usuario sale del equipo.

### Accesibilidad

Cada casilla, lista y vista de la ventana tiene un nombre que los lectores de pantalla dicen (`gui/access.py`); las que no recibieron uno propio lo toman de su texto de ejemplo, de su ayuda emergente o de la etiqueta que tienen al lado, y una prueba recorre todos los modos en busca de alguna sin nombre. Ver > Panel siguiente (Ctrl+F6) lleva el teclado de las miniaturas a las páginas y a cada panel visible. Configuración > Apariencia tiene un tema de alto contraste, blanco sobre negro, con lo elegido en amarillo, un borde blanco en cada casilla y uno amarillo en la que tiene el foco.

### Trabajar con muchas páginas

En todos los modos, el menú Buscar reúne las búsquedas, y Herramientas lo que trabaja sobre el documento entero. Configuración tiene Aplicar. El clasificador de páginas muestra todas en una cuadrícula de miniaturas grandes, dibujadas solo cuando se ven; ahí se ordenan arrastrándolas y se giran, duplican o borran, y Aceptar lo hace en un solo paso del historial (`arrange.Sort`).

Aplicar pasos a varios archivos hace, en el orden elegido, algunos de estos pasos en cada archivo de una lista: OCR, encabezado o pie, marca de agua, tamaño reducido, PDF/A. Cada paso es una orden de la línea de órdenes sobre un archivo temporal (`pages/steps.py`); el resultado va a una carpeta, sin escribir sobre otro archivo, y los pasos se guardan como recetas.

El panel Historial describe cada paso de deshacer: un cambio del documento, con el mensaje que su estado guarda; uno de las anotaciones, comparando por identidad la lista anterior con la siguiente. Un clic en un paso deshace o rehace hasta él.

Buscar mientras se escribe (Ctrl+F) baja sobre las páginas y busca con cada letra; se detiene en el primer lugar y cuenta los demás después. Usa un índice propio (`annotate/textindex.py`): cada página se lee una vez y su texto se guarda también sin acentos y en minúsculas.

## Ambiente

Fue desarrollado en Fedora Linux 45 con KDE Plasma, con Python 3.14 y uv, y con git. El código está en repositorios de GitHub (https://github.com/nivaca/py-pdftools) y de Codeberg (https://codeberg.org/nivaca/py-pdftools), públicos. Un script (`tools/release.py`) corre las pruebas, hace la rueda, el paquete fuente, el ZIP, la AppImage, el paquete de Debian (`tools/bundle-deb.py`, que escribe el archivo ar sin las herramientas de Debian) y el RPM firmado, pone la etiqueta, publica en los dos sitios y manda el RPM fuente a Copr (https://copr.fedorainfracloud.org/coprs/nivaca/py-pdftools/), que lo construye para Fedora 45 y Rawhide.

El manual de usuario, en inglés y en español (`docs/MANUAL_en.pdf`, `docs/MANUAL_es.pdf`, hechos con LaTeX a partir de `docs/MANUAL_en.tex` y `docs/MANUAL_es.tex`), explica la instalación, cada modo, el trabajo con archivos enteros, la configuración, la línea de órdenes y las teclas, con 38 imágenes en cada idioma. Las hace `tools/manual_images.py`, que abre documentos de muestra en la ventana, sin pantalla y con una configuración propia, y guarda la ventana y los diálogos; pueden rehacerse cuando la ventana cambie. Cada versión se firma con la clave del autor: el RPM, cada archivo publicado (con su firma `.asc`), las sumas `SHA256SUMS` y la etiqueta; antes de publicar se comprueba cada firma con la clave pública que va con la versión.

En Fedora, `sudo dnf copr enable nivaca/py-pdftools` y `sudo dnf install py-pdftools` lo instalan con su entrada en el menú y su manual. Desde el código fuente, `uv sync` lo prepara; `uv run py-pdftools-gui` abre la ventana y `uv run py-pdftools` es la línea de órdenes, con sus grupos: `labels`, `view`, `header-footer`, `watermark`, `pages`, `impose` (las treinta órdenes de py-imposition), `ocr`, `combine` y `from-images`. En Linux y macOS, `install/install.sh` lo instala para el usuario, con su entrada en el menú; en Windows, `install\install.bat`, que admite también las opciones escritas como en install.sh (`--uninstall`, `--desktop`, `--python`). Configuración tiene páginas para lo general, la apariencia (colores, tamaño, idioma, barras), los documentos (cómo se abren, los recientes), los colores, los atajos, las categorías y el rendimiento; con «Empezar con la sesión», arranca en la bandeja al iniciar la sesión. Las barras de herramientas empiezan en una fila, con iconos pequeños (16 puntos), también la de los modos, y Navegación de páginas entre Navegación y Zoom; la que el usuario mueva o cambie conserva su lugar y sus botones, y la que saque de la ventana se oculta con su pestaña. Queda en la carpeta de configuración del usuario (`~/.config/py-pdftools/config.toml` en Linux, o `$PY_PDFTOOLS_CONFIG`); en macOS, en `~/Library/Application Support/py-pdftools/`, y en Windows, en `%APPDATA%\py-pdftools\`. Es un solo archivo: lo que la ventana guarda de sí misma (su tamaño, la disposición de cada modo, las barras, los documentos recientes) va también allí, en las tablas `[window]` e `[impose]`; antes lo guardaba QSettings aparte, y el primer arranque lo traslada. Fuera de él quedan las recetas de pasos (`recipes.json`), las firmas hechas de una imagen (`signatures/`, sin el papel) y los sellos propios: PNG en la carpeta `stamps`, de una imagen o de una página de un PDF, con su tamaño en `stamps.json` (`annotate/mystamps.py`).

### Las barras de herramientas

Cada modo guarda la disposición de sus barras, con la configuración de Qt. Una barra se arrastra por su asa, más ancha que la que dibuja Fusion; al soltarla, las barras de cada fila vuelven a quedar juntas desde su comienzo, en su orden y sin cambiar de fila, porque Qt conserva el lugar donde se soltó y estira la barra anterior hasta allí. Un espacio vacío, donde se quiera, se pone con «Añadir un espacio» en Personalizar las barras, como en las barras de KDE; el código de estas (KToolBar, KEditToolBar) no tiene enlace para PySide6, así que se tomó de ellas el comportamiento y no la biblioteca.
