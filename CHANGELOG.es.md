# Registro de cambios – Passermark

**English:** [CHANGELOG.md](CHANGELOG.md) · [Deutsch](CHANGELOG.de.md) · [Magyar](CHANGELOG.hu.md) · [Français](CHANGELOG.fr.md) · **Español**

> Este registro contiene las versiones **1.10.x** en español. El historial completo:
> [CHANGELOG.md](CHANGELOG.md) (inglés) o [CHANGELOG.de.md](CHANGELOG.de.md) (alemán).

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
