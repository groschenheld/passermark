# Passermark 1.10.8

Visor de PDF, herramienta de impresión y caja de herramientas de preprensa para **Linux y Windows**.
Software libre (GPL-3.0-or-later).

**English:** [README.md](README.md) · [Deutsch](README.de.md) · [Magyar](README.hu.md) · [Français](README.fr.md) · **Español**

> **Estado:** un proyecto privado, desarrollado junto al trabajo diario de preprensa. Los comentarios son
> bienvenidos – las respuestas y las nuevas funciones se ofrecen sin garantía. Probado con controladores de
> CUPS y de Windows (inyección de tinta, impresoras de oficina y de producción con encuadernadora a través de
> un servidor de impresión); los controladores menos comunes y las opciones de acabado pueden necesitar
> ajustes.

## Funciones

- **Ver e imprimir** PDF, imágenes (también HEIC, SVG) y archivos de Office (a través de LibreOffice).
  Utiliza los controladores de impresora ya instalados (CUPS en Linux, controladores de Windows) con todas
  sus opciones.
- **Imposición (Ausschießen):** ajustar/escalar, varias páginas por hoja, póster, step & repeat; folletos
  como grapado a cabalga secciones agrupadas u hojas sueltas apiladas (encuadernación encolada), con
  desplazamiento (creep), páginas en blanco, marcas de plegado, de registro y de cotejo y vista general de
  hojas. También en la línea de comandos (`passermark-cli impose`).
- **Manipulación de documentos:** conversión CMYK con vista previa de color, recorte al formato, separar
  objetos, **CutContour** para plotter de corte (contorno, formas, sangrado, cortes interiores; redimensionar
  y mover formas con tiradores).
- **Dividir páginas:** mitades o rejilla como páginas separadas – p. ej. un folleto exportado como páginas
  dobles; seleccionar páginas, botón derecho → Dividir. Sin pérdida (no se rasteriza nada), se respetan el
  formato final y el sangrado.
- **Preflight:** comprueba fuentes, capas y transparencias al abrir un documento; correcciones: incrustar o
  sustituir fuentes (fuentes libres métricamente compatibles o descarga desde fontsource.org), texto a
  curvas, fijar/eliminar capas, aplanar transparencias.
- **Edición:** seleccionar líneas de texto y capas con el ratón; cambiar texto, fuente y tamaño; mover,
  escalar, ocultar, eliminar o sustituir capas; deshacer.
- Reglas y medición: reglas en mm al borde de la vista; clic en inicio y fin para medir (Mayús se alinea en
  horizontal/vertical/45°), resultado en la barra de estado.
- **Datos variables:** numeración (inicio, paso, dígitos, dígitos de control, hacia atrás, contador que
  continúa), texto desde CSV, códigos QR, Code 128 y EAN-13 como vectores (con zona de silencio);
  marcadores `{{…}}` en el PDF; fecha, página, número aleatorio y otras variables; varias páginas por
  registro (anverso/reverso) y campos en páginas impares/pares; registro de códigos; step & repeat con su
  propio registro por copia (hoja por hoja o cortar y apilar). También en la línea de comandos
  (`passermark-cli vdp`).
- **Introducir datos:** crear la tabla de datos directamente en Passermark – tarjeta de visita QR (vCard),
  acceso WLAN, correo electrónico, dirección web, llamada, SMS, cita, ubicación, Code 128, EAN-13 – con las
  columnas adecuadas, comprobación inmediata y pegado desde Excel; guardado como CSV y utilizable
  directamente en los datos variables. Los archivos CSV propios con otros nombres de columna (p. ej.
  exportaciones de contactos de Outlook, Google, Thunderbird) se asignan automáticamente. Siete ejemplos
  listos (Ayuda → Obtener ejemplos).
- **Áreas de trabajo** (Ver e imprimir, Preprensa, Editar, Datos variables, Automatización) con su propia
  barra de herramientas.
- **Preajustes** para CutContour, CMYK/recorte, diseño de impresión y datos variables – compartidos con la
  línea de comandos.
- Reparar/optimizar PDF, PDF/A, protección con contraseña (también al «Guardar como PDF» en el diálogo de
  impresión), fusionar archivos, seleccionar y copiar texto.
- Idiomas: español, alemán, inglés, húngaro, francés.

## Instalación

**Windows:** descargar `Passermark-<versión>-Setup.exe` desde [Releases](../../releases) y ejecutarlo. Todo
está incluido (Python, Qt, Ghostscript).

**Linux (cualquier distribución):** descargar `Passermark-<versión>-x86_64.AppImage` desde
[Releases](../../releases), luego
```sh
chmod +x Passermark-*-x86_64.AppImage
./Passermark-*-x86_64.AppImage
```

**Linux (Debian/Ubuntu, instalación en el sistema con integración en el gestor de archivos):**
```sh
sudo ./install.sh        # instala dependencias vía apt, entrada de menú, menú de Nautilus
sudo ./uninstall.sh      # eliminar de nuevo (--dry-run muestra una vista previa, --purge también elimina /etc/passermark)
```

Opcional: LibreOffice (archivos de Office), 7-Zip (importar perfiles ICC desde archivos).

## Línea de comandos

Todas las funciones pesadas funcionan también sin interfaz – para scripts, carpetas enteras y automatización:

```sh
passermark-cli list                                   # tareas disponibles
passermark-cli settings cutcontour > pegatina.json     # valores predeterminados = plantilla de preajuste
passermark-cli cutcontour entrada.pdf salida.pdf --set shape=rect --set bleed_mm=2
passermark-cli cutcontour entrada.pdf salida.pdf --preset pegatina.json --pages 1,3-5
passermark-cli cutcontour entrada.pdf salida.pdf --preset "Sticker rund"   # preajuste guardado en el programa
passermark-cli presets                                # preajustes guardados en el programa
```

Tareas: `cutcontour`, `separate`, `manip` (CMYK/recorte), `repair`, `preflight_fix`, `impose`, `vdp`,
`split`; además `beispiele`, `datenarten`, `datenvorlage`, `datencheck` (tablas de datos). Ajustes
anidados con punto (`--set detect.tolerance=40`). Ctrl+C interrumpe limpiamente (ningún archivo a medias).
Códigos de retorno: 0 terminado, 1 error, 2 indicación incorrecta, 130 cancelado. `--json-progress` imprime
el progreso y el resultado como líneas JSON. Las tareas grandes usan varios núcleos; limitar con la variable
de entorno `PASSERMARK_WORKERS` (1 = sin paralelismo).

Dónde: Linux `install.sh` → `passermark-cli`; AppImage → `Passermark-*.AppImage --cli …`;
Windows → `passermark-cli.exe` en la carpeta de instalación (opción de instalación: añadirlo al PATH).
Guías con ejemplos en el programa: **Ayuda → Línea de comandos – guía** y
**Ayuda → Datos variables – guía**.

## Registros de errores

Si algo falla, Passermark escribe un archivo de registro para adjuntar (Ayuda → Abrir registros de errores):
Linux `~/.local/state/passermark/logs`, Windows `%LOCALAPPDATA%\Passermark\logs`. Tras un fallo, el siguiente
inicio señala el registro. Los registros sin errores se eliminan al salir.

## Compilación

Cada push a `main` compila en GitHub el instalador de Windows y el AppImage de Linux (**Actions**); ambos se
comprueban con `--selftest`. Una etiqueta `v*` (p. ej. `git tag v1.10.8 && git push origin v1.10.8`) los
adjunta a una Release de GitHub.

Localmente: `powershell -ExecutionPolicy Bypass -File windows\build.ps1` (Windows, necesita Python 3.12 e
Inno Setup 6) o `./linux/build-appimage.sh` (Linux, los paquetes necesarios en la cabecera del script).

Pruebas: `python3 tests/test_<nombre>.py` (no se necesita framework de pruebas).

## Licencia

GPL-3.0-or-later, véase `LICENSE`. El instalador de Windows y el AppImage contienen
[Ghostscript](https://ghostscript.com) (AGPL-3.0, Artifex Software).
