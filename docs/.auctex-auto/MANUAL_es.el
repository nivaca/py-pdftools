;; -*- lexical-binding: t; -*-

(TeX-add-style-hook
 "MANUAL_es"
 (lambda ()
   (TeX-add-to-alist 'LaTeX-provided-class-options
                     '(("memoir" "12pt" "article" "oneside")))
   (TeX-add-to-alist 'LaTeX-provided-package-options
                     '(("iftex" "") ("fontspec" "") ("babel" "english" "" "spanish" "es-minimal" "es-noshorthands" "es-tabla") ("fontenc" "T1") ("libertinus" "osf") ("FiraMono" "scaled=0.9") ("microtype" "babel=true" "verbose=false" "tracking=true" "expansion=true" "protrusion=true" "final" "draft=false") ("csquotes" "autostyle=false" "style=british") ("latexcolors" "") ("graphicx" "") ("booktabs" "") ("enumitem" "") ("hyperref" "") ("bookmark" "")))
   (add-to-list 'LaTeX-verbatim-environments-local "verbatimtab")
   (add-to-list 'LaTeX-verbatim-environments-local "verbatimwrite")
   (add-to-list 'LaTeX-verbatim-environments-local "boxedverbatim")
   (add-to-list 'LaTeX-verbatim-environments-local "listing")
   (add-to-list 'LaTeX-verbatim-environments-local "listing*")
   (add-to-list 'LaTeX-verbatim-environments-local "listingcont")
   (add-to-list 'LaTeX-verbatim-environments-local "listingcont*")
   (add-to-list 'LaTeX-verbatim-macros-with-braces-local "path")
   (add-to-list 'LaTeX-verbatim-macros-with-braces-local "url")
   (add-to-list 'LaTeX-verbatim-macros-with-braces-local "nolinkurl")
   (add-to-list 'LaTeX-verbatim-macros-with-braces-local "hyperbaseurl")
   (add-to-list 'LaTeX-verbatim-macros-with-braces-local "hyperimage")
   (add-to-list 'LaTeX-verbatim-macros-with-braces-local "href")
   (add-to-list 'LaTeX-verbatim-macros-with-delims-local "path")
   (TeX-run-style-hooks
    "latex2e"
    "g"
    "memoir"
    "memoir12"
    "iftex"
    "fontspec"
    "babel"
    "fontenc"
    "libertinus"
    "FiraMono"
    "microtype"
    "csquotes"
    "latexcolors"
    "graphicx"
    "booktabs"
    "enumitem"
    "hyperref"
    "bookmark")
   (TeX-add-symbols
    '("naranja" 1)
    '("morado" 1)
    '("amarillo" 1)
    '("verde" 1)
    '("azul" 1)
    '("rojoit" 1)
    '("rojo" 1)
    "version"
    "Rojo"
    "Azul"
    "Verde"
    "Amarillo"
    "Morado"
    "Naranja"
    "elipsis"
    "elipsisb"))
 :latex)

