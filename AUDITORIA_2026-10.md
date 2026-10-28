# Auditoría de código — PDF ToolOffice v2.0.0 → v2.1.0

**Fecha:** 23/10/2026 · **Alcance:** `app/` completo (Python, JS, HTML, CSS, Docker) · **Estado:** todos los hallazgos corregidos, salvo los marcados como *pendiente*.

Cada hallazgo se verificó reproduciéndolo (script o prueba) antes de corregirlo; las correcciones tienen prueba automatizada en `tests/` salvo donde se indica.

## Seguridad

| # | Severidad | Hallazgo | Corrección |
|---|---|---|---|
| S1 | Crítica | **Path traversal** en `/api/*-sesion` y `/api/descargar-edicion`: `edit_id` se concatenaba a la ruta sin validar. En Windows `edit_id=/../../../x` se normaliza a `x.pdf` fuera de `uploads` (reproducido) y permitía leer y **sobrescribir** cualquier `.pdf` accesible al proceso. | `sesiones.py` valida `^[0-9a-f]{32}$` antes de construir rutas. |
| S2 | Alta | **XSS almacenado** en `/admin/logs`: la tabla HTML insertaba sin escapar `detalle`, que contenía entradas del usuario (p. ej. `nivel` sin validar en unión, `modo` en división). | `html.escape` en todas las celdas; `nivel`/`modo` validados. |
| S3 | Media | Contraseña admin con valor por defecto conocido si faltaba `.env`; comparación no constante. | Sin contraseña (o con la de ejemplo) el panel queda deshabilitado; `hmac.compare_digest`. |
| S4 | Media | Errores 500 devolvían `str(e)` con rutas internas (`/api/paginas`, editor). | Errores internos → mensaje genérico; detalle solo en el log. |
| S5 | Media | `dpi` de render sin límite (`dpi=5000` → pixmap de cientos de MB). | Acotado 36–220. |
| S6 | Media | Cifrado RC4-128 (obsoleto). | AES-256. |
| S7 | Baja | Inyección de fórmulas: texto de un PDF que empieza por `=` se escribía como fórmula en el Excel exportado (PDF→Excel y export de logs). | Celdas forzadas a texto. |
| S8 | Baja | Documentos del editor en disco hasta 7 días; limpieza cada 24 h. | Sesiones expiran a las `EDIT_SESSION_HOURS` (8 h); limpieza cada hora; botón Cerrar las borra. |
| S9 | Media | El `Dockerfile` copiaba `app/uploads` (PDFs de usuarios) y `logs.db` dentro de la imagen (sin `.dockerignore`). | `.dockerignore` excluye uploads, database y `.env`. |
| S10 | Baja | Sin cabeceras de seguridad; nombres de archivo insertados con `innerHTML`. | `nosniff`, `X-Frame-Options`, `Referrer-Policy`; `textContent`. |

## Funcionamiento (bugs)

| # | Área | Hallazgo | Corrección |
|---|---|---|---|
| B1 | Editor | La redacción usaba el bbox completo del texto: con interlineado apretado **borraba la línea de abajo**. | Banda estrecha sobre la línea base. |
| B2 | Editor | `apply_redactions()` con valores por defecto **borraba bordes de tabla** y pintaba un **rectángulo blanco** sobre fondos de color. | `fill=False`, imágenes y trazos intactos. |
| B3 | Editor | Alias base14 inexistentes (`heob`, `hebb`, `coob`, `cobb`): editar texto en cursiva Helvetica/Courier fallaba. | Alias correctos (`heit`, `hebi`, `coit`, `cobi`). |
| B4 | Editor | Siempre reemplazaba con Helvetica/Times/Courier y desde el borde superior: fuente distinta y texto desplazado. | Misma familia del sistema (o equivalente métrico) en la línea base original. |
| B5 | Editor | Recuadros desplazados en páginas rotadas (no se aplicaba `rotation_matrix`). | Coordenadas de vista transformadas. |
| B6 | Editor | Texto de anotaciones (FreeText, sellos, campos) aparecía como editable: editarlo duplicaba el texto. | Se excluye de la detección. |
| B7 | Compresión | *Ultra* cambiaba el tamaño de página (×1,3) y reinsertaba la imagen como pixmap sin JPEG. | Mismo tamaño de página, JPEG real. |
| B8 | Compresión | *Media* y *Alta* solo diferían en `garbage=3/4`: en escaneos no reducían casi nada. | Reducción de resolución de imágenes por nivel. |
| B9 | Conversión | PDF→Word con `ARCHIVO.PDF` (mayúsculas): la ruta de salida coincidía con la de entrada. | Salida en carpeta temporal. |
| B10 | Conversión | Word→PDF: `&` o `<` rompían reportlab; **todas las tablas se omitían**. | Texto escapado, tablas renderizadas; LibreOffice si está instalado. |
| B11 | Conversión | Excel→PDF mostraba fórmulas (`=SUM(...)`) y solo la hoja activa; tablas anchas desbordaban. | `data_only`, todas las hojas visibles, horizontal y anchos proporcionales. |
| B12 | Conversión | Validación MIME (libmagic) **rechazaba DOCX/XLSX válidos** no generados por Office (los ve como `application/zip`). | Validación por estructura del paquete. |
| B13 | Conversión | Imágenes→PDF: PNG transparente con fondo negro, fotos de celular giradas (EXIF), TIFF multipágina solo la primera página, errores silenciados. | Fondo blanco, `exif_transpose`, todas las páginas, error claro si ninguna sirve. |
| B14 | Arranque | `python run.py` (según README) no existía en la raíz y `app/run.py` falla con import relativo. | `run.py` en la raíz; `FLASK_HOST/FLASK_PORT` del `.env` ahora se usan. |
| B15 | HTTP | Archivo > 50 MB devolvía HTML 413; el front mostraba "Error desconocido". | 413 en JSON. |
| B16 | División | Campos de rango vacíos extraían la página 1 en silencio. | Validación en front y back. |
| B17 | Docker | Volúmenes montados en `/app/uploads` pero la app escribe en `/app/app/uploads`; `libmupdf-dev` innecesario; root. | Rutas corregidas, usuario sin privilegios, fuentes libres, LibreOffice opcional. |
| B19 | Limpieza | Con varios workers de gunicorn, cada uno limpia `uploads/` a la vez y uno fallaba al tocar un archivo que otro ya borró (visto en el log al desplegar). | Errores de archivo ya borrado se ignoran por archivo. |
| B18 | Script | `test_compresion.ps1` usaba el alias `curl` de PowerShell (no acepta `-F`) y `-f` mal aplicado. | `curl.exe` y formato correcto. |

## Mantenibilidad

- **PyPDF2** está abandonado (último release 2022); se reemplazó por PyMuPDF, ya presente.
- `print` → `logging` (respeta `LOG_LEVEL`).
- Indentación mezclada tabs/espacios unificada a espacios.
- Sin pruebas → 65 pruebas `pytest` (pasan en Windows y dentro del contenedor Linux).
- Editor reescrito con sesiones versionadas (deshacer) y bloqueo entre procesos.

## Pendiente / fuera de alcance

- **Desplegado** el 23/10/2026 en `app-web-1` (Docker en WSL, puerto 5000): v2.1.0 con LibreOffice 25.2 y fuentes libres, usuario sin privilegios, volúmenes corregidos.
  *Actualización 28/10/2026: ese destino quedó atrás. Desde la v2.2.0, ese mismo 23/10, producción es el contenedor `pdf_tooloffice` en el servidor `192.168.1.250:3000`, desplegado desde `~/pdf_tooloffice` con `docker-compose.prod.yml`. La receta está en el `README.md`.*
- Aviso `The fitz API is deprecated` en el log: lo emite `pdf2docx` (dependencia externa); el código propio ya usa `import pymupdf`.
- **Licencias**: PyMuPDF es AGPL-3.0 y la app declara CC BY-NC 4.0 (licencia no pensada para software). Para uso interno no hay conflicto práctico; si se distribuye o se ofrece a terceros conviene revisarlo.
- Sin autenticación en la interfaz principal ni límite de peticiones: aceptable solo en red interna.
- `legacy/`, los `test_editado_*.pdf` de la raíz y `app/uploads/edit_*.pdf` (sesiones de agosto) son restos de pruebas anteriores; la limpieza automática borrará los de `uploads/` al arrancar. Los de la raíz se pueden borrar a mano.

---

# Auditoría del módulo de conversión PDF → Excel / Word (v2.2.0)

**Fecha:** 23/10/2026. **Método:** banco de pruebas con datos conocidos, ejecutado dentro del contenedor (Linux, LibreOffice 25.2, PyMuPDF 1.28, Camelot 2.0, Tesseract 5). Documentos:

| Documento | Características |
|---|---|
| Factura (Word → PDF) | tabla con bordes, descripciones de varias líneas, códigos con ceros, montos `1.234,56`, datos fuera de tabla (NIT, fecha, total) |
| Inventario (Excel → PDF) | 85 filas en 3 páginas, sin bordes, encabezado repetido, montos `1,234.56` |
| Extracto bancario | sin líneas verticales, filas sombreadas, débito/crédito con celdas vacías |
| Factura escaneada | la factura anterior como imagen a 200 dpi |

**Métrica:** % de filas reales que aparecen completas, en orden y en la columna correcta, y datos fuera de tabla recuperados.

| Motor | Factura | Inventario | Extracto | Escaneada | Tiempo |
|---|---|---|---|---|---|
| **Implementación anterior** | 0 % · datos 3/6 | 0 % | 0 % | 0 % | 0,3–3 s |
| PyMuPDF líneas | 100 % | 0 % | 0 % | 0 % | <1,5 s |
| PyMuPDF texto | 0 % | 0 % | 0 % | 0 % | <3 s |
| pdfplumber líneas / texto | 100 % / 0 % | 0 % / 0 % | 0 % / 0 % | 0 % | <1,3 s |
| Camelot lattice | 80 % | 0 % | 0 % | 0 % | <2 s |
| Camelot stream / network | 0 % | 100 % | 100 % | 0 % | <0,3 s |
| Camelot hybrid | 80 % | 100 % | 100 % | 0 % (60 % con OCR) | <2 s |
| img2table | 0 % | 100 % | 100 % | 0 % | <3 s |
| Docling (IBM, IA) | 100 % | **0 %** | 100 % | 100 % | **13–75 s** |
| **Nuevo (PyMuPDF + Camelot + OCR)** | **100 % · datos 6/6** | **100 %** | **100 % · datos 2/2** | **80 % · datos 6/6** | 0,7–3,7 s |

**Por qué no Docling:** es el mejor en escaneados, pero falló el inventario de varias páginas, tarda entre 20 y 100 veces más, añade cerca de 1 GB a la imagen y descarga modelos de internet al ejecutarse. Queda como alternativa si en el futuro predominan los escaneados.

## Hallazgos en la implementación anterior

| # | Hallazgo | Corrección |
|---|---|---|
| C1 | La detección "por texto" de pdfplumber se aplicaba primero y partía las tablas con bordes (0 % de filas correctas en la factura, aunque PyMuPDF sola obtiene 100 %). | Orden por tipo: bordes → PyMuPDF; sin bordes → Camelot. |
| C2 | Un único encabezado (el de la primera tabla) se aplicaba a todas las tablas y las filas se fusionaban o recortaban para ajustarse a él (`_normalize_row_to_header` unía celdas de 1–2 caracteres, p. ej. cantidades). | Encabezado por tabla; no se fusionan celdas. |
| C3 | Todo en una sola hoja con columnas Página/Tabla/Fila mezclando tablas distintas. | Una hoja por tabla + Resumen. |
| C4 | Las tablas que continúan en otra página quedaban como tablas separadas, con el encabezado repetido como fila de datos. | Se unen y se quita el encabezado repetido. |
| C5 | Todos los valores quedaban como texto: no se podía sumar ni filtrar por fecha. | Números, fechas y porcentajes reales por columna, con detección del separador decimal (`1.234,56` / `1,234.56`). |
| C6 | Todo lo que no era tabla (NIT, cliente, fechas, totales) se perdía si la página tenía alguna tabla. | Hojas Datos (pares etiqueta: valor) y Texto. |
| C7 | PDF escaneados: Excel vacío. PDF → Word: solo una imagen. | OCR Tesseract (español/inglés); para el OCR se borran las líneas de las tablas, que impedían leer el texto encerrado en cajas (comprobado). |
| C8 | Filas de texto de una sola celda de más de 45 caracteres se descartaban sin aviso. | Se conservan en la hoja Texto. |

## Pruebas de robustez

- Contrato de solo texto: 0 tablas falsas; la hoja Datos solo recoge datos reales (no la primera línea de cada cláusula).
- Inventario de 420 filas en 10 páginas: 1 tabla, 420/420 filas únicas, 7 s.
- Camelot devolvía a veces la misma tabla dos veces (una parcial) en una página: se descartan las tablas superpuestas.

## Limitaciones conocidas

- En escaneados la calidad depende del escaneo: el OCR puede confundir caracteres (por eso el Resumen pide revisar cifras de las páginas leídas con OCR).
- Tablas sin bordes con columnas muy juntas o celdas combinadas complejas pueden necesitar revisión manual.
- OCR y Camelot solo están en la imagen Docker; ejecutando la app directamente en Windows, sin ellos, los escaneados no se leen y las tablas sin bordes usan un método menos preciso (la hoja Resumen lo avisa).
