# Passermark 1.15.1

Visor de PDF, herramienta de impresiÃ³n y caja de herramientas de preprensa para **Linux y Windows**.
Software libre (GPL-3.0-or-later).

**English:** [README.md](README.md) Â· [Deutsch](README.de.md) Â· [Magyar](README.hu.md) Â· [FranÃ§ais](README.fr.md) Â· **EspaÃ±ol**

> **Estado:** un proyecto privado, desarrollado junto al trabajo diario de preprensa. Los comentarios son
> bienvenidos â las respuestas y las nuevas funciones se ofrecen sin garantÃ­a. Probado con controladores de
> CUPS y de Windows (inyecciÃ³n de tinta, impresoras de oficina y de producciÃ³n con encuadernadora a travÃ©s de
> un servidor de impresiÃ³n); los controladores menos comunes y las opciones de acabado pueden necesitar
> ajustes.

## Capturas de pantalla

| | |
|---|---|
| ![ComprobaciÃ³n del documento con avisos y notas](docs/screenshots/preflight_example.jpg) | ![ConversiÃ³n CMYK con vista previa de color](docs/screenshots/cmyk_adjustment_example.png) |
| ![Step & repeat](docs/screenshots/step_and_repeat_example.png) | ![CutContour para plotter de corte](docs/screenshots/cut_contour_example.png) |
| ![Recorte](docs/screenshots/trim_example.png) | ![Datos variables](docs/screenshots/variable_data_example.png) |

## Funciones

- **Ver e imprimir** PDF, imÃ¡genes (tambiÃ©n HEIC, SVG) y archivos de Office (a travÃ©s de LibreOffice).
  Utiliza los controladores de impresora ya instalados (CUPS en Linux, controladores de Windows) con todas
  sus opciones.
- **ImposiciÃ³n (AusschieÃen):** ajustar/escalar, varias pÃ¡ginas por hoja, pÃ³ster, step & repeat; folletos
  como grapado a cabalga secciones agrupadas u hojas sueltas apiladas (encuadernaciÃ³n encolada), con
  desplazamiento (creep), pÃ¡ginas en blanco, marcas de plegado, de registro y de cotejo y vista general de
  hojas. TambiÃ©n en la lÃ­nea de comandos (`passermark-cli impose`). El step & repeat permite montar la hoja terminada una segunda vez en un formato destino de libre elecciÃ³n (paso 2).
- **ManipulaciÃ³n de documentos:** conversiÃ³n CMYK con vista previa de color, recorte al formato, separar
  objetos, **CutContour** para plotter de corte (contorno, formas, sangrado, cortes interiores; redimensionar
  y mover formas con tiradores). El recorte ahora tambiÃ©n con Â«recortar bordesÂ» (mm por lado, sin formato
  destino) y Â«eliminar el espacio blancoÂ» (detectar el contenido, nuevo marco de pÃ¡gina Â± margen, el
  contenido queda 1:1).
- **Dividir pÃ¡ginas:** mitades o rejilla como pÃ¡ginas separadas â p. ej. un folleto exportado como pÃ¡ginas
  dobles; seleccionar pÃ¡ginas, botÃ³n derecho â Dividir. Sin pÃ©rdida (no se rasteriza nada), se respetan el
  formato final y el sangrado.
- **Preflight:** comprueba fuentes, capas y transparencias al abrir un documento; correcciones: incrustar o
  sustituir fuentes (fuentes libres mÃ©tricamente compatibles o descarga desde fontsource.org), texto a
  curvas, fijar/eliminar capas, aplanar transparencias.
- **EdiciÃ³n:** seleccionar lÃ­neas de texto y capas con el ratÃ³n; cambiar texto, fuente y tamaÃ±o; mover,
  escalar, ocultar, eliminar o sustituir capas; deshacer.
- Reglas y mediciÃ³n: reglas en mm al borde de la vista; clic en inicio y fin para medir (MayÃºs se alinea en
  horizontal/vertical/45Â°), resultado en la barra de estado. Con Control pulsado, la cruceta se imanta a las lÃ­neas de corte e interiores (borde de pÃ¡gina,
  formato final, sangrado), a los bordes de imÃ¡genes y a las lÃ­neas vectoriales â nunca al texto; se pega
  al borde hasta que el ratÃ³n se aleja claramente. La visualizaciÃ³n del formato final lo muestra en verde, con el sangrado en lÃ­nea de puntos.
- **Datos variables:** numeraciÃ³n (inicio, paso, dÃ­gitos, dÃ­gitos de control, hacia atrÃ¡s, contador que
  continÃºa), texto desde CSV, cÃ³digos QR, Code 128 y EAN-13 como vectores (con zona de silencio);
  marcadores `{{â¦}}` en el PDF; fecha, pÃ¡gina, nÃºmero aleatorio y otras variables; varias pÃ¡ginas por
  registro (anverso/reverso) y campos en pÃ¡ginas impares/pares; registro de cÃ³digos; step & repeat con su
  propio registro por copia (hoja por hoja o cortar y apilar). TambiÃ©n en la lÃ­nea de comandos
  **ventanas (grupos de pÃ¡ginas)** para plantillas de varias pÃ¡ginas â p. ej. anverso con el nombre, reverso con un cÃ³digo QR â con selecciÃ³n de pÃ¡ginas por ventana (todas/impares/pares o intervalos) y distribuciÃ³n de registros hoja por hoja o pÃ¡gina por pÃ¡gina (`passermark-cli vdp`).
- **Introducir datos:** crear la tabla de datos directamente en Passermark â tarjeta de visita QR (vCard),
  acceso WLAN, correo electrÃ³nico, direcciÃ³n web, llamada, SMS, cita, ubicaciÃ³n, Code 128, EAN-13 â con las
  columnas adecuadas, comprobaciÃ³n inmediata y pegado desde Excel; guardado como CSV y utilizable
  directamente en los datos variables. Los archivos CSV propios con otros nombres de columna (p. ej.
  exportaciones de contactos de Outlook, Google, Thunderbird) se asignan automÃ¡ticamente. Siete ejemplos
  listos (Ayuda â Obtener ejemplos).
- **Ãreas de trabajo** (Ver e imprimir, Preprensa, Editar, Datos variables, AutomatizaciÃ³n) con su propia
  barra de herramientas.
- **Preajustes** para CutContour, CMYK/recorte, diseÃ±o de impresiÃ³n y datos variables â compartidos con la
  lÃ­nea de comandos.
- Reparar/optimizar PDF, PDF/A, protecciÃ³n con contraseÃ±a (tambiÃ©n al Â«Guardar como PDFÂ» en el diÃ¡logo de
  impresiÃ³n), fusionar archivos, seleccionar y copiar texto.
- Idiomas: espaÃ±ol, alemÃ¡n, inglÃ©s, hÃºngaro, francÃ©s.

## InstalaciÃ³n

**Windows:** descargar `Passermark-<versiÃ³n>-Setup.exe` desde [Releases](../../releases) y ejecutarlo. Todo
estÃ¡ incluido (Python, Qt, Ghostscript).

**Linux (cualquier distribuciÃ³n):** descargar `Passermark-<versiÃ³n>-x86_64.AppImage` desde
[Releases](../../releases), luego
```sh
chmod +x Passermark-*-x86_64.AppImage
./Passermark-*-x86_64.AppImage
```

**Linux (Debian/Ubuntu, instalaciÃ³n en el sistema con integraciÃ³n en el gestor de archivos):**
```sh
sudo ./install.sh        # instala dependencias vÃ­a apt, entrada de menÃº, menÃº de Nautilus
sudo ./uninstall.sh      # eliminar de nuevo (--dry-run muestra una vista previa, --purge tambiÃ©n elimina /etc/passermark)
```

Opcional: LibreOffice (archivos de Office), 7-Zip (importar perfiles ICC desde archivos).

## LÃ­nea de comandos

Todas las funciones pesadas funcionan tambiÃ©n sin interfaz â para scripts, carpetas enteras y automatizaciÃ³n:

```sh
passermark-cli list                                   # tareas disponibles
passermark-cli settings cutcontour > pegatina.json     # valores predeterminados = plantilla de preajuste
passermark-cli cutcontour entrada.pdf salida.pdf --set shape=rect --set bleed_mm=2
passermark-cli cutcontour entrada.pdf salida.pdf --preset pegatina.json --pages 1,3-5
passermark-cli cutcontour entrada.pdf salida.pdf --preset "Sticker rund"   # preajuste guardado en el programa
passermark-cli presets                                # preajustes guardados en el programa
```

Tareas: `cutcontour`, `separate`, `manip` (CMYK/recorte), `repair`, `preflight_fix`, `impose`, `vdp`,
`split`; ademÃ¡s `beispiele`, `datenarten`, `datenvorlage`, `datencheck` (tablas de datos). Ajustes
anidados con punto (`--set detect.tolerance=40`). Ctrl+C interrumpe limpiamente (ningÃºn archivo a medias).
CÃ³digos de retorno: 0 terminado, 1 error, 2 indicaciÃ³n incorrecta, 130 cancelado. `--json-progress` imprime
el progreso y el resultado como lÃ­neas JSON. Las tareas grandes usan varios nÃºcleos; limitar con la variable
de entorno `PASSERMARK_WORKERS` (1 = sin paralelismo).

DÃ³nde: Linux `install.sh` â `passermark-cli`; AppImage â `Passermark-*.AppImage --cli â¦`;
Windows â `passermark-cli.exe` en la carpeta de instalaciÃ³n (opciÃ³n de instalaciÃ³n: aÃ±adirlo al PATH).
GuÃ­as con ejemplos en el programa: **Ayuda â LÃ­nea de comandos â guÃ­a** y
**Ayuda â Datos variables â guÃ­a**.
Interfaz para programas externos (eventos JSON estables, cÃ³digos de error): [docs/cli-api.md](docs/cli-api.md).

## Registros de errores

Si algo falla, Passermark escribe un archivo de registro para adjuntar (Ayuda â Abrir registros de errores):
Linux `~/.local/state/passermark/logs`, Windows `%LOCALAPPDATA%\Passermark\logs`. Tras un fallo, el siguiente
inicio seÃ±ala el registro. Los registros sin errores se eliminan al salir.

## CompilaciÃ³n

Localmente: `powershell -ExecutionPolicy Bypass -File windows\build.ps1` (Windows, necesita Python 3.12 e
Inno Setup 6) o `./linux/build-appimage.sh` (Linux, los paquetes necesarios en la cabecera del script).

Pruebas: `python3 tests/test_<nombre>.py` (no se necesita framework de pruebas).

## Licencia

GPL-3.0-or-later, vÃ©ase `LICENSE`. El instalador de Windows y el AppImage contienen
[Ghostscript](https://ghostscript.com) (AGPL-3.0, Artifex Software).

Licencias de terceros: el instalador y el AppImage incluyen junto al programa una carpeta
`licenses` (Ayuda â Licencias â¦) con `THIRD_PARTY_NOTICES.txt`, los archivos de licencia de todos
los paquetes de Python incluidos, el aviso LGPL de Qt/PySide6 (cÃ³mo sustituir las bibliotecas de Qt)
y el aviso de Ghostscript con los enlaces al cÃ³digo fuente de la versiÃ³n incluida. Previa solicitud
tambiÃ©n se facilita el cÃ³digo fuente correspondiente de los componentes incluidos: abra un issue en
[GitHub](https://github.com/groschenheld/passermark/issues).

