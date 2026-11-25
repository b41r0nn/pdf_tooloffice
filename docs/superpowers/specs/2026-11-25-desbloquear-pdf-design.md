# Quitar la contraseña de un PDF protegido · diseño

**Fecha:** 2026-11-25 · **Módulo:** Proteger · **Versión prevista:** 2.6.0

## Para qué, y por qué ahora

*Proteger* hoy solo sabe **poner** contraseña. Falta lo contrario: un PDF propio que
llega cifrado y del que **se conoce la contraseña** hay que poder dejarlo listo para
trabajar —leerlo, imprimirlo, convertirlo, archivarlo— sin volver a escribir la clave
cada vez que se abre.

Lo que dijo el dueño, en sus términos: *"una herramienta que se centre en archivos PDF y
que incluya una opción para quitar la contraseña de un PDF protegido sin modificar su
contenido"*, con la contraseña escrita por el usuario en un campo, el original intacto y
un mensaje claro cuando la contraseña no sirve.

## Objetivos

- Quitar el cifrado de un PDF con la contraseña que da el usuario y devolver **un PDF
  nuevo** que se abre sin pedir nada.
- **Conservar** páginas, texto, imágenes, diseño y metadatos.
- **No tocar el original**: la entrada se sube, se procesa en una copia temporal y se borra.
- Opción para quitar también **restricciones de impresión y copia**.
- Aprovechar lo que ya existe en el panel: varios archivos a la vez (tanda) y la casilla
  del ZIP.
- Decir con claridad qué pasó cuando no se puede: contraseña incorrecta, archivo que no
  está protegido, archivo dañado.

## No objetivos

- **Otros formatos.** Desbloquear `.xlsx` o `.docx` protegidos exige `msoffcrypto-tool`,
  una dependencia nueva, que es decisión del dueño. Queda fuera de este trabajo y se
  retoma si aparece la necesidad real.
- **Adivinar, probar o romper contraseñas.** Sin contraseña no se desbloquea un PDF que
  la pide para abrirse. La herramienta sirve para documentos cuya clave ya se conoce.
- **Cambiar el modo Proteger**, que se queda exactamente como está.

## Anti objetivos (sería un fracaso aunque "funcione")

- Entregar un PDF "desbloqueado" al que le falten páginas, texto o metadatos.
- Confundir las causas: decir "contraseña incorrecta" de un archivo que en realidad está
  dañado, o al revés.
- Dejar a la persona sin saber qué hacer a continuación.
- Que la contraseña acabe escrita en los logs.

## Restricciones

- **Sin dependencias nuevas**: PyMuPDF y la biblioteca estándar.
- Español en código, mensajes e interfaz. `ValueError` = culpa del usuario → 400 con el
  mensaje visible tal cual; cualquier otra excepción → 500 genérico.
- Los scripts del navegador comparten un único ámbito global (ver `CLAUDE.md`).
- Accesibilidad: las pastillas son `input[type=radio]` de verdad con su `label`; el campo
  de contraseña con etiqueta; nada comunicado solo por color.
- Responsivo de 320 a 1440 px, verificado.
- Finales de línea LF.

## Formas consideradas

| | Cómo sería | Qué cuesta |
|---|---|---|
| **A. Selector de modo** *(elegida)* | Dos pastillas en el panel, *Poner contraseña* / *Quitar contraseña*, con el patrón de `.pill-option` que ya usan los niveles de compresión. El paso de la contraseña y la etiqueta del botón cambian con el modo. Endpoint nuevo `/api/desbloqueo`. | Hay que esconder y mostrar pasos según el modo, y `procesarTanda` tiene que armar la petición del modo activo. |
| **B. Dos botones en el mismo panel** | Cada uno con su paso y su endpoint. | Más barato de escribir y peor de usar: dos botones primarios compiten y el campo de contraseña significa cosas distintas según cuál se pulse. |
| **C. Pestaña nueva «Desbloquear»** | Panel aparte. | Descartada: el dueño fijó la ubicación dentro de *Proteger*, y duplicaría la lista de archivos, la tanda y el ZIP. |

## Decisiones

**Servidor**

- `services.desbloquear_pdf(ruta, contrasena='', quitar_restricciones=False)`:
  - Abre con la contraseña. Si el PDF **pide contraseña** y la que llega no sirve →
    `ValueError('La contraseña no es correcta. Escribe la contraseña con la que se abre
    este PDF.')`
  - Si **no pide contraseña y no tiene restricciones** → `ValueError('«<nombre>» no tiene
    contraseña ni restricciones: no hay nada que quitar.')`
  - Si **no pide contraseña pero sí tiene restricciones** y la casilla está desmarcada →
    `ValueError` que nombra el archivo y dice qué marcar. Con la casilla marcada, se
    procesa.
  - Guarda con `encryption=fitz.PDF_ENCRYPT_NONE` y **sin** `garbage` ni `deflate`, al
    contrario que el resto de la app: aquí manda la fidelidad, no el tamaño.
  - **Comprueba su propio resultado** antes de devolverlo: lo reabre y exige que no pida
    contraseña, que tenga las mismas páginas y que el texto de cada página coincida. Si
    no cuadra, no se entrega y el mensaje lo dice.
- `POST /api/desbloqueo`: campos `archivo`, `contrasena` (opcional),
  `quitar_restricciones`. Salida `<nombre>_sin_contrasena.pdf`. Registra en el log con
  módulo `desbloqueo` y **nunca** la contraseña.
- Nota técnica que justifica el `encryption=`: sin ese parámetro PyMuPDF **conserva** el
  cifrado al guardar (`PDF_ENCRYPT_KEEP`), así que el archivo saldría igual de protegido.

**Pantalla**

- Dos pastillas (`radiogroup`) arriba del panel: *Poner contraseña* (marcada) y *Quitar
  contraseña*.
- En *Quitar*: **un** campo, *Contraseña actual*, con la nota de que se deja vacío si el
  PDF se abre sin pedirla; casilla *Quitar también las restricciones de impresión y
  copia*; el paso de "repite la contraseña" se esconde. El botón dice *Quitar contraseña*.
- Sigue valiendo la tanda: varios PDF con **la misma** contraseña, sueltos o en ZIP.
  Un archivo que falla no tumba la tanda, como ya ocurre hoy.

**Por qué la casilla es solo para las restricciones**: los permisos viven dentro del
diccionario de cifrado, así que al quitar la contraseña de apertura se van con ella. No
son separables. La casilla cubre el otro caso: el PDF que abre sin pedir nada pero no deja
imprimir ni copiar.

## Lo que queda al constructor

- El texto fino de los mensajes, dentro de lo acordado arriba.
- Dónde exactamente caen las pastillas y los pasos dentro del panel, y cómo se esconden.
- Si la comprobación del texto por página se hace completa o acotada por tamaño, siempre
  que un cambio de contenido no pase inadvertido.
- Las pruebas: por TDD, en rojo antes del código, cubriendo al menos contraseña correcta,
  contraseña incorrecta, PDF sin protección, PDF solo con restricciones con la casilla
  marcada y sin marcar, metadatos conservados, y que el original no cambia.
