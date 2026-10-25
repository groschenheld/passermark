# Registro de cambios – Passermark

**English:** [CHANGELOG.md](CHANGELOG.md) · [Deutsch](CHANGELOG.de.md) · [Magyar](CHANGELOG.hu.md) · [Français](CHANGELOG.fr.md) · **Español**

> Este registro contiene las versiones desde **1.10.0** en español. El historial completo:
> [CHANGELOG.md](CHANGELOG.md) (inglés) o [CHANGELOG.de.md](CHANGELOG.de.md) (alemán).

## 1.18.2

### Preflight: cajas de página, sangrado, protección, PDF/X, campos de formulario
- **Cajas de página:** `UserUnit ≠ 1` es un error; una CropBox más pequeña que la MediaBox o fuera de ella también (el caso ColorWave); una TrimBox fuera de la zona visible o más grande que la BleedBox; páginas giradas y formatos mixtos como aviso.
- **Sangrado:** si el contenido llega hasta el borde del formato final pero la página tiene menos de 2 mm de sangrado, se notifica. La comprobación se hace sobre una vista previa aproximada – los planos sin sangrado quedan limpios; solo avisa si el contenido llega de verdad al borde.
- **Protección:** «impresión no permitida» es un error; solo la baja resolución es un aviso.
- **PDF/X:** el archivo se presenta como PDF/X pero no tiene output intent para ello; un output intent sin perfil incrustado; páginas sin TrimBox.
- **Campos de formulario:** la comprobación dice cuántos no se imprimen. Passermark imprime de todos modos los valores del formulario en su propia impresión – el aviso solo aparece si un campo de verdad no se imprime; la nota sobre NeedAppearances vale para la entrega y las carpetas vigiladas.
- **Páginas vacías** se notifican.
- Los formatos mixtos son solo un aviso, no una advertencia – en juegos de planos son normales los formatos distintos.
- El informe de comprobación ahora lista las cajas de página y el sangrado de la primera página.
- **Para los flujos** hay dos nuevos valores de comprobación: `blank_pages` y `print_allowed`.

### Línea de comandos: plan
- `passermark-cli plan` admite ahora `--roll` (alimentación, nombre en el aparato o ancho, p. ej. `--roll 914`), `--align center|left|right` y `--no-split`.

### Manual
- El manual (docs/cli-api.md) está ampliado en alemán e inglés: impresión de planos y pósters (rollo fijo, material por nombre, posición en el rollo, un trabajo por ejemplar, valores predeterminados de póster), una nueva sección sobre la comprobación y dos ejemplos.

## 1.18.1

### Mensaje al leer los rollos
- El mensaje ahora está en su propia línea bajo la barra de impresora – ya no entre la selección de impresora y los botones.
- Crece como máximo hasta 3 líneas, lo que sobra se desplaza; seleccionar texto y copiarlo con Ctrl+C funciona.
- El mensaje de la ventana «Rollos …» (hasta 5 líneas, también el resultado de «comprobar aparato») y los avisos bajo «metros lineales por rollo» (hasta 4 líneas) funcionan ahora igual.

### Responsive
- Los nombres largos de rollos, materiales e impresoras ya no ensanchan las listas: se acortan, y desplegado se ve el texto completo.
- Con poco espacio, un campo de los ajustes se coloca bajo su etiqueta en lugar de solaparse con su vecino.
- La columna derecha con los metros lineales y los ajustes se desplaza; la línea de separación entre la lista de planos y los ajustes se puede mover, ningún lado se cierra del todo.
- La ventana se puede reducir hasta 640 × 420.

## 1.18.0

### Espacio de trabajo «Plan & Poster»
- Un nuevo espacio de trabajo para la impresión de planos y pósters – también como paso de un flujo y vía `passermark-cli plan` y `passermark-cli poster`. Con `--dry-run` solo se calculan los metros lineales.

### Rollos leídos del aparato
- Por IPP, si no por SNMP; SNMP prueba v2c y cae a v1. Las alimentaciones de tipo «other» con ancho cuentan como rollo; la comunidad se ajusta por aparato.
- Los Roland se consultan aparte; si no, se introducen los rollos a mano.
- En Windows, la dirección del aparato sale de la conexión (puerto IP, TCP/IP o WSD) o se introduce a mano.
- «Comprobar aparato» (probe) consulta puertos, IPP y SNMP y guarda todo como informe JSON. Solo lee, no imprime nada.

### Zona de impresión
- Con dos líneas exteriores se recorta a la exterior; si no, el contenido recibe un margen de 5 mm – modificable por plano.

### Elección del rollo
- Automática: el rollo más estrecho que encaje, elegido por el gramaje del papel del plano o el material – los materiales ahora también por el nombre.
- Fija: cada rollo leído se puede elegir, incluso sin material registrado.
- El tipo de soporte del rollo se pasa al controlador.
- Posición en el rollo: centrado o en el borde (izquierda o derecha); la página impresa siempre es tan ancha como el rollo. En planos, «en el borde» es lo predeterminado; en pósters, «centrado».

### Ejemplares y metros lineales
- Ordenados o sin ordenar, según la lista o el ancho del rollo. «Cortar individualmente» es lo predeterminado: cada ejemplar es un trabajo propio (1/3, 2/3 …).
- Metros lineales en vivo por rollo, aviso cuando el largo restante no alcanza – y quedan en el registro de impresión.

### Herramientas de planos
- Escalado, rotación, bandas de relleno (espejadas, vacías o de un solo color), marcas de corte, elevar las líneas finas, marcas de plegado según DIN 824.

### Herramientas de pósters
- En paralelo sobre el rollo es opcional y ahora está desactivado por defecto.
- Lo más ancho que el rollo se recorta o se divide en bandas con solape.
- Dobladillo, marcas de ojetes, CutContour y marcas de registro para print & cut con la Roland.

### Materiales para Plan & Poster
- Impresión de planos o impresión de calidad; por material gramaje, tipo de soporte, calidad, cantidad de tinta y perfil. Guardados por usuario, con valores predeterminados del administrador.

### Otros
- Salida a carpeta vigilada, p. ej. para VersaWorks.
- Mensajes de error más claros cuando no se encuentra el aparato.

## 1.17.1

### Fusionar con clic derecho (Windows)
- El Explorador inicia un proceso Passermark por cada archivo seleccionado (MultiSelectModel=Player). Sin una instancia en marcha, varios de ellos se convertían a la vez en servidores, porque en Windows `listen()` no falla aunque alguien ya escuche el nombre – cada proceso recibía solo una parte de los archivos. A partir del tercer o sexto intento funcionaba, porque entonces ya había una instancia abierta.
- Ahora hay un bloqueo de arranque (un named mutex en Windows, si no `flock`), antes de cargar Qt: exactamente un proceso se convierte en la instancia principal; los demás esperan y le pasan sus archivos.
- Además, el arranque en Windows comprueba antes de `listen()` si ya corre un servidor. Los archivos se reúnen solo cuando corre el bucle de eventos.
- Probado con 10 procesos iniciados en paralelo en Linux: un servidor, todos los archivos dentro. La parte del mutex para Windows no está probada.

### Insertar página en blanco
- En el menú contextual de la barra lateral de páginas y en el menú Páginas: «Insertar página en blanco – antes de la selección» y «Insertar página en blanco – después de la selección» (Ctrl+Alt+I).
- La página nueva toma el formato, la rotación y la caja trim/bleed de la página vecina. Traducido en todos los idiomas.

### Tirones
- La protección de la rueda del ratón (campos combo, spin y slider) corría como filtro sobre cada evento de la app – casi todos los 0,4–0,5 s al abrir pestañas y ventanas venían de ahí. Ahora se sustituye directamente el `wheelEvent` de esos campos; al arrancar, Passermark comprueba que funciona y, si no, vuelve al filtro antiguo.
- El diálogo de controladores (4–6 s) no era un cuelgue real, sino el diálogo abierto de Windows; ya no se registra en el protocolo.
- Al rasterizar durante la impresión (2–5,7 s), la ventana sigue dibujando entre las franjas – la impresión no se vuelve más rápida por ello.
- `load_settings` solo relee el archivo cuando ha cambiado.
- Primera ventana: el preflight carga urllib/SSL solo cuando hace falta.
- No atacado (exigiría rehacerlo en un hilo o proceso en segundo plano): `get_page` en `page_doc_bleeds` (1–1,5 s), `paintEvent` y la llamada de análisis del preflight en el panel de edición.

### CLI: caída con caracteres que la consola no puede mostrar
- Los informes de caída («→», cp1252) venían todavía de 1.10.4 – `emit` ya estaba corregido. Ahora todas las salidas de la CLI están aseguradas: los caracteres que la consola no puede mostrar se sustituyen en lugar de hacer caer el programa.

## 1.17.0

### Menú Color
- Un nuevo menú principal **Color** (entre Manipulación de documento y Ver) reúne todo lo relativo al color: comprobación de color, Softproof (Ctrl+Y, se configura como antes con Ctrl+Mayús+Y), exportar para la imprenta, conversión CMYK, papeles y mediciones, obtener perfiles estándar y la ayuda breve «La gestión del color en pocas palabras».
- Lo mismo como botones en la barra de herramientas del espacio de trabajo de preparación de impresión.
- El Softproof pasa del menú Ver al menú Color; Ctrl+Y se mantiene.
- Si falta ArgyllCMS (spotread) para medir, el menú de ayuda muestra un enlace con ayuda de instalación.

### Comprobación de color (Ctrl+Mayús+F)
- Una barra lateral como el preflight, pero para el papel: arriba eliges la condición de impresión (material o perfil del sistema); debajo aparece lo que contiene el documento – imágenes RGB por página, la mayor cobertura de tinta por página, colores directos y el output intent presente. Para la condición de impresión ves el perfil o el material y el ΔE2000 respecto al blanco de papel.
- Los hallazgos están en texto claro, cada uno con su botón: convertir, incrustar el output intent, separar de nuevo, medir papel, obtener perfiles adecuados o comprobación del documento. Los hallazgos se pueden pulsar como en el preflight (◀ ▶, marco rojo).
- Se comprueba: presencia de RGB; cobertura de tinta por encima del límite del perfil; output intent ausente o que no corresponde a la condición de impresión; colores directos presentes (solo aviso).

### Exportar para la imprenta
- Un asistente en cuatro pasos: elegir la condición de impresión (material o perfil del sistema), convertir según la recomendación, comprobar (antes y después), guardar.
- El perfil ICC se incrusta siempre como output intent.
- Si el archivo contiene RGB, Passermark pregunta siempre: ¿convertir o entregarlo con su perfil? No hay preselección.
- Opcionalmente Passermark crea un paquete `…_Druckerei.zip`: el PDF, los perfiles ICC utilizados y un informe (condición de impresión, intent, blanco de papel, avisos).
- El resultado es apto para PDF/X-4 según las reglas de Passermark: RGB resuelto, output intent en su sitio, cobertura de tinta dentro del límite. El archivo no se marca como PDF/X-4 y no se valida.
- Deliberadamente no incluido: una comparación de Softproof antes/después en el asistente – el resultado se ve con «Abrir en Passermark».

### CLI: press
- `passermark-cli press entrada.pdf salida.pdf` también hace la exportación para la imprenta en los flujos y los vigilantes: condición de impresión, conversión según la recomendación, output intent siempre incrustado.
- Si el archivo contiene RGB y `rgb` no está fijado, el trabajo se interrumpe en lugar de adivinar.
- El manual de la CLI tiene su propia sección sobre press.

### Papeles y mediciones
- Materiales propios sin derechos de administrador: viven en `~/.config/passermark/materials.json` y se guardan al instante. Los materiales de la administración se quedan; ambos aparecen en todas partes.
- El botón «Medir papel …» crea el papel e inicia la medición enseguida. «Buscar dispositivo» encuentra el aparato X-Rite a través de ArgyllCMS (spotread); si falta ArgyllCMS, se ofrece ayuda de instalación (paquete de Linux, descarga de Windows).
- Los tooltips explican el blanco de papel, el ΔE, la intención de renderizado (intent) y el output intent.
- En el diálogo de administración, la lista de materiales vacía ahora explica los cuatro pasos (crear el papel, medir el blanco de papel, asignar un perfil, elegirlo), en vez de estar en gris sin decir nada.
- Deliberadamente sigue sin incluirse: crear perfiles propios con una carta de pruebas.

### Perfiles estándar
- «Obtener perfiles estándar» carga PSO Coated v3, PSO Uncoated v3 (FOGRA52), FOGRA39/47, SC-B, GRACoL y SWOP desde registry.color.org en tu propia carpeta de ICC.
- No se incluyen en el programa: según el registro, los perfiles ECI solo pueden transmitirse con permiso de la ECI – usarlos e incrustarlos es libre.
- Las sugerencias de perfiles también muestran perfiles estándar aún no instalados; «Aplicar» los descarga y los asigna.

## 1.16.5

### Flujos: condiciones
- **«if» en cada paso:** un paso solo se ejecuta si se cumple su condición.
- **Bifurcaciones:** `{"choose": [{"if": …, "steps": […]}, {"else": …}]}` ejecuta exactamente la rama cuya condición es verdadera.
- **«fail» y «stop»:** fail rechaza el archivo (código de salida 1, código de error `rejected`), stop termina el flujo sin error. Ambos pueden llevar un mensaje, con `${pages}`, `${format}` etc.
- `check` señala los errores de escritura en una condición, con la posición exacta.
- Se puede comprobar: número de páginas, formato, medidas, sangrado, tamaño del archivo, nombre del archivo, errores y avisos del preflight, RGB, colores directos, fuentes que faltan, transparencia, capas y `var.NAME`.

### serve: --init y archivos rechazados
- `passermark-cli serve --init` (o `--init --system`, para todos) crea una plantilla `watch.json`, un flujo de ejemplo y la carpeta `hotfolder/beispiel`. Nunca se sobrescribe nada existente.
- El vigilante lleva los archivos rechazados por una condición a `failed/`, junto con el registro.
- El script de instalación de Linux y el instalador de Windows ejecutan una vez `serve --init --system` después de instalar, si todavía no hay nada.

### Nutzen (step & repeat): paso 2 al imprimir directamente
- El segundo montaje (paso 2) ahora también se aplica al imprimir directamente desde el diálogo de impresión – no solo con `passermark-cli impose`. Nueve tarjetas de visita en medio SRA3, montadas 2×, llegan así también a un SRA3.

### Preflight: hallazgos clicables
- Cada hallazgo nombra su sitio con claridad («página 2 – abajo a la derecha, 40 × 20 mm»).
- Un clic salta hasta él y lo enmarca en rojo; con ◀ ▶ recorres los hallazgos.

### Registro de impresión
- Se activa por usuario en los ajustes, o se impone como administrador (`print_log`: `force`, `dir`, `keep_days`).
- Por trabajo se escribe un JSON con los ajustes exactos, además de un `printlog.csv`. Carpeta por defecto: `printlog`.
- `passermark-cli reprint <log.json>` reimprime el trabajo. Si el original ha cambiado mientras tanto, aparece un aviso.

### Softproof
- En la vista: Ver → Softproof (Ctrl+Y) o con el botón de la barra de herramientas. Se configura con Ctrl+Mayús+Y; los cambios surten efecto de inmediato y el ajuste se recuerda.
- La condición de impresión es un material (por impresora), un perfil de la administración o un perfil CMYK del sistema. Se añaden la intención de renderizado (intent) y la BPC.
- A elegir: simular el color del papel, simular la tinta negra de impresión, usar el blanco de papel medido del material.
- Avisos para el intervalo de colores (los no imprimibles se vuelven magenta) y para la cobertura de tinta por encima de un límite ajustable en %.
- Con un perfil CMYK y Ghostscript la página se separa de verdad, como en la conversión CMYK: el CMYK existante permanece, el RGB y el gris se convierten. Sin Ghostscript, o con un perfil RGB de impresora, se aproxima mediante la imagen de pantalla. Abajo a la derecha se indica siempre qué se está simulando.
### Materiales
- Administración → nueva pestaña «Materiales», guardada con derechos de administrador como los perfiles.
- Por papel: nombre, gramaje, superficie, intención de renderizado, notas y el perfil por impresora (o para todas las impresoras).
- El gramaje y la superficie se rellenan previamente a partir del nombre, p. ej. «ungestrichen 120 g».
- El blanco de papel de tres maneras: con el aparato de medición a través de ArgyllCMS (spotread), con calibración y varias mediciones que se promedian – la dispersión se muestra; desde un archivo de medición (CGATS de i1Profiler o ArgyllCMS, se toma el campo sin color); o a mano como L*a*b*.
- Las sugerencias de perfiles ordenan los perfiles por ΔE2000 respecto al blanco de papel, con la misma superficie e impresora, con valoración y justificación. «Aplicar» asigna el perfil; un perfil del sistema se importa al mismo tiempo.
- Si nada encaja bien, aparece una sugerencia, p. ej. FOGRA52 de eci.org o medir un perfil propio.
- Al eliminar un perfil, los materiales pierden esa asignación automáticamente.
- Deliberadamente no incluido: crear un perfil con una carta de pruebas; los materiales en la línea de comandos (se sigue imprimiendo con el perfil de impresora de la administración).
- install.sh añade opcionalmente argyll a los paquetes apt (de lo contrario no hay aparato de medición en Linux).
### Material en el diálogo de impresión
- Al elegir un material se ajustan el perfil y la intención, y se ve el valor ΔE del blanco de papel al perfil. Al cambiar el perfil a mano, el material se deselecciona de nuevo.
### Material en la conversión CMYK
- El material ajusta el perfil de destino y la intención. El método se recomienda según el archivo: si el archivo ya se creó para ese perfil, el CMYK se mantiene; si se creó para otra cosa (p. ej. FOGRA39), todo se separa de nuevo, con ese perfil de origen si está instalado. La vista previa de color toma el blanco de papel medido.
## 1.15.1
### Nutzen (step & repeat): giro
- Si la rejilla no cabe entera en la hoja en ninguna orientación, gana ahora la orientación con el menor sobrante. Solo después cuenta «mejor sin girar».
- Los datos en vertical ahora se giran y quedan exactamente igual que los datos en horizontal.
- Cambiado igualmente en el paso 2 y para el caso de que una copia ni siquiera quepa sola en la hoja.
- Si todo cabe, sigue sin girarse. «Girar Nutzen: 0°» y «90°» siguen forzando el giro.

### Formatos de papel
- Las medidas ahora vienen siempre primero de la impresora, en este orden: `*PaperDimension`, si no `<</PageSize[b h]>>` de la PPD, si no del nombre o del texto mostrado (p. ej. «8K 270 x 390 mm») – y solo entonces de la tabla.
- Una sola tabla de formatos (papersizes.py) en lugar de tres. Nuevos: SRA4, SRA2, SRA0–1, la serie RA, A7–A10, ISO-B, C0–C10. Los valores existentes siguen igual.
- Una coma en lugar de un punto en la PPD se reconoce: las medidas se toman igualmente, y se avisa.
- Si falta el área imprimible, Passermark toma los márgenes que la impresora tiene en sus otros formatos. En los formatos sin márgenes es la hoja entera.
- El aviso del diálogo de impresión indica la causa y muestra las líneas PPD listas con los valores pt correctos.
- Las impresoras IPP y de Windows recurren al nombre y a la tabla cuando el controlador no dice nada o informa de 0 × 0.
- `caps --json` muestra ahora de dónde saca cada formato sus medidas, y los posibles errores de la PPD.

### Guardar como PDF
- Con «Como el documento» ya no aparece el aviso erróneo de A4. SRA4 y SRA2 están ahora también en la lista.

### JSON legibles
- Los presets guardan a partir de ahora solo lo que se aparta del valor estándar. Un preset de folleto queda p. ej. en `{"handling": "booklet", "sheet": "A3"}`.
- En el menú de la línea del preset está la casilla «Guardar todos los ajustes». Vale para todos los diálogos.
- `passermark-cli tidy archivo.json` acorta presets y flujos existentes. Con `--print` solo muestra; con `--full` vuelve a escribir un preset completo.
- Dos cosas tidy no acorta a propósito: pasos de flujo con `preset` (allí un valor estándar puede sobrescribir el preset adrede) y `layout` en el paso de impresión (los valores que faltan allí vienen del ajuste de administración, no del estándar del programa).

## 1.15.0
### Carpetas de entrada: passermark-cli serve (vigilante)
- `passermark-cli serve` vigila carpetas y envía cada archivo por el flujo asignado. La asignación está en `watch.json` (se toma de `--config`, si no la propia, si no la de todos).
- Tras el procesamiento, el resultado va a `output/`, el original a `processed/`; con errores el original va a `failed/` con un `.log` al lado. Cada uno de estos ajustes también puede ponerse a `""` (no conservar el resultado / borrar el original). Un flujo que solo imprime no conserva resultado por defecto.
- Fiable: un archivo solo se toma cuando lleva `settle` segundos sin cambios; los archivos copiados a medias (`.part`, `.tmp`) nunca se tocan. Cada archivo se mueve primero a `.passermark/` – dos vigilantes sobre la misma carpeta nunca procesan dos veces el mismo archivo, y tras un bloqueo los archivos quedados vuelven al siguiente inicio. Los resultados nunca vuelven a la carpeta de entrada y nunca se sobrescriben (`-1`, `-2` …).
- Opciones: `--check`, `--once` (código 1 si falla un archivo), `--json`, `--quiet`, `--log`.
- Como servicio: `linux/passermark-watch.service` con un usuario propio sin derechos (los pasos están en el archivo); para Windows `windows/watch-task.ps1`, que crea una tarea al arrancar el sistema.

### Carpetas de flujos: ablaeufe → workflows
- La carpeta se llama ahora `workflows`; una carpeta `ablaeufe` antigua se renombra automáticamente en la primera llamada. Si faltan los permisos, Passermark sigue leyendo la carpeta antigua.
- **Carpetas de flujos compartidas:** nuevo en la administración en General → «Más carpetas de flujos», p. ej. un recurso de red. Orden: propia → compartida → para todos; el primer flujo con el nombre es el que vale. Quién puede poner flujos allí lo regulan los permisos de la carpeta (p. ej. un grupo con permiso de escritura) – nadie necesita derechos de administrador para ello. `workflows --dirs` muestra de qué carpeta (user / shared / system) viene cada flujo.

### Paso de impresión
- **`"paper": "auto"`:** con el manejo de páginas «tamaño», el paso de impresión elige el papel que encaja con la página, para folletos dos páginas lado a lado (A5 → A4). Si la impresora no tiene un papel que encaje, un error muestra los formatos disponibles; con step & repeat o póster hay un error claro – allí hay que indicar el papel. Un `paper` vacío funciona como antes (el papel por defecto de la impresora).

### Corregido además
- Las especificaciones de páginas fuera del documento (p. ej. `pages: "1-2"` en un PDF de una página) ahora dan «la página 2 no existe …» en lugar de «list index out of range».

## 1.14.2
### Archivo → Propiedades … (Ctrl+D)
- Cinco pestañas:
  - **Archivo:** nombre, carpeta («Abrir carpeta», «Copiar ruta»), tamaño, modificado el, estado (guardado / modificado / solo en memoria / temporal). En documentos combinados, convertidos o creados a partir de imágenes aparece «Creado a partir de:» con los archivos de origen; en resultados «Resultado de …».
  - **Documento:** versión de PDF, título, autor, asunto, palabras clave, creado con / PDF generado con, creado el / modificado el; cifrado con método, permisos permitidos y denegados; perfil de salida (Output Intent), capas, campos de formulario, comentarios y sellos, marcadores, adjuntos, JavaScript, vista web rápida.
  - **Páginas:** tabla por página con formato, orientación, rotación, formato final y sangrado, y encima un resumen de los formatos.
  - **Fuentes:** nombre, tipo, incrustada, subconjunto, páginas. Las fuentes no incrustadas se resaltan en amarillo.
  - **Comprobación:** errores, avisos y notas con páginas.
- La ventana aparece al instante; los datos del documento se leen en el proceso de análisis y llegan poco después – el programa no se bloquea ni con archivos grandes. En documentos modificados se muestra el estado actual, no el archivo del disco. Los datos son los mismos que en `passermark-cli inspect`, que ahora también entrega los datos adicionales del documento.

### Guía de la línea de comandos (Ayuda, alemán e inglés)
- Secciones nuevas sobre flujos de trabajo (con carpetas de flujos), la impresión (con finishers), `inspect` y la interfaz para otros programas; también se añadieron: el resumen de comandos, consejos nuevos y el capítulo de perspectiva (vigilante, previsto para 1.15).
- Todos los ejemplos se ejecutan de verdad como pruebas, incluidos los JSON de flujo mostrados; solo el ejemplo de impresión se comprueba y no se ejecuta cuando no hay impresora configurada.
- La guía existe por ahora en alemán e inglés; húngaro, español y francés muestran como antes la inglesa.

## 1.14.1
### Línea de comandos: impresión
- **Paso `print` en los flujos:** impresora, papel, bandeja, soporte, dúplex (`none` | `long` | `short`), color (`color` | `gray`), copias, intercalado y rango de páginas – además de todas las opciones del diálogo de impresión (step & repeat, folleto, póster etc.), el perfil de color de la impresora de la administración y opciones de controlador en bruto directamente. `dry_run` no envía nada y solo muestra qué se enviaría.
- Se imprime por el mismo camino que desde el diálogo de impresión: con selección automática de bandeja y los ajustes del fabricante en Windows.
- Los valores se aceptan como valor de controlador, como nombre visible o como un fragmento inequívoco; si algo no encaja, el mensaje de error enumera todos los valores posibles.
- El PDF queda sin cambios tras imprimir – seguir trabajando, guardar o imprimir de nuevo con otros ajustes. Sin `output` solo imprime.
- **Comandos nuevos:** `printers` (impresoras con estado e impresora predeterminada) y `caps <impresora>` (todas las opciones del controlador con sus elecciones, formatos de papel y qué opción es responsable de papel, bandeja, soporte, dúplex, color, bandeja de salida y los finishers – grapado, perforado, plegado, grapado a cabalga, corte, desfase).
- Internamente: la sesión de impresión ahora vive sin Qt en `pdfdruck/session.py` para que la CLI pueda usarla; el programa la recibe vía `gui/common.py` como antes.
- Paquete de pruebas: los flujos 30 y 31 son simulacros (`dry_run`) y participan en «ejecutar todas las pruebas»; en la carpeta propia `ablaeufe-echt-drucken/` hay dos flujos que imprimen de verdad (no se ejecutan automáticamente).

## 1.14.0
### Línea de comandos: flujos de trabajo
- **Varios trabajos seguidos en un archivo JSON versionado** («flujo», versión de formato 1): los pasos se ejecutan uno tras otro, cada uno trabaja con el resultado del anterior. La salida solo se escribe si todo ha funcionado.
- **Comandos nuevos:** `run` (ejecutar un flujo, también con varias entradas – las imágenes y archivos de Office se convierten antes y se combinan con los PDF), `check` (validar sin ejecutar, todos los errores a la vez), `schema` (esquema JSON del archivo de flujo o de un trabajo), `inspect` (información del documento: páginas, formatos, formato final/sangrado, hallazgos del preflight – con `--check`), `version --json` (versión, versión de API y de formato, trabajos disponibles).
- **Variables** en la ruta de salida: `${…}` desde `--var`; integradas `${input}`, `${dir}`, `${stem}`, `${date}` y `${workflow_dir}`.
- **Los errores tipográficos son errores:** los ajustes desconocidos y los tipos incorrectos se notifican, nada cae silenciosamente a un valor por defecto.
- **Para programas externos:** eventos JSON estables (`start` → `step` → `progress` → `step_done` → `done`) y códigos de error fijos (`usage`, `not_found`, `invalid`, `failed`, `cancelled`) con paso y trabajo; la versión de API y de formato está en `version --json`. La interfaz está documentada en [docs/cli-api.md](docs/cli-api.md) (inglés, con resumen en alemán) – el contrato vinculante para programas externos, enlazado desde todos los README.

## 1.13.2
### Diálogo de impresión: vista previa en segundo plano
- **Vista previa sin esperas:** la hoja se monta y dibuja ahora en el proceso de renderizado; la ventana ya no espera por ello. Con un archivo grande, la vista previa tarda 0,001 s en la ventana principal, en lugar de bloqueos de hasta 6 s como antes. Si se cambia algo mientras sigue calculando, solo se dibuja hasta el final el estado más reciente.
- El tiempo de espera sigue ahí: la vista previa no está lista antes de 2–5 s, porque dibujar la página en sí tarda eso. Pero la ventana se puede seguir usando mientras tanto.
- **Varias copias (p. ej. step & repeat):** la página se renderiza una sola vez en lugar de una por copia – aproximadamente el doble de rápido. La imagen se desvía mínimamente por ser una imagen de trama; solo con tramas muy finas se ve un ligero moiré. Para imprimir se sigue usando el original.
- **Sin varias copias** la vista previa es idéntica al píxel a la de antes (comparado para páginas sueltas, 9 en 1, folleto, pliegos y dúplex).
- **Formato final/sangrado** sale ahora de los datos de página sin cargar las páginas; los valores son los mismos que antes.
- **Vista general de pliegos** se calcula también en segundo plano.
- **Todavía en la ventana principal:** cambiar a «Folleto como pliegos» tarda aún unos 0,9 s; la generación de los pliegos no se ha sacado fuera.
- **Vista de página:** las imágenes de página grandes se escalan en bruto inmediatamente al hacer zoom; la imagen nítida llega en segundo plano. El límite superior de la imagen de página sigue siendo de 16 megapíxeles.

### Fusionar en Windows
- **Una ventana:** si llegan varios archivos a la vez, todos caen en la misma ventana. Probado con 12 llamadas simultáneas: 1 ventana, 12 archivos, ordenados por nombre.
- **Botones nuevos:** «Añadir carpeta …», subir/bajar y «Ordenar por nombre». Los archivos también se pueden arrastrar; se muestra cuántos hay dentro.
- **Para muchos planos:** lo mejor es «Enviar a → Passermark – fusionar» – pasa todos los archivos de una vez y se crea una única vez en el primer inicio. Como alternativa, añadir la carpeta entera en la ventana.
- **Barra lateral:** las páginas marcadas se pueden mover. La barra amarilla muestra dónde quedarán; en el borde la barra sigue desplazándose automáticamente.

## 1.13.1
### Corrección de velocidad
- Pequeñas mejoras de velocidad en la nueva vista (renderizado).

## 1.13.0
### Vista más rápida (renovación del renderizado)
- **Renderizado en un proceso aparte:** las páginas las renderiza un proceso en segundo plano (`passermark-cli render-server`); la interfaz nunca espera por él. Solo hay una petición en vuelo, así que al hojear rápido no se acumulan peticiones anticuadas. Si el proceso se cuelga, se reinicia; si no arranca (o el PDF está protegido con contraseña), la vista renderiza dentro del programa como antes.
- **Una imagen por página:** cada página se renderiza una vez con aproximadamente el doble del tamaño de vista; los niveles de zoom hasta ese tamaño y las miniaturas solo se escalan a partir de ella. Las imágenes de una página se descomprimen una sola vez, en lugar de una por nivel de zoom y otra por miniatura.
- **El zoom fuerte renderiza solo la parte visible,** con precisión de píxel incluso con la vista girada. Al 400 % la página está un momento borrosa y luego nítida (antes se ampliaba y quedaba borrosa).
- **Guardar sobre el mismo archivo ya funciona en Windows:** el archivo se lee en memoria y queda libre en el disco.
- **Modo de edición:** al arrastrar, el objeto acompaña semitransparente; al aplicar, las imágenes antiguas quedan como marcadores de posición y se renuevan en segundo plano, primero la página editada. Antes todo se volvía blanco y todas las miniaturas se volvían a renderizar en la ventana principal.
- **La comprobación automática lee los archivos sin cambios directamente** – al abrir se ahorra el volver a guardar en la ventana principal.
- Localizar errores: con `PASSERMARK_RENDER=local` todo funciona como antes – así se comprueba rápido si la causa es el nuevo proceso de renderizado.
- Limitación conocida: soltar un objeto en el modo de edición tarda aún unos 1 s en páginas pesadas (la comprobación de seguridad compara la página antes y después). Un elemento usado en varias páginas puede cambiar en todas por una edición; por eso tras editar se vuelven a renderizar todas las páginas en segundo plano, primero la editada.

## 1.12.6
### Ajustes del preflight
- Pequeños ajustes en «Reducir el tamaño del archivo» (`shrink`) y en las comprobaciones del preflight; traducciones completadas; manual de la CLI (DE/EN) actualizado.

## 1.12.5
### Licencias
- El instalador y el AppImage ahora incluyen todos los avisos de licencia de terceros (paquetes de Python, Qt LGPL-3.0, Ghostscript AGPL-3.0 con referencia al código fuente, bibliotecas del sistema incluidas), consultables mediante la nueva entrada de menú Ayuda → Licencias.
- README: nueva sección sobre licencias de terceros, con el código fuente disponible previa solicitud.
### Documentación
- El manual de la CLI (DE/EN) se ha actualizado con `shrink` y `flatten_softmask`.

## 1.12.4
### Reducir el tamaño del archivo (nuevo)
- Disponible desde la pestaña «Tamaño del archivo» o Documento → «Reducir el tamaño del archivo …», también para archivos que no estén marcados como demasiado grandes.
- Cada medida se puede activar y desactivar individualmente:
  - **Sin pérdidas, activado por defecto:** reescribir (elimina versiones guardadas antiguas), quitar recursos sin usar, fusionar duplicados (fuentes, imágenes, perfiles ICC), eliminar datos de edición y miniaturas, recomprimir imágenes sin pérdidas (también quita el ZIP alrededor del JPEG si queda más pequeño).
  - **Desactivado por defecto:** 16 → 8 bits, eliminar adjuntos, eliminar el contenido de capas ocultas.
  - **Reducción de resolución opcional:** a 300/240/150/100 dpi con umbral y calidad JPEG, medido en la colocación más grande. Las máscaras suaves se escalan a la par.
- El resultado se abre en una ventana nueva y el original permanece sin cambios. Si el resultado no es más pequeño, el archivo se deja tal cual.
- CLI: `passermark-cli shrink in.pdf out.pdf [--set downsample=true --set target_dpi=150 …]`
- Ejemplo: un archivo de 34 MB con el mismo perfil CMYK incrustado 90 veces quedó en 0,5 MB, idéntico píxel a píxel.

## 1.12.3
### Preflight
- **Nueva pestaña «Tamaño del archivo»:** muestra adónde van los bytes: imágenes, fuentes, perfiles de color, datos de edición de Illustrator/Photoshop, miniaturas, adjuntos, contenido de página.
  - También enumera versiones guardadas antiguas, duplicados y las imágenes más grandes con sus dpi efectivos.
  - Advierte de archivos muy grandes (más de 20 MB por superficie A4) y duplicados grandes.

## 1.12.2
### Preflight
- **Degradados transparentes (máscara suave en patrones):** se detectan y se pueden reparar. Algunos RIP/plóteres los imprimen como una zona negra que tapa las imágenes inferiores. La nueva reparación «Convertir degradados transparentes en imágenes (300 dpi)» renderiza solo los degradados afectados, junto con lo que hay debajo, como una imagen opaca. El texto y los vectores superiores permanecen intactos. No hace falta Ghostscript.
- **Fotos HDR (gain map):** una foto HDR de móvil abierta con ambas imágenes ahora se detecta en la comprobación. Reparación: «Eliminar páginas auxiliares HDR …», con tamaño seleccionable y una fusión opcional del gain map.
- **Nueva pestaña «Imágenes y colores»:**
  - Espacio de color por imagen y página (RGB, CMYK, escala de grises, tintas directas), incluido el nombre exacto del perfil ICC y el output intent.
  - Resolución efectiva por colocación, también para imágenes usadas varias veces o dentro de formularios.
  - Tamaño máximo recomendado a 300 y 150 dpi, más la escala máxima por página.
  - Avisos de baja resolución e información sobre contenido RGB y tintas directas.

## 1.12.1
- **Edición: varios objetos y líneas a la vez.** «Escalar / mover …», «Eliminar objeto», «Aplicar»
  (fuente y tamaño) y «Eliminar línea» actúan ahora sobre todos los objetos o líneas elegidos, ya
  no solo sobre uno. Con varias líneas seleccionadas el campo de texto está bloqueado – cambiar el
  texto solo funciona con una línea
- **Edición: cambiar color.** Nuevo botón «Color …» para líneas de texto y objetos vectoriales, a
  elección CMYK (predeterminado, para impresión) o RGB; en los vectores relleno y contorno se
  eligen por separado. El negro 0/0/0/100 sigue siendo negro puro. El color se ajusta directamente
  en el contenido de la página – todo lo que queda fuera de la selección permanece intacto,
  incluidos los objetos que solo heredaron su color
- **Edición: visión general.** Las pestañas muestran la cantidad («Texto (12)», «Objetos (40)»); en
  la pestaña «Objetos» se puede filtrar por vectores o imágenes, con la cantidad por tipo. Con un
  filtro activo, un clic en la página solo selecciona ese tipo
- **Fotos HDR del móvil (iPhone, Android) reconocidas.** Estos JPG contienen junto a la foto un
  mapa de luminancia gris para pantallas HDR. Antes esto se convertía en una segunda página de otro
  tamaño – con colores erróneos en el plotter. Ahora aparece un aviso al abrir; «Reparar» produce
  una página con la foto sin cambios, tamaño seleccionable (como la imagen auxiliar o como está
  guardado en la foto). El mapa de luminancia puede calcularse opcionalmente. Sin pregunta
  (línea de comandos, impresión directa) se repara automáticamente
- **Corregido: tamaño de letra del texto en trayectoria.** Tras cambiarlo, la lista seguía
  mostrando el tamaño antiguo y cada cambio posterior agrandaba de nuevo (24 → 36 → 54 pt). Ahora
  se muestra el tamaño real; los arcos cortos con pocas letras también se reconocen como texto en
  trayectoria. «Aplicar» sin cambios deja la página intacta
- **Corregido: orden Z.** «Un paso adelante» en el objeto superior informaba falsamente «estructura
  de la página no reconocida» – ahora todo simplemente queda como está
- **Corregido: arrastrar texto con el ratón** abortaba con un mensaje de error en algunos PDF (p.
  ej. de Chrome)
- Traducciones añadidas para la disposición de las poses en el diálogo de impresión (inglés,
  húngaro, español, francés)

## 1.11.3
- **Diálogo VDP renovado.** Los datos variables lucen ahora como el diálogo de impresión: cuatro
  secciones numeradas plegables (campos, datos, numeración, salida) y arriba una «Guía» plegada.
  Las explicaciones de los campos son ahora tooltips y solo aparecen bajo el campo con el nuevo
  interruptor «Mostrar textos de ayuda». La nota de salida desactualizada remite ahora al orden
  del diálogo de impresión (Copias, «Siguiente página en cada copia»). El widget
  CollapsibleSection vive en common.py y lo comparten ambos diálogos.
- **Diálogo de impresión sin pestañas.** El selector de modo superior («¿Qué se va a imprimir?»)
  guía ahora en una sola columna continua: preset, modo, panel del modo, escalado («¿Cómo a la
  hoja?»), marcas de corte, papel/salida, finisher, gestión de color. La antigua navegación por
  pestañas desaparece.
- **El Step & Repeat es un modo propio.** «Nutzen» se une al selector de modo junto a hojas
  individuales, varias por hoja, folleto y póster – con texto explicativo como los demás modos.
  La antigua casilla se sustituye por el botón de modo; el panel Nutzen aparece donde los demás
  paneles de modo.
- **«¿Cómo a la hoja?»** el escalado y la orientación forman ahora un grupo: ajustar/tamaño
  original/reducir/personalizado, rotación, rotación automática, centrado, márgenes. La elección de
  escalado es visible y efectiva en todos los modos: ajustar = valor estándar del modo, tamaño original/reducir/personalizado
  anula el escalado del modo – los campos del modo (escalado por celda, escala Nutzen, póster) se mantienen.
- **Espejo y opciones del controlador plegables.** Ambas secciones siguen bien visibles con un
  título claro y solo se despliegan cuando hace falta – todas las opciones sin cambios.
- **Encuadernación de folleto: «Estándar» primero.** El clásico grapado por el lomo («todas las
  hojas intercaladas, plegadas una vez») encabeza ahora la lista de tipos con el nombre claro
  «Estándar» – el contador «hojas por pliezo» solo aparece con «Pliezos agrupados» y ya no sugiere
  un ajuste sin efecto.
- **Secciones plegables uniformes.** Cada bloque de la nueva columna – preset, selector de modo
  («¿Qué se va a imprimir?», «¿Cómo a la hoja?»), marcas de corte, papel/salida, finisher, gestión de
  color, espejo, controlador – lleva el mismo encabezado plegable y del mismo tamaño. Los botones de
  modo van uno debajo del otro: todas las etiquetas se mantienen legibles; el panel del modo se
  reduce al modo visible (sin espacios vacíos). Desde el modo «Nutzen» siempre se puede cambiar a
  otro.
- **Traducciones:** 26 mensajes nuevos/completados por idioma (EN/DE/ES/FR/HU); las cadenas de
  1.11.1 que faltaban en los catálogos ES/FR/HU/EN se han completado. Los presets antiguos siguen
  siendo totalmente compatibles (handling size/multiple/sr se siguen cargando).

## 1.11.2
- **Paso 2: montar la hoja de nuevo.** La hoja terminada del paso 1 se monta una segunda vez en un formato
  destino de libre elección (formatos del dispositivo o medidas propias en mm) – fila por fila, siempre
  centrada, contenido sin cambios; el resultado se puede emitir con un botón como documento nuevo
  (pestaña nueva), la vista previa lo muestra como en el paso 1 y el diálogo se cierra después. El giro
  y la orientación del paso 1 también valen para el paso 2. Rejilla: 0 × 0 = automática (tantas como quepan).
- **Usar las marcas de corte existentes.** En documentos con formato final (TrimBox), los lados
  exteriores del bloque de copias muestran el borde real del documento – las marcas de corte existentes
  permanecen visibles; las marcas propias siguen siendo activables con una casilla como siempre.
- **Montar la rejilla exactamente.** Una rejilla definida (p. ej. 3 × 3) siempre permanece exacta en el
  paso 1 y en el paso 2 – si no cabe en la hoja, se recorta simétricamente por el borde y se avisa,
  nunca se cancela.
- **Formato destino planificado sin márgenes:** p. ej. dos hojas A4 del paso 1 caben limpiamente en un A3.
- La ruta de impresión y la orientación del paso 1 permanecen sin cambios.

## 1.11.1
- **Formatos especiales: solo «Guardar como PDF».** Los formatos propios ya no se envían a las impresoras –
  los controladores y spoolers de Windows a menudo no aceptan tamaños especiales (hojas en blanco, cancelaciones);
  con «Guardar como PDF» (★) siguen siendo plenamente utilizables
- **Recortar: dos modos nuevos.** «Recortar bordes»: recortar la página por los cuatro lados en mm, sin formato
  destino; «Eliminar el espacio blanco»: detecta el contenido visible (incluido el ruido JPEG), el nuevo tamaño
  de página resulta del marco del contenido ± margen (también negativo), el contenido queda 1:1 (solo movido)

## 1.11.0
- **Datos variables – ventanas (grupos de páginas).** En plantillas de varias páginas, cada campo pertenece
  a una ventana (p. ej. «anversos (nombre), reversos (código QR)»); las ventanas se pueden crear, renombrar
  y eliminar – sus campos pasan entonces a la primera ventana. Selección de páginas por ventana: todas,
  impares (anversos), pares (reversos) o intervalos («1,3-5 o impares 1-50»); sin selección propia se aplica
  la capa base «todas las páginas». Distribución «hoja por hoja» (primero todas las páginas con el registro 1)
  o «página por página» (primero la página 1 con todos los registros); indicador «{0} registros → {1} páginas»
  y aviso «– {0} páginas sin ventana!»
- **Vista previa VDP:** formato final en verde, sangrado en rojo; marco interior ajustable (línea guía)
- **Indicador de página «actual / total»** en la barra de herramientas; escribir un número y Enter para ir directo
- **Reglas, medición y formato final permanentes en la barra de herramientas principal** – en todas las
  áreas de trabajo
- **Formato final y sangrado en la vista principal:** borde interior (formato final) en verde en lugar de
  rojo, sangrado como línea de puntos roja discreta en lugar de superficie plena
- **Medición con imán:** con Control pulsado, la cruceta se imanta a las líneas de corte e interiores (borde
  de página, formato final, sangrado) así como a los bordes de imágenes y líneas vectoriales – nunca al
  texto; la cruceta de previsualización se pega al borde hasta que el ratón se aleja claramente; Mayús
  sigue bloqueando horizontal/vertical/45°

## 1.10.7
- **CutContour: formas básicas sin cálculo.** Nueva colocación «Sobre el formato final (sin cálculo)»:
  rectángulo, rectángulo redondeado, círculo … se colocan directamente sobre el formato final (TrimBox, en
  su defecto la página) – sin renderizado, sin detección del motivo, sin procesos de trabajo, en fracciones
  de segundo. Distancia, tamaño, desplazamiento y arrastre con el ratón funcionan como antes. Solo se calcula
  con «Contorno» o cuando la forma se coloca alrededor del motivo o por objeto. Línea de comandos:
  `--set fit=trim`
- **Valor predeterminado en CutContour:** rectángulo sobre el formato final (mientras no haya ajustes
  propios de último uso guardados)

## 1.10.6
- **Corrección Windows: CutContour se quedaba atascado al 0 %** (desde 1.10.5). El cambio de la salida de la
  línea de comandos a UTF-8 se elimina de nuevo; la corrección de «Dividir páginas» se mantiene (mensajes de
  progreso en ASCII puro)
- CutContour: ya no hay error si un cálculo de vista previa llega tarde al cerrarse la ventana
  («expected LP_struct_fpdf_document_t … NoneType»)

## 1.10.5
- **Corrección Windows:** «Dividir páginas» (y toda tarea cuyo mensaje contiene caracteres como «→») se
  interrumpía con `UnicodeEncodeError … cp1252`. La línea de comandos ahora cambia ella misma su salida a
  UTF-8; los mensajes de progreso hacia la interfaz son ASCII puro
- `SECURITY.md`, `CONTRIBUTING.md` y las plantillas de GitHub para informes de errores y sugerencias en el
  paquete

## 1.10.4
- README bilingüe: `README.md` (inglés) y `README.de.md` (alemán), al día (dividir páginas, datos variables,
  introducir datos, todas las tareas de la línea de comandos) y con una nota sobre el estado del proyecto
- Configuración de ejemplo `data/defaults.example.json` con nombres de impresora neutros

## 1.10.3
- **Dividir páginas con el botón derecho:** seleccionar páginas en la barra lateral → botón derecho →
  **Dividir** → «Partir por la mitad verticalmente» / «Partir por la mitad horizontalmente» – al instante,
  solo las páginas seleccionadas, sin página de comparación. «Rejilla / más opciones …» abre el diálogo con la
  selección preajustada

## 1.10.2
- **Datos variables – anverso y reverso:** nuevo «Páginas por registro» (bajo el 2.): 2 = páginas 1+2 →
  registro 1, 3+4 → registro 2 … – tanto si la plantilla tiene 2 páginas como si ya tiene todas las tarjetas
  (p. ej. 200 páginas para 100 tarjetas de visita). Los campos «Solo en estas páginas» ahora conocen
  **impar** y **par**, también combinables con rangos («impar 1-50»). Ejemplo 7: tarjeta de visita con el
  nombre delante y una tarjeta QR detrás
- **Más variables:** {{datum}}, {{zeit}}, {{jahr}}, {{monat}}, {{tag}}, {{wochentag}}, {{kw}},
  {{datum_iso}}, {{datum:FORMAT}}, {{seite}}, {{seiten}}, {{vorlagenseite}}, {{datensatz}},
  {{datensaetze}}, {{datei}}, {{zufall}}, {{zufall:N}}, {{code:N}}, {{uuid}}. El botón **?** junto al
  contenido las muestra todas con un valor de ejemplo, doble clic inserta. Las columnas CSV con el mismo
  nombre tienen prioridad
- Un doble clic en una columna **sustituye** a un {{nr}} sin cambios en lugar de dejarlo delante
- **Dividir páginas** (Páginas → Dividir páginas …, área de trabajo Editar): partir por la mitad
  vertical/horizontalmente o en rejilla, todas/actuales/seleccionadas páginas o rango, solo dobles páginas,
  orden de derecha→izquierda; con vista previa de las líneas de corte. **Dividir dobles páginas** con un clic
  para folletos mal exportados. Sin pérdida (el contenido no se copia ni se rasteriza), las páginas giradas
  tal como se ven; con formato final se divide dentro y el sangrado queda fuera. Línea de comandos: tarea
  `split`
- **Barra lateral:** las miniaturas giran junto con «Girar vista izquierda/derecha»
- **Corregido: abrir desde fuera acababa en una ventana bloqueada** (Windows, botón derecho/doble clic
  mientras una herramienta está abierta en una ventana) – ahora su propia ventana. Causa: abrir en la ventana
  de inicio vacía dejaba una pestaña vacía invisible; ahora se usa la propia ventana vacía. Los resultados de
  una ventana bloqueada también se abren en su propia ventana

## 1.10.1
- **Usar directamente un CSV propio con otros nombres de columna:** Datos variables → Abrir CSV reconoce a
  qué se adapta la tabla («La tabla encaja con: QR – tarjeta de visita»), **Crear campo adecuado** crea el
  código QR con ese tipo. Las columnas se asignan automáticamente – también nombres ingleses, húngaros,
  españoles, franceses y los encabezados de las exportaciones de contactos de **Outlook, Google y Thunderbird**.
  El CSV queda sin cambios
- **Asignar columnas …** en el campo QR con tipo: elegir la columna por dato, «dejar vacío» o automático;
  con vista previa del contenido final. Debajo del tipo se indica qué viene de dónde y qué falta. La
  asignación se guarda en el preajuste (`qr_map`) y también vale en la línea de comandos
- Introducir datos: un CSV con nombres de columna extraños ya no recibe columnas duplicadas; el encabezado
  muestra la asignación («First Name → Vorname»). `datencheck` también reconoce nombres de columna extraños
- Carpeta de ejemplos: `kontakte-outlook.csv` (así se ve una exportación de Outlook); la guía ampliada con
  «CSV propio con otros nombres de columna»

## 1.10.0
- **Introducir datos** (área de trabajo Datos variables, menú Manipulación de documentos, o en el diálogo
  Datos variables bajo el 2.): crear la tabla de datos directamente en Passermark. Las columnas adecuadas por
  tipo – **tarjeta de visita QR (vCard), acceso WLAN, correo electrónico, dirección web, llamada, SMS, cita,
  ubicación**, texto QR libre, **Code 128**, **EAN-13**, texto con columnas propias. Cada fila se comprueba
  al instante (datos obligatorios, dígito de control EAN, diéresis en el Code 128, fecha …), a la derecha el
  código terminado de la fila seleccionada. Pegar desde Excel con Ctrl+V, duplicar filas, rellenar una columna
  con una serie de números (también crea las filas), columnas propias. Guardar como CSV (UTF-8 con BOM, punto
  y coma – Excel lee bien las diéresis)
- **«Usar en datos variables»** adopta la tabla como fuente de datos y crea el campo adecuado
- **Campo QR «Tipo de código QR»:** contenido tal como se introdujo o compuesto a partir de las columnas de
  la tabla (vCard, WLAN, mailto, tel, SMS, cita, geo). El CSV sigue siendo legible; Passermark construye el
  contenido del código al generar
- **Zona de silencio:** el código QR y el Code 128 ahora tienen un borde blanco en el campo (desactivable).
  Sin él, los códigos cercanos a otro contenido se leían mal. *Preajustes existentes: el código QR se vuelve
  un poco más pequeño en el campo por esto*
- **Un EAN-13 con 13 dígitos y un dígito de control incorrecto ahora es un error** (con el número correcto en
  el mensaje) – antes el último dígito se sustituía en silencio
- Línea de comandos: `datenarten`, `datenvorlage <tipo> [archivo.csv]`, `datencheck <archivo.csv> [tipo]`
  (código de retorno 1 ante problemas); en el preajuste `qr_type` por campo QR
- Ejemplos 5 (tarjeta de visita desde una lista de contactos) y 6 (acceso WLAN); la guía «Datos variables»
  con una nueva sección «Introducir datos», guía CLI ampliada
- Las pruebas ahora leen de verdad los códigos generados: QR y EAN-13 con OpenCV (si está instalado), Code 128
  con su propio lector con suma de control
- Corregido: los datos variables usaban «una copia del documento entero por registro» sin elegir la
  distribución en lugar de «el siguiente registro en cada página»

