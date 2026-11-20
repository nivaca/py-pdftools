py-pdftools
===========

*(English: [README.md](README.md))*

py-pdftools edita documentos PDF. Los anota, los censura, cambia sus
etiquetas de página, sus encabezados, pies de página y marcas de agua y el
orden de sus páginas, y los impone para imprenta. Reúne, en una sola
ventana y una sola línea de órdenes, lo que hacían por separado cuatro
programas anteriores míos:

* [py-annotate](https://github.com/nivaca/py-annotate): resaltados, notas,
  cuadros de texto, formas, dibujos y sellos, escritos como anotaciones PDF
  corrientes;
* [py-redact](https://github.com/nivaca/py-redact): recuadros sobre lo que
  debe quitarse, y una copia censurada en la que se elimina para siempre, y
  se comprueba;
* [py-foliation](https://github.com/nivaca/py-foliation): etiquetas de
  página (números romanos, folios, prefijos), encabezados y pies con números
  Bates, marcas de agua, la vista al abrir el documento y el orden de las
  páginas;
* [py-imposition](https://github.com/nivaca/py-imposition): folletos, n-up,
  paso y repetición, sangrados y marcas de corte, secuencias y carpetas
  vigiladas.

La ventana y la línea de órdenes están en español y en inglés. Funciona en
Linux, y sus instaladores lo instalan también en Windows y macOS. Esta es la
versión 0.1.0.

Soy Nicolas Vaughan (<nicolasvaughan@proton.me>) y lo escribí en 2026. Es
software libre, bajo la Licencia Pública General de GNU, versión 3 o
posterior (véase «Licencia»).

Capturas de pantalla
--------------------

El modo Anotar:

![Anotar](docs/img/annotate_es.png)

El modo Censurar: un recuadro sobre un renglón, que va en todas las páginas
desde la segunda:

![Censurar](docs/img/redact_es.png)

El modo Foliar: la portada sin etiqueta, luego 1, 2, 3, y la etiqueta en
el pie de página:

![Páginas](docs/img/pages_es.png)

El modo Imponer: un folleto:

![Imponer](docs/img/impose_es.png)

De dónde viene
--------------

py-pdftools nació de cuatro programas que escribí antes, cada uno para un
tipo de trabajo con documentos PDF. Tras un tiempo de crecer uno al lado
del otro, era claro que compartían mucho (la manera de traducir la
interfaz, la configuración, el paso a PDF/A y PDF/X, el empaquetado) y que
un mismo documento solía pasar por más de uno: se anotaba, luego se
censuraba, luego recibía sus etiquetas de página y por último se imponía
para imprenta. Así que los reuní. Su código se copió en py-pdftools, no se
usa desde ellos: py-pdftools no necesita que estén instalados, y ellos
quedan como estaban, cada uno con su repositorio y sus versiones.

    py-annotate 1.1.0      el modo Anotar; la ventana misma (sus páginas,
                           miniaturas y paneles) es la de py-annotate
    py-redact 1.0.9        el modo Censurar
    py-foliation 1.0.1     el modo Foliar, y las órdenes labels, view,
                           header-footer, watermark y pages
    py-imposition 0.10.3   el modo Imponer, y las órdenes de impose

Lo que cambió al reunirlos:

* Una sola ventana, con una barra de modos, en lugar de cuatro; y un solo
  historial, de modo que Deshacer recorre todo lo que se hizo al documento.
* Los recuadros de py-redact son ahora las marcas de redacción del propio
  PDF: se guardan en el documento, sin aplicar, hasta que se escribe la
  copia censurada.
* Los cambios del modo Foliar se hacen en el acto, y se ven, en lugar de
  esperar, como en py-foliation, a que se guarde el archivo.
* Una sola línea de órdenes, con grupos: las etiquetas de py-foliation están
  en `labels`, y todas las órdenes de py-imposition en `impose`.
* Una sola carpeta de configuración. La configuración de los programas
  anteriores no se lee; los códigos de censura de py-redact (`codes.xml`) y
  los perfiles de encabezados, pies y marcas de agua de py-foliation
  (`header-footer.json`, `watermark.json`) pueden copiarse de sus carpetas
  a la de py-pdftools (véase «Configuración»).

Un quinto programa mío entró entero: [pdf2iso](https://github.com/nivaca/pdf2iso),
que hace las copias como PDF/A y PDF/X. Ya no es un programa que haya que
instalar aparte: la ventana, las órdenes con `--conform` y `py-pdftools
pdf2iso`, que es la línea de órdenes del propio pdf2iso, usan el que trae
py-pdftools. Solo hace falta tener instalado Ghostscript, que hace la
conversión. En la configuración todavía puede indicarse otro pdf2iso.

Los documentos que hicieron los programas anteriores se leen como antes:
las claves que escribían en un PDF (etiquetas y categorías de las
anotaciones, capas de encabezados, pies y marcas de agua, la historia de una
imposición) conservan su nombre, y los archivos JSON de anotaciones que
exporta py-annotate pueden importarse. Cómo se reunieron los cuatro, y qué
apareció por el camino, está en [docs/DESCRIPCIÓN_es.md](docs/DESCRIPCIÓN_es.md).

Instalación
-----------

Cada versión está en las [publicaciones](https://github.com/nivaca/py-pdftools/releases),
en GitHub y en [Codeberg](https://codeberg.org/nivaca/py-pdftools/releases),
con estos archivos:

    py-pdftools-VERSIÓN.zip                 el código, con los instaladores
    py-pdftools-VERSIÓN-x86_64.AppImage     la AppImage (Linux)
    py-pdftools-VERSIÓN-1.fc45.noarch.rpm   el paquete de Fedora, firmado
    RPM-GPG-KEY-py-pdftools                 la clave que lo firma
    py_pdftools-VERSIÓN.tar.gz              el paquete fuente, para Python
    py_pdftools-VERSIÓN-py3-none-any.whl    la rueda, para Python

**Fedora.** Desde [Copr](https://copr.fedorainfracloud.org/coprs/nivaca/py-pdftools/),
para Fedora 45 y posteriores, con el Python, el PyMuPDF, el pikepdf, el
reportlab y el PySide6 de Fedora, una entrada en el menú y el manual
(`man py-pdftools`):

    $ sudo dnf copr enable nivaca/py-pdftools
    $ sudo dnf install py-pdftools

Las actualizaciones llegan luego con `sudo dnf upgrade`. El RPM de cada
versión también puede instalarse a mano, después de importar su clave:
`sudo rpm --import RPM-GPG-KEY-py-pdftools`.

**AppImage (cualquier Linux).** No necesita nada más: lleva su propio
Python, Qt y bibliotecas, y funciona con glibc 2.34 o posterior (Ubuntu
22.04, Debian 12, Fedora 35 y posteriores). Se la hace ejecutable y se la
abre:

    $ chmod +x py-pdftools-*-x86_64.AppImage
    $ ./py-pdftools-*-x86_64.AppImage [archivo.pdf]               la ventana
    $ ./py-pdftools-*-x86_64.AppImage impose booklet libro.pdf    una orden

**Con los instaladores (Linux, macOS, Windows).** Necesitan Python 3.14 o
posterior. Desde la carpeta del código:

    $ install/install.sh                Linux y macOS: instalar, o actualizar
    $ install/install.sh --uninstall
    > install\install.bat               Windows: instalar, o actualizar
    > install\install.bat -Desktop      también un acceso en el escritorio
    > install\install.bat -Uninstall

Cada uno hace un entorno de Python propio para py-pdftools, lo instala en él
con PyMuPDF, pikepdf, reportlab y PySide6 (descargados de PyPI, así que la
primera vez necesita internet), enlaza las órdenes `py-pdftools` y
`py-pdftools-gui` y añade la ventana al menú del sistema. Nada necesita
permisos de administrador, y la configuración nunca se toca.

**Desde el código**, con [uv](https://docs.astral.sh/uv/):

    $ git clone https://github.com/nivaca/py-pdftools.git
    $ cd py-pdftools
    $ uv run py-pdftools-gui [archivo.pdf]    la ventana
    $ uv run py-pdftools --help               la línea de órdenes

Las copias como PDF/A o PDF/X necesitan Ghostscript, que las hace (pdf2iso,
que las prepara y las comprueba, es parte de py-pdftools: véase «De dónde
viene»). Para las copias con texto buscable de páginas escaneadas,
Tesseract.

La ventana
----------

Un documento se abre con Archivo > Abrir, o soltándolo sobre la ventana. Sus
páginas se ven una debajo de otra, con sus miniaturas a la izquierda. La
barra de modos, arriba (o Ctrl+1 a Ctrl+5), elige qué hace la ventana, y
cómo se dispone:

* **Leer**: solo las páginas y sus miniaturas, con las barras para abrir,
  buscar, recorrer las páginas y cambiar el tamaño; el ratón mueve las
  páginas;
* **Censurar**: la herramienta Censurar (arrastrar sobre un texto lo marca;
  en otra parte, o con Ctrl, dibuja un recuadro), Buscar y censurar, los
  códigos de censura y el panel de los recuadros;
* **Anotar**: las herramientas de py-annotate, en la segunda barra y en el
  menú Herramientas; el panel de las anotaciones a la derecha, que se puede
  buscar, filtrar y ordenar;
* **Foliar**: los intervalos de etiquetas y la lista de las páginas con sus
  etiquetas, a la derecha; las acciones sobre las páginas elegidas, en la
  barra y en su menú del botón derecho; los encabezados y pies, las marcas
  de agua y la vista al abrir el documento, en el menú Páginas;
* **Imponer**: el espacio de trabajo de py-imposition, con su formulario
  básico, los formularios de cada orden, la secuencia y el registro, en
  lugar de las páginas.

Cada modo guarda su propia disposición de la ventana: qué barras y paneles
se ven, dónde están, las miniaturas y el ancho de las páginas a su lado.
Basta con disponer un modo una vez (arrastrar sus barras y paneles,
ocultarlos con el botón derecho sobre ellos) para que, al elegirlo de
nuevo, vuelva así, también la próxima vez que se abra el programa.

Al elegir un modo, un consejo sobre lo que se puede hacer en él aparece
unos segundos sobre la parte de abajo de las páginas; Ayuda > Consejos de
este modo (F1) lo muestra otra vez.

Cada modo trabaja sobre sus propias anotaciones: en Anotar, los recuadros de
censura se ven, pero el ratón los atraviesa, y en Censurar, las anotaciones.
Deshacer recorre todo lo que se hizo al documento, en cualquier modo.

**Guardar.** Archivo > Guardar escribe el documento: sus anotaciones, sus
recuadros de censura (como marcas de redacción del PDF, todavía sin
aplicar) y los cambios de los modos Foliar e Imponer. Esos cambios se
hacen en el acto sobre una copia de trabajo, y se ven, pero el archivo
queda como estaba hasta que se guarda.

**Censurar.** Nada de lo que hay debajo de los recuadros se elimina hasta
que se escribe la copia censurada, con Censurar > Guardar la copia
censurada (Ctrl+Mayús+R): un archivo nuevo, nunca el que está abierto, en el
que lo que hay debajo de los recuadros desaparece para siempre. Se
comprueba al escribirlo: si algún texto debajo de un recuadro todavía puede
leerse, o un marcador lo delata, la ventana lo dice. La copia se hace a
partir del documento tal como se guardó por última vez, así que la ventana
ofrece guardar antes los otros cambios. Las copias que vuelven las
anotaciones parte de las páginas (aplanadas, buscables, impresas) dejan
fuera los recuadros, porque un recuadro pintado ahí taparía lo que sigue en
el archivo.

**Imponer.** El modo Imponer impone el documento tal como está en la
ventana. Vista previa ejecuta la orden y muestra el resultado; Guardar lo
escribe como un archivo nuevo; Aplicar convierte el resultado en el
documento (Deshacer lo revierte).

La línea de órdenes
-------------------

    $ py-pdftools labels set libro.pdf 1:r 9:D -i     i, ii ... desde la página 1; 1, 2 ... desde la 9
    $ py-pdftools labels libro.pdf                     las etiquetas de un archivo
    $ py-pdftools header-footer libro.pdf --footer-center 'Página $pagelabel' -i
    $ py-pdftools watermark libro.pdf --text BORRADOR --opacity 30% -i
    $ py-pdftools pages libro.pdf --move 201-214 9 --delete LAST -i
    $ py-pdftools view libro.pdf --layout cover --open-at 9 -i
    $ py-pdftools impose booklet libro.pdf -o folleto.pdf
    $ py-pdftools impose --help                        las órdenes de la imposición

`py-pdftools ORDEN -h` explica cada orden. `py-pdftools completion
bash|fish|zsh` imprime el script de completado del shell. Las órdenes son
las de py-foliation y py-imposition, que sus README explican con detalle;
`labels` reúne `show`, `set`, `clear` y `copy` de py-foliation.

Configuración
-------------

El idioma de la interfaz se elige en Configuración > Idioma, o con
`py-pdftools interface es`. La configuración se guarda en un archivo,
`config.toml`, en la carpeta de configuración del usuario:
`~/.config/py-pdftools/` en Linux, `~/Library/Application Support/py-pdftools/`
en macOS y `%APPDATA%\py-pdftools\` en Windows (o la carpeta que diga
`$PY_PDFTOOLS_CONFIG`). Cada ajuste se comprueba al leerlo, de modo que un
archivo editado a mano no puede detener el programa.

Pruebas
-------

    $ uv run pytest

Hay 417 pruebas: las de los cuatro programas, y las de lo nuevo (la línea de
órdenes entera, los modos de la ventana, los recuadros de censura, las
copias de trabajo, la interfaz en español, el empaquetado). Cómo se hizo el
programa está en [docs/DESCRIPCIÓN_es.md](docs/DESCRIPCIÓN_es.md).

Licencia
--------

py-pdftools es software libre: puede redistribuirlo o modificarlo según los
términos de la Licencia Pública General de GNU publicada por la Free
Software Foundation, versión 3 o (a su elección) cualquier versión
posterior (véase [LICENSE](LICENSE)). Usa PyMuPDF (GNU AGPL 3), pikepdf
(Mozilla Public License 2.0), reportlab (BSD) y PySide6 (GNU LGPL 3).
