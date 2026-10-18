# Registro de cambios â Passermark

**English:** [CHANGELOG.md](CHANGELOG.md) Â· [Deutsch](CHANGELOG.de.md) Â· [Magyar](CHANGELOG.hu.md) Â· [FranÃ§ais](CHANGELOG.fr.md) Â· **EspaÃ±ol**

> Este registro contiene las versiones desde **1.10.0** en espaÃ±ol. El historial completo:
> [CHANGELOG.md](CHANGELOG.md) (inglÃ©s) o [CHANGELOG.de.md](CHANGELOG.de.md) (alemÃ¡n).

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
- `passermark-cli serve` vigila carpetas y envÃ­a cada archivo por el flujo asignado. La asignaciÃ³n estÃ¡ en `watch.json` (se toma de `--config`, si no la propia, si no la de todos).
- Tras el procesamiento, el resultado va a `output/`, el original a `processed/`; con errores el original va a `failed/` con un `.log` al lado. Cada uno de estos ajustes tambiÃ©n puede ponerse a `""` (no conservar el resultado / borrar el original). Un flujo que solo imprime no conserva resultado por defecto.
- Fiable: un archivo solo se toma cuando lleva `settle` segundos sin cambios; los archivos copiados a medias (`.part`, `.tmp`) nunca se tocan. Cada archivo se mueve primero a `.passermark/` â dos vigilantes sobre la misma carpeta nunca procesan dos veces el mismo archivo, y tras un bloqueo los archivos quedados vuelven al siguiente inicio. Los resultados nunca vuelven a la carpeta de entrada y nunca se sobrescriben (`-1`, `-2` â¦).
- Opciones: `--check`, `--once` (cÃ³digo 1 si falla un archivo), `--json`, `--quiet`, `--log`.
- Como servicio: `linux/passermark-watch.service` con un usuario propio sin derechos (los pasos estÃ¡n en el archivo); para Windows `windows/watch-task.ps1`, que crea una tarea al arrancar el sistema.

### Carpetas de flujos: ablaeufe â workflows
- La carpeta se llama ahora `workflows`; una carpeta `ablaeufe` antigua se renombra automÃ¡ticamente en la primera llamada. Si faltan los permisos, Passermark sigue leyendo la carpeta antigua.
- **Carpetas de flujos compartidas:** nuevo en la administraciÃ³n en General â Â«MÃ¡s carpetas de flujosÂ», p. ej. un recurso de red. Orden: propia â compartida â para todos; el primer flujo con el nombre es el que vale. QuiÃ©n puede poner flujos allÃ­ lo regulan los permisos de la carpeta (p. ej. un grupo con permiso de escritura) â nadie necesita derechos de administrador para ello. `workflows --dirs` muestra de quÃ© carpeta (user / shared / system) viene cada flujo.

### Paso de impresiÃ³n
- **`"paper": "auto"`:** con el manejo de pÃ¡ginas Â«tamaÃ±oÂ», el paso de impresiÃ³n elige el papel que encaja con la pÃ¡gina, para folletos dos pÃ¡ginas lado a lado (A5 â A4). Si la impresora no tiene un papel que encaje, un error muestra los formatos disponibles; con step & repeat o pÃ³ster hay un error claro â allÃ­ hay que indicar el papel. Un `paper` vacÃ­o funciona como antes (el papel por defecto de la impresora).

### Corregido ademÃ¡s
- Las especificaciones de pÃ¡ginas fuera del documento (p. ej. `pages: "1-2"` en un PDF de una pÃ¡gina) ahora dan Â«la pÃ¡gina 2 no existe â¦Â» en lugar de Â«list index out of rangeÂ».

## 1.14.2
### Archivo â Propiedades â¦ (Ctrl+D)
- Cinco pestaÃ±as:
  - **Archivo:** nombre, carpeta (Â«Abrir carpetaÂ», Â«Copiar rutaÂ»), tamaÃ±o, modificado el, estado (guardado / modificado / solo en memoria / temporal). En documentos combinados, convertidos o creados a partir de imÃ¡genes aparece Â«Creado a partir de:Â» con los archivos de origen; en resultados Â«Resultado de â¦Â».
  - **Documento:** versiÃ³n de PDF, tÃ­tulo, autor, asunto, palabras clave, creado con / PDF generado con, creado el / modificado el; cifrado con mÃ©todo, permisos permitidos y denegados; perfil de salida (Output Intent), capas, campos de formulario, comentarios y sellos, marcadores, adjuntos, JavaScript, vista web rÃ¡pida.
  - **PÃ¡ginas:** tabla por pÃ¡gina con formato, orientaciÃ³n, rotaciÃ³n, formato final y sangrado, y encima un resumen de los formatos.
  - **Fuentes:** nombre, tipo, incrustada, subconjunto, pÃ¡ginas. Las fuentes no incrustadas se resaltan en amarillo.
  - **ComprobaciÃ³n:** errores, avisos y notas con pÃ¡ginas.
- La ventana aparece al instante; los datos del documento se leen en el proceso de anÃ¡lisis y llegan poco despuÃ©s â el programa no se bloquea ni con archivos grandes. En documentos modificados se muestra el estado actual, no el archivo del disco. Los datos son los mismos que en `passermark-cli inspect`, que ahora tambiÃ©n entrega los datos adicionales del documento.

### GuÃ­a de la lÃ­nea de comandos (Ayuda, alemÃ¡n e inglÃ©s)
- Secciones nuevas sobre flujos de trabajo (con carpetas de flujos), la impresiÃ³n (con finishers), `inspect` y la interfaz para otros programas; tambiÃ©n se aÃ±adieron: el resumen de comandos, consejos nuevos y el capÃ­tulo de perspectiva (vigilante, previsto para 1.15).
- Todos los ejemplos se ejecutan de verdad como pruebas, incluidos los JSON de flujo mostrados; solo el ejemplo de impresiÃ³n se comprueba y no se ejecuta cuando no hay impresora configurada.
- La guÃ­a existe por ahora en alemÃ¡n e inglÃ©s; hÃºngaro, espaÃ±ol y francÃ©s muestran como antes la inglesa.

## 1.14.1
### LÃ­nea de comandos: impresiÃ³n
- **Paso `print` en los flujos:** impresora, papel, bandeja, soporte, dÃºplex (`none` | `long` | `short`), color (`color` | `gray`), copias, intercalado y rango de pÃ¡ginas â ademÃ¡s de todas las opciones del diÃ¡logo de impresiÃ³n (step & repeat, folleto, pÃ³ster etc.), el perfil de color de la impresora de la administraciÃ³n y opciones de controlador en bruto directamente. `dry_run` no envÃ­a nada y solo muestra quÃ© se enviarÃ­a.
- Se imprime por el mismo camino que desde el diÃ¡logo de impresiÃ³n: con selecciÃ³n automÃ¡tica de bandeja y los ajustes del fabricante en Windows.
- Los valores se aceptan como valor de controlador, como nombre visible o como un fragmento inequÃ­voco; si algo no encaja, el mensaje de error enumera todos los valores posibles.
- El PDF queda sin cambios tras imprimir â seguir trabajando, guardar o imprimir de nuevo con otros ajustes. Sin `output` solo imprime.
- **Comandos nuevos:** `printers` (impresoras con estado e impresora predeterminada) y `caps <impresora>` (todas las opciones del controlador con sus elecciones, formatos de papel y quÃ© opciÃ³n es responsable de papel, bandeja, soporte, dÃºplex, color, bandeja de salida y los finishers â grapado, perforado, plegado, grapado a cabalga, corte, desfase).
- Internamente: la sesiÃ³n de impresiÃ³n ahora vive sin Qt en `pdfdruck/session.py` para que la CLI pueda usarla; el programa la recibe vÃ­a `gui/common.py` como antes.
- Paquete de pruebas: los flujos 30 y 31 son simulacros (`dry_run`) y participan en Â«ejecutar todas las pruebasÂ»; en la carpeta propia `ablaeufe-echt-drucken/` hay dos flujos que imprimen de verdad (no se ejecutan automÃ¡ticamente).

## 1.14.0
### LÃ­nea de comandos: flujos de trabajo
- **Varios trabajos seguidos en un archivo JSON versionado** (Â«flujoÂ», versiÃ³n de formato 1): los pasos se ejecutan uno tras otro, cada uno trabaja con el resultado del anterior. La salida solo se escribe si todo ha funcionado.
- **Comandos nuevos:** `run` (ejecutar un flujo, tambiÃ©n con varias entradas â las imÃ¡genes y archivos de Office se convierten antes y se combinan con los PDF), `check` (validar sin ejecutar, todos los errores a la vez), `schema` (esquema JSON del archivo de flujo o de un trabajo), `inspect` (informaciÃ³n del documento: pÃ¡ginas, formatos, formato final/sangrado, hallazgos del preflight â con `--check`), `version --json` (versiÃ³n, versiÃ³n de API y de formato, trabajos disponibles).
- **Variables** en la ruta de salida: `${â¦}` desde `--var`; integradas `${input}`, `${dir}`, `${stem}`, `${date}` y `${workflow_dir}`.
- **Los errores tipogrÃ¡ficos son errores:** los ajustes desconocidos y los tipos incorrectos se notifican, nada cae silenciosamente a un valor por defecto.
- **Para programas externos:** eventos JSON estables (`start` â `step` â `progress` â `step_done` â `done`) y cÃ³digos de error fijos (`usage`, `not_found`, `invalid`, `failed`, `cancelled`) con paso y trabajo; la versiÃ³n de API y de formato estÃ¡ en `version --json`. La interfaz estÃ¡ documentada en [docs/cli-api.md](docs/cli-api.md) (inglÃ©s, con resumen en alemÃ¡n) â el contrato vinculante para programas externos, enlazado desde todos los README.

## 1.13.2
### DiÃ¡logo de impresiÃ³n: vista previa en segundo plano
- **Vista previa sin esperas:** la hoja se monta y dibuja ahora en el proceso de renderizado; la ventana ya no espera por ello. Con un archivo grande, la vista previa tarda 0,001 s en la ventana principal, en lugar de bloqueos de hasta 6 s como antes. Si se cambia algo mientras sigue calculando, solo se dibuja hasta el final el estado mÃ¡s reciente.
- El tiempo de espera sigue ahÃ­: la vista previa no estÃ¡ lista antes de 2â5 s, porque dibujar la pÃ¡gina en sÃ­ tarda eso. Pero la ventana se puede seguir usando mientras tanto.
- **Varias copias (p. ej. step & repeat):** la pÃ¡gina se renderiza una sola vez en lugar de una por copia â aproximadamente el doble de rÃ¡pido. La imagen se desvÃ­a mÃ­nimamente por ser una imagen de trama; solo con tramas muy finas se ve un ligero moirÃ©. Para imprimir se sigue usando el original.
- **Sin varias copias** la vista previa es idÃ©ntica al pÃ­xel a la de antes (comparado para pÃ¡ginas sueltas, 9 en 1, folleto, pliegos y dÃºplex).
- **Formato final/sangrado** sale ahora de los datos de pÃ¡gina sin cargar las pÃ¡ginas; los valores son los mismos que antes.
- **Vista general de pliegos** se calcula tambiÃ©n en segundo plano.
- **TodavÃ­a en la ventana principal:** cambiar a Â«Folleto como pliegosÂ» tarda aÃºn unos 0,9 s; la generaciÃ³n de los pliegos no se ha sacado fuera.
- **Vista de pÃ¡gina:** las imÃ¡genes de pÃ¡gina grandes se escalan en bruto inmediatamente al hacer zoom; la imagen nÃ­tida llega en segundo plano. El lÃ­mite superior de la imagen de pÃ¡gina sigue siendo de 16 megapÃ­xeles.

### Fusionar en Windows
- **Una ventana:** si llegan varios archivos a la vez, todos caen en la misma ventana. Probado con 12 llamadas simultÃ¡neas: 1 ventana, 12 archivos, ordenados por nombre.
- **Botones nuevos:** Â«AÃ±adir carpeta â¦Â», subir/bajar y Â«Ordenar por nombreÂ». Los archivos tambiÃ©n se pueden arrastrar; se muestra cuÃ¡ntos hay dentro.
- **Para muchos planos:** lo mejor es Â«Enviar a â Passermark â fusionarÂ» â pasa todos los archivos de una vez y se crea una Ãºnica vez en el primer inicio. Como alternativa, aÃ±adir la carpeta entera en la ventana.
- **Barra lateral:** las pÃ¡ginas marcadas se pueden mover. La barra amarilla muestra dÃ³nde quedarÃ¡n; en el borde la barra sigue desplazÃ¡ndose automÃ¡ticamente.

## 1.13.1
### CorrecciÃ³n de velocidad
- PequeÃ±as mejoras de velocidad en la nueva vista (renderizado).

## 1.13.0
### Vista mÃ¡s rÃ¡pida (renovaciÃ³n del renderizado)
- **Renderizado en un proceso aparte:** las pÃ¡ginas las renderiza un proceso en segundo plano (`passermark-cli render-server`); la interfaz nunca espera por Ã©l. Solo hay una peticiÃ³n en vuelo, asÃ­ que al hojear rÃ¡pido no se acumulan peticiones anticuadas. Si el proceso se cuelga, se reinicia; si no arranca (o el PDF estÃ¡ protegido con contraseÃ±a), la vista renderiza dentro del programa como antes.
- **Una imagen por pÃ¡gina:** cada pÃ¡gina se renderiza una vez con aproximadamente el doble del tamaÃ±o de vista; los niveles de zoom hasta ese tamaÃ±o y las miniaturas solo se escalan a partir de ella. Las imÃ¡genes de una pÃ¡gina se descomprimen una sola vez, en lugar de una por nivel de zoom y otra por miniatura.
- **El zoom fuerte renderiza solo la parte visible,** con precisiÃ³n de pÃ­xel incluso con la vista girada. Al 400 % la pÃ¡gina estÃ¡ un momento borrosa y luego nÃ­tida (antes se ampliaba y quedaba borrosa).
- **Guardar sobre el mismo archivo ya funciona en Windows:** el archivo se lee en memoria y queda libre en el disco.
- **Modo de ediciÃ³n:** al arrastrar, el objeto acompaÃ±a semitransparente; al aplicar, las imÃ¡genes antiguas quedan como marcadores de posiciÃ³n y se renuevan en segundo plano, primero la pÃ¡gina editada. Antes todo se volvÃ­a blanco y todas las miniaturas se volvÃ­an a renderizar en la ventana principal.
- **La comprobaciÃ³n automÃ¡tica lee los archivos sin cambios directamente** â al abrir se ahorra el volver a guardar en la ventana principal.
- Localizar errores: con `PASSERMARK_RENDER=local` todo funciona como antes â asÃ­ se comprueba rÃ¡pido si la causa es el nuevo proceso de renderizado.
- LimitaciÃ³n conocida: soltar un objeto en el modo de ediciÃ³n tarda aÃºn unos 1 s en pÃ¡ginas pesadas (la comprobaciÃ³n de seguridad compara la pÃ¡gina antes y despuÃ©s). Un elemento usado en varias pÃ¡ginas puede cambiar en todas por una ediciÃ³n; por eso tras editar se vuelven a renderizar todas las pÃ¡ginas en segundo plano, primero la editada.

## 1.12.6
### Ajustes del preflight
- PequeÃ±os ajustes en Â«Reducir el tamaÃ±o del archivoÂ» (`shrink`) y en las comprobaciones del preflight; traducciones completadas; manual de la CLI (DE/EN) actualizado.

## 1.12.5
### Licencias
- El instalador y el AppImage ahora incluyen todos los avisos de licencia de terceros (paquetes de Python, Qt LGPL-3.0, Ghostscript AGPL-3.0 con referencia al cÃ³digo fuente, bibliotecas del sistema incluidas), consultables mediante la nueva entrada de menÃº Ayuda â Licencias.
- README: nueva secciÃ³n sobre licencias de terceros, con el cÃ³digo fuente disponible previa solicitud.
### DocumentaciÃ³n
- El manual de la CLI (DE/EN) se ha actualizado con `shrink` y `flatten_softmask`.

## 1.12.4
### Reducir el tamaÃ±o del archivo (nuevo)
- Disponible desde la pestaÃ±a Â«TamaÃ±o del archivoÂ» o Documento â Â«Reducir el tamaÃ±o del archivo â¦Â», tambiÃ©n para archivos que no estÃ©n marcados como demasiado grandes.
- Cada medida se puede activar y desactivar individualmente:
  - **Sin pÃ©rdidas, activado por defecto:** reescribir (elimina versiones guardadas antiguas), quitar recursos sin usar, fusionar duplicados (fuentes, imÃ¡genes, perfiles ICC), eliminar datos de ediciÃ³n y miniaturas, recomprimir imÃ¡genes sin pÃ©rdidas (tambiÃ©n quita el ZIP alrededor del JPEG si queda mÃ¡s pequeÃ±o).
  - **Desactivado por defecto:** 16 â 8 bits, eliminar adjuntos, eliminar el contenido de capas ocultas.
  - **ReducciÃ³n de resoluciÃ³n opcional:** a 300/240/150/100 dpi con umbral y calidad JPEG, medido en la colocaciÃ³n mÃ¡s grande. Las mÃ¡scaras suaves se escalan a la par.
- El resultado se abre en una ventana nueva y el original permanece sin cambios. Si el resultado no es mÃ¡s pequeÃ±o, el archivo se deja tal cual.
- CLI: `passermark-cli shrink in.pdf out.pdf [--set downsample=true --set target_dpi=150 â¦]`
- Ejemplo: un archivo de 34 MB con el mismo perfil CMYK incrustado 90 veces quedÃ³ en 0,5 MB, idÃ©ntico pÃ­xel a pÃ­xel.

## 1.12.3
### Preflight
- **Nueva pestaÃ±a Â«TamaÃ±o del archivoÂ»:** muestra adÃ³nde van los bytes: imÃ¡genes, fuentes, perfiles de color, datos de ediciÃ³n de Illustrator/Photoshop, miniaturas, adjuntos, contenido de pÃ¡gina.
  - TambiÃ©n enumera versiones guardadas antiguas, duplicados y las imÃ¡genes mÃ¡s grandes con sus dpi efectivos.
  - Advierte de archivos muy grandes (mÃ¡s de 20 MB por superficie A4) y duplicados grandes.

## 1.12.2
### Preflight
- **Degradados transparentes (mÃ¡scara suave en patrones):** se detectan y se pueden reparar. Algunos RIP/plÃ³teres los imprimen como una zona negra que tapa las imÃ¡genes inferiores. La nueva reparaciÃ³n Â«Convertir degradados transparentes en imÃ¡genes (300 dpi)Â» renderiza solo los degradados afectados, junto con lo que hay debajo, como una imagen opaca. El texto y los vectores superiores permanecen intactos. No hace falta Ghostscript.
- **Fotos HDR (gain map):** una foto HDR de mÃ³vil abierta con ambas imÃ¡genes ahora se detecta en la comprobaciÃ³n. ReparaciÃ³n: Â«Eliminar pÃ¡ginas auxiliares HDR â¦Â», con tamaÃ±o seleccionable y una fusiÃ³n opcional del gain map.
- **Nueva pestaÃ±a Â«ImÃ¡genes y coloresÂ»:**
  - Espacio de color por imagen y pÃ¡gina (RGB, CMYK, escala de grises, tintas directas), incluido el nombre exacto del perfil ICC y el output intent.
  - ResoluciÃ³n efectiva por colocaciÃ³n, tambiÃ©n para imÃ¡genes usadas varias veces o dentro de formularios.
  - TamaÃ±o mÃ¡ximo recomendado a 300 y 150 dpi, mÃ¡s la escala mÃ¡xima por pÃ¡gina.
  - Avisos de baja resoluciÃ³n e informaciÃ³n sobre contenido RGB y tintas directas.

## 1.12.1
- **EdiciÃ³n: varios objetos y lÃ­neas a la vez.** Â«Escalar / mover â¦Â», Â«Eliminar objetoÂ», Â«AplicarÂ»
  (fuente y tamaÃ±o) y Â«Eliminar lÃ­neaÂ» actÃºan ahora sobre todos los objetos o lÃ­neas elegidos, ya
  no solo sobre uno. Con varias lÃ­neas seleccionadas el campo de texto estÃ¡ bloqueado â cambiar el
  texto solo funciona con una lÃ­nea
- **EdiciÃ³n: cambiar color.** Nuevo botÃ³n Â«Color â¦Â» para lÃ­neas de texto y objetos vectoriales, a
  elecciÃ³n CMYK (predeterminado, para impresiÃ³n) o RGB; en los vectores relleno y contorno se
  eligen por separado. El negro 0/0/0/100 sigue siendo negro puro. El color se ajusta directamente
  en el contenido de la pÃ¡gina â todo lo que queda fuera de la selecciÃ³n permanece intacto,
  incluidos los objetos que solo heredaron su color
- **EdiciÃ³n: visiÃ³n general.** Las pestaÃ±as muestran la cantidad (Â«Texto (12)Â», Â«Objetos (40)Â»); en
  la pestaÃ±a Â«ObjetosÂ» se puede filtrar por vectores o imÃ¡genes, con la cantidad por tipo. Con un
  filtro activo, un clic en la pÃ¡gina solo selecciona ese tipo
- **Fotos HDR del mÃ³vil (iPhone, Android) reconocidas.** Estos JPG contienen junto a la foto un
  mapa de luminancia gris para pantallas HDR. Antes esto se convertÃ­a en una segunda pÃ¡gina de otro
  tamaÃ±o â con colores errÃ³neos en el plotter. Ahora aparece un aviso al abrir; Â«RepararÂ» produce
  una pÃ¡gina con la foto sin cambios, tamaÃ±o seleccionable (como la imagen auxiliar o como estÃ¡
  guardado en la foto). El mapa de luminancia puede calcularse opcionalmente. Sin pregunta
  (lÃ­nea de comandos, impresiÃ³n directa) se repara automÃ¡ticamente
- **Corregido: tamaÃ±o de letra del texto en trayectoria.** Tras cambiarlo, la lista seguÃ­a
  mostrando el tamaÃ±o antiguo y cada cambio posterior agrandaba de nuevo (24 â 36 â 54 pt). Ahora
  se muestra el tamaÃ±o real; los arcos cortos con pocas letras tambiÃ©n se reconocen como texto en
  trayectoria. Â«AplicarÂ» sin cambios deja la pÃ¡gina intacta
- **Corregido: orden Z.** Â«Un paso adelanteÂ» en el objeto superior informaba falsamente Â«estructura
  de la pÃ¡gina no reconocidaÂ» â ahora todo simplemente queda como estÃ¡
- **Corregido: arrastrar texto con el ratÃ³n** abortaba con un mensaje de error en algunos PDF (p.
  ej. de Chrome)
- Traducciones aÃ±adidas para la disposiciÃ³n de las poses en el diÃ¡logo de impresiÃ³n (inglÃ©s,
  hÃºngaro, espaÃ±ol, francÃ©s)

## 1.11.3
- **DiÃ¡logo VDP renovado.** Los datos variables lucen ahora como el diÃ¡logo de impresiÃ³n: cuatro
  secciones numeradas plegables (campos, datos, numeraciÃ³n, salida) y arriba una Â«GuÃ­aÂ» plegada.
  Las explicaciones de los campos son ahora tooltips y solo aparecen bajo el campo con el nuevo
  interruptor Â«Mostrar textos de ayudaÂ». La nota de salida desactualizada remite ahora al orden
  del diÃ¡logo de impresiÃ³n (Copias, Â«Siguiente pÃ¡gina en cada copiaÂ»). El widget
  CollapsibleSection vive en common.py y lo comparten ambos diÃ¡logos.
- **DiÃ¡logo de impresiÃ³n sin pestaÃ±as.** El selector de modo superior (Â«Â¿QuÃ© se va a imprimir?Â»)
  guÃ­a ahora en una sola columna continua: preset, modo, panel del modo, escalado (Â«Â¿CÃ³mo a la
  hoja?Â»), marcas de corte, papel/salida, finisher, gestiÃ³n de color. La antigua navegaciÃ³n por
  pestaÃ±as desaparece.
- **El Step & Repeat es un modo propio.** Â«NutzenÂ» se une al selector de modo junto a hojas
  individuales, varias por hoja, folleto y pÃ³ster â con texto explicativo como los demÃ¡s modos.
  La antigua casilla se sustituye por el botÃ³n de modo; el panel Nutzen aparece donde los demÃ¡s
  paneles de modo.
- **Â«Â¿CÃ³mo a la hoja?Â»** el escalado y la orientaciÃ³n forman ahora un grupo: ajustar/tamaÃ±o
  original/reducir/personalizado, rotaciÃ³n, rotaciÃ³n automÃ¡tica, centrado, mÃ¡rgenes. La elecciÃ³n de
  escalado es visible y efectiva en todos los modos: ajustar = valor estÃ¡ndar del modo, tamaÃ±o original/reducir/personalizado
  anula el escalado del modo â los campos del modo (escalado por celda, escala Nutzen, pÃ³ster) se mantienen.
- **Espejo y opciones del controlador plegables.** Ambas secciones siguen bien visibles con un
  tÃ­tulo claro y solo se despliegan cuando hace falta â todas las opciones sin cambios.
- **EncuadernaciÃ³n de folleto: Â«EstÃ¡ndarÂ» primero.** El clÃ¡sico grapado por el lomo (Â«todas las
  hojas intercaladas, plegadas una vezÂ») encabeza ahora la lista de tipos con el nombre claro
  Â«EstÃ¡ndarÂ» â el contador Â«hojas por pliezoÂ» solo aparece con Â«Pliezos agrupadosÂ» y ya no sugiere
  un ajuste sin efecto.
- **Secciones plegables uniformes.** Cada bloque de la nueva columna â preset, selector de modo
  (Â«Â¿QuÃ© se va a imprimir?Â», Â«Â¿CÃ³mo a la hoja?Â»), marcas de corte, papel/salida, finisher, gestiÃ³n de
  color, espejo, controlador â lleva el mismo encabezado plegable y del mismo tamaÃ±o. Los botones de
  modo van uno debajo del otro: todas las etiquetas se mantienen legibles; el panel del modo se
  reduce al modo visible (sin espacios vacÃ­os). Desde el modo Â«NutzenÂ» siempre se puede cambiar a
  otro.
- **Traducciones:** 26 mensajes nuevos/completados por idioma (EN/DE/ES/FR/HU); las cadenas de
  1.11.1 que faltaban en los catÃ¡logos ES/FR/HU/EN se han completado. Los presets antiguos siguen
  siendo totalmente compatibles (handling size/multiple/sr se siguen cargando).

## 1.11.2
- **Paso 2: montar la hoja de nuevo.** La hoja terminada del paso 1 se monta una segunda vez en un formato
  destino de libre elecciÃ³n (formatos del dispositivo o medidas propias en mm) â fila por fila, siempre
  centrada, contenido sin cambios; el resultado se puede emitir con un botÃ³n como documento nuevo
  (pestaÃ±a nueva), la vista previa lo muestra como en el paso 1 y el diÃ¡logo se cierra despuÃ©s. El giro
  y la orientaciÃ³n del paso 1 tambiÃ©n valen para el paso 2. Rejilla: 0 Ã 0 = automÃ¡tica (tantas como quepan).
- **Usar las marcas de corte existentes.** En documentos con formato final (TrimBox), los lados
  exteriores del bloque de copias muestran el borde real del documento â las marcas de corte existentes
  permanecen visibles; las marcas propias siguen siendo activables con una casilla como siempre.
- **Montar la rejilla exactamente.** Una rejilla definida (p. ej. 3 Ã 3) siempre permanece exacta en el
  paso 1 y en el paso 2 â si no cabe en la hoja, se recorta simÃ©tricamente por el borde y se avisa,
  nunca se cancela.
- **Formato destino planificado sin mÃ¡rgenes:** p. ej. dos hojas A4 del paso 1 caben limpiamente en un A3.
- La ruta de impresiÃ³n y la orientaciÃ³n del paso 1 permanecen sin cambios.

## 1.11.1
- **Formatos especiales: solo Â«Guardar como PDFÂ».** Los formatos propios ya no se envÃ­an a las impresoras â
  los controladores y spoolers de Windows a menudo no aceptan tamaÃ±os especiales (hojas en blanco, cancelaciones);
  con Â«Guardar como PDFÂ» (â) siguen siendo plenamente utilizables
- **Recortar: dos modos nuevos.** Â«Recortar bordesÂ»: recortar la pÃ¡gina por los cuatro lados en mm, sin formato
  destino; Â«Eliminar el espacio blancoÂ»: detecta el contenido visible (incluido el ruido JPEG), el nuevo tamaÃ±o
  de pÃ¡gina resulta del marco del contenido Â± margen (tambiÃ©n negativo), el contenido queda 1:1 (solo movido)

## 1.11.0
- **Datos variables â ventanas (grupos de pÃ¡ginas).** En plantillas de varias pÃ¡ginas, cada campo pertenece
  a una ventana (p. ej. Â«anversos (nombre), reversos (cÃ³digo QR)Â»); las ventanas se pueden crear, renombrar
  y eliminar â sus campos pasan entonces a la primera ventana. SelecciÃ³n de pÃ¡ginas por ventana: todas,
  impares (anversos), pares (reversos) o intervalos (Â«1,3-5 o impares 1-50Â»); sin selecciÃ³n propia se aplica
  la capa base Â«todas las pÃ¡ginasÂ». DistribuciÃ³n Â«hoja por hojaÂ» (primero todas las pÃ¡ginas con el registro 1)
  o Â«pÃ¡gina por pÃ¡ginaÂ» (primero la pÃ¡gina 1 con todos los registros); indicador Â«{0} registros â {1} pÃ¡ginasÂ»
  y aviso Â«â {0} pÃ¡ginas sin ventana!Â»
- **Vista previa VDP:** formato final en verde, sangrado en rojo; marco interior ajustable (lÃ­nea guÃ­a)
- **Indicador de pÃ¡gina Â«actual / totalÂ»** en la barra de herramientas; escribir un nÃºmero y Enter para ir directo
- **Reglas, mediciÃ³n y formato final permanentes en la barra de herramientas principal** â en todas las
  Ã¡reas de trabajo
- **Formato final y sangrado en la vista principal:** borde interior (formato final) en verde en lugar de
  rojo, sangrado como lÃ­nea de puntos roja discreta en lugar de superficie plena
- **MediciÃ³n con imÃ¡n:** con Control pulsado, la cruceta se imanta a las lÃ­neas de corte e interiores (borde
  de pÃ¡gina, formato final, sangrado) asÃ­ como a los bordes de imÃ¡genes y lÃ­neas vectoriales â nunca al
  texto; la cruceta de previsualizaciÃ³n se pega al borde hasta que el ratÃ³n se aleja claramente; MayÃºs
  sigue bloqueando horizontal/vertical/45Â°

## 1.10.7
- **CutContour: formas bÃ¡sicas sin cÃ¡lculo.** Nueva colocaciÃ³n Â«Sobre el formato final (sin cÃ¡lculo)Â»:
  rectÃ¡ngulo, rectÃ¡ngulo redondeado, cÃ­rculo â¦ se colocan directamente sobre el formato final (TrimBox, en
  su defecto la pÃ¡gina) â sin renderizado, sin detecciÃ³n del motivo, sin procesos de trabajo, en fracciones
  de segundo. Distancia, tamaÃ±o, desplazamiento y arrastre con el ratÃ³n funcionan como antes. Solo se calcula
  con Â«ContornoÂ» o cuando la forma se coloca alrededor del motivo o por objeto. LÃ­nea de comandos:
  `--set fit=trim`
- **Valor predeterminado en CutContour:** rectÃ¡ngulo sobre el formato final (mientras no haya ajustes
  propios de Ãºltimo uso guardados)

## 1.10.6
- **CorrecciÃ³n Windows: CutContour se quedaba atascado al 0 %** (desde 1.10.5). El cambio de la salida de la
  lÃ­nea de comandos a UTF-8 se elimina de nuevo; la correcciÃ³n de Â«Dividir pÃ¡ginasÂ» se mantiene (mensajes de
  progreso en ASCII puro)
- CutContour: ya no hay error si un cÃ¡lculo de vista previa llega tarde al cerrarse la ventana
  (Â«expected LP_struct_fpdf_document_t â¦ NoneTypeÂ»)

## 1.10.5
- **CorrecciÃ³n Windows:** Â«Dividir pÃ¡ginasÂ» (y toda tarea cuyo mensaje contiene caracteres como Â«âÂ») se
  interrumpÃ­a con `UnicodeEncodeError â¦ cp1252`. La lÃ­nea de comandos ahora cambia ella misma su salida a
  UTF-8; los mensajes de progreso hacia la interfaz son ASCII puro
- `SECURITY.md`, `CONTRIBUTING.md` y las plantillas de GitHub para informes de errores y sugerencias en el
  paquete

## 1.10.4
- README bilingÃ¼e: `README.md` (inglÃ©s) y `README.de.md` (alemÃ¡n), al dÃ­a (dividir pÃ¡ginas, datos variables,
  introducir datos, todas las tareas de la lÃ­nea de comandos) y con una nota sobre el estado del proyecto
- ConfiguraciÃ³n de ejemplo `data/defaults.example.json` con nombres de impresora neutros

## 1.10.3
- **Dividir pÃ¡ginas con el botÃ³n derecho:** seleccionar pÃ¡ginas en la barra lateral â botÃ³n derecho â
  **Dividir** â Â«Partir por la mitad verticalmenteÂ» / Â«Partir por la mitad horizontalmenteÂ» â al instante,
  solo las pÃ¡ginas seleccionadas, sin pÃ¡gina de comparaciÃ³n. Â«Rejilla / mÃ¡s opciones â¦Â» abre el diÃ¡logo con la
  selecciÃ³n preajustada

## 1.10.2
- **Datos variables â anverso y reverso:** nuevo Â«PÃ¡ginas por registroÂ» (bajo el 2.): 2 = pÃ¡ginas 1+2 â
  registro 1, 3+4 â registro 2 â¦ â tanto si la plantilla tiene 2 pÃ¡ginas como si ya tiene todas las tarjetas
  (p. ej. 200 pÃ¡ginas para 100 tarjetas de visita). Los campos Â«Solo en estas pÃ¡ginasÂ» ahora conocen
  **impar** y **par**, tambiÃ©n combinables con rangos (Â«impar 1-50Â»). Ejemplo 7: tarjeta de visita con el
  nombre delante y una tarjeta QR detrÃ¡s
- **MÃ¡s variables:** {{datum}}, {{zeit}}, {{jahr}}, {{monat}}, {{tag}}, {{wochentag}}, {{kw}},
  {{datum_iso}}, {{datum:FORMAT}}, {{seite}}, {{seiten}}, {{vorlagenseite}}, {{datensatz}},
  {{datensaetze}}, {{datei}}, {{zufall}}, {{zufall:N}}, {{code:N}}, {{uuid}}. El botÃ³n **?** junto al
  contenido las muestra todas con un valor de ejemplo, doble clic inserta. Las columnas CSV con el mismo
  nombre tienen prioridad
- Un doble clic en una columna **sustituye** a un {{nr}} sin cambios en lugar de dejarlo delante
- **Dividir pÃ¡ginas** (PÃ¡ginas â Dividir pÃ¡ginas â¦, Ã¡rea de trabajo Editar): partir por la mitad
  vertical/horizontalmente o en rejilla, todas/actuales/seleccionadas pÃ¡ginas o rango, solo dobles pÃ¡ginas,
  orden de derechaâizquierda; con vista previa de las lÃ­neas de corte. **Dividir dobles pÃ¡ginas** con un clic
  para folletos mal exportados. Sin pÃ©rdida (el contenido no se copia ni se rasteriza), las pÃ¡ginas giradas
  tal como se ven; con formato final se divide dentro y el sangrado queda fuera. LÃ­nea de comandos: tarea
  `split`
- **Barra lateral:** las miniaturas giran junto con Â«Girar vista izquierda/derechaÂ»
- **Corregido: abrir desde fuera acababa en una ventana bloqueada** (Windows, botÃ³n derecho/doble clic
  mientras una herramienta estÃ¡ abierta en una ventana) â ahora su propia ventana. Causa: abrir en la ventana
  de inicio vacÃ­a dejaba una pestaÃ±a vacÃ­a invisible; ahora se usa la propia ventana vacÃ­a. Los resultados de
  una ventana bloqueada tambiÃ©n se abren en su propia ventana

## 1.10.1
- **Usar directamente un CSV propio con otros nombres de columna:** Datos variables â Abrir CSV reconoce a
  quÃ© se adapta la tabla (Â«La tabla encaja con: QR â tarjeta de visitaÂ»), **Crear campo adecuado** crea el
  cÃ³digo QR con ese tipo. Las columnas se asignan automÃ¡ticamente â tambiÃ©n nombres ingleses, hÃºngaros,
  espaÃ±oles, franceses y los encabezados de las exportaciones de contactos de **Outlook, Google y Thunderbird**.
  El CSV queda sin cambios
- **Asignar columnas â¦** en el campo QR con tipo: elegir la columna por dato, Â«dejar vacÃ­oÂ» o automÃ¡tico;
  con vista previa del contenido final. Debajo del tipo se indica quÃ© viene de dÃ³nde y quÃ© falta. La
  asignaciÃ³n se guarda en el preajuste (`qr_map`) y tambiÃ©n vale en la lÃ­nea de comandos
- Introducir datos: un CSV con nombres de columna extraÃ±os ya no recibe columnas duplicadas; el encabezado
  muestra la asignaciÃ³n (Â«First Name â VornameÂ»). `datencheck` tambiÃ©n reconoce nombres de columna extraÃ±os
- Carpeta de ejemplos: `kontakte-outlook.csv` (asÃ­ se ve una exportaciÃ³n de Outlook); la guÃ­a ampliada con
  Â«CSV propio con otros nombres de columnaÂ»

## 1.10.0
- **Introducir datos** (Ã¡rea de trabajo Datos variables, menÃº ManipulaciÃ³n de documentos, o en el diÃ¡logo
  Datos variables bajo el 2.): crear la tabla de datos directamente en Passermark. Las columnas adecuadas por
  tipo â **tarjeta de visita QR (vCard), acceso WLAN, correo electrÃ³nico, direcciÃ³n web, llamada, SMS, cita,
  ubicaciÃ³n**, texto QR libre, **Code 128**, **EAN-13**, texto con columnas propias. Cada fila se comprueba
  al instante (datos obligatorios, dÃ­gito de control EAN, diÃ©resis en el Code 128, fecha â¦), a la derecha el
  cÃ³digo terminado de la fila seleccionada. Pegar desde Excel con Ctrl+V, duplicar filas, rellenar una columna
  con una serie de nÃºmeros (tambiÃ©n crea las filas), columnas propias. Guardar como CSV (UTF-8 con BOM, punto
  y coma â Excel lee bien las diÃ©resis)
- **Â«Usar en datos variablesÂ»** adopta la tabla como fuente de datos y crea el campo adecuado
- **Campo QR Â«Tipo de cÃ³digo QRÂ»:** contenido tal como se introdujo o compuesto a partir de las columnas de
  la tabla (vCard, WLAN, mailto, tel, SMS, cita, geo). El CSV sigue siendo legible; Passermark construye el
  contenido del cÃ³digo al generar
- **Zona de silencio:** el cÃ³digo QR y el Code 128 ahora tienen un borde blanco en el campo (desactivable).
  Sin Ã©l, los cÃ³digos cercanos a otro contenido se leÃ­an mal. *Preajustes existentes: el cÃ³digo QR se vuelve
  un poco mÃ¡s pequeÃ±o en el campo por esto*
- **Un EAN-13 con 13 dÃ­gitos y un dÃ­gito de control incorrecto ahora es un error** (con el nÃºmero correcto en
  el mensaje) â antes el Ãºltimo dÃ­gito se sustituÃ­a en silencio
- LÃ­nea de comandos: `datenarten`, `datenvorlage <tipo> [archivo.csv]`, `datencheck <archivo.csv> [tipo]`
  (cÃ³digo de retorno 1 ante problemas); en el preajuste `qr_type` por campo QR
- Ejemplos 5 (tarjeta de visita desde una lista de contactos) y 6 (acceso WLAN); la guÃ­a Â«Datos variablesÂ»
  con una nueva secciÃ³n Â«Introducir datosÂ», guÃ­a CLI ampliada
- Las pruebas ahora leen de verdad los cÃ³digos generados: QR y EAN-13 con OpenCV (si estÃ¡ instalado), Code 128
  con su propio lector con suma de control
- Corregido: los datos variables usaban Â«una copia del documento entero por registroÂ» sin elegir la
  distribuciÃ³n en lugar de Â«el siguiente registro en cada pÃ¡ginaÂ»

