# PDF ToolOffice

Aplicación web para manipulación de documentos PDF: unión, división, conversión, compresión, cifrado y **edición** (texto, firmas, imágenes, formularios y páginas).

**Versión:** 2.4.0
**Última actualización:** 28/10/2026
**Uso interno bajo licencia de no comercialización:** REPRESENTACIONES Y DISTRIBUCIONES HOSPITALARIAS S.A.S "REDIHOS" - PROYECTO EDUCATIVO

---

## Tabla de contenidos

- [Inicio rápido](#inicio-rápido)
- [Configuración](#configuración)
- [Dividir un PDF](#dividir-un-pdf)
- [Editor de PDF](#editor-de-pdf)
- [Conversión PDF → Excel / Word](#conversión-pdf--excel--word)
- [Herramientas libres utilizadas](#herramientas-libres-utilizadas)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Endpoints](#endpoints)
- [Compresión](#compresión)
- [Conversión Office → PDF](#conversión-office--pdf)
- [Seguridad](#seguridad)
- [Pruebas](#pruebas)
- [Troubleshooting](#troubleshooting)
- [Changelog](#changelog)

---

## Inicio rápido

### Windows (PowerShell)

```powershell
cd pdf_tooloffice
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r app\requirements.txt
python run.py
```

### Linux / WSL

```bash
cd pdf_tooloffice
python3 -m venv .venv && source .venv/bin/activate
pip install -r app/requirements.txt
python run.py
```

`run.py` está en la raíz del proyecto (también funciona `python -m app.run`). Host y puerto se toman de `.env` (`FLASK_HOST`, `FLASK_PORT`); por defecto `127.0.0.1:5000`. Para que otros equipos de la red la usen, `FLASK_HOST=0.0.0.0`.

### Docker

```bash
cd pdf_tooloffice
docker compose up -d --build        # construye (con LibreOffice) y reemplaza el contenedor app-web-1
docker compose logs -f web          # ver logs
```

El `docker-compose.yml` está en la raíz del proyecto. Para una imagen sin LibreOffice:
`docker compose build --build-arg INSTALAR_LIBREOFFICE=0`.

### Servidor de producción (192.168.1.250, puerto 3000)

Vive en `/home/sistemas/pdf_tooloffice` (no es git: se copia) y usa `docker-compose.prod.yml`: contenedor `pdf_tooloffice`, usuario `app` (uid 1000), `restart: unless-stopped`, puerto `192.168.1.250:3000`, 2 workers, límite de 1,5 GB de RAM y chequeo de salud. El `.env` del servidor es propio (permisos 600) y no se copia desde el PC.

```bash
# desde el PC (Git Bash), en la carpeta pdf_tooloffice
tar --force-local -czf /tmp/pdf.tgz --exclude=./.venv_test --exclude=./.venv_wsl --exclude=./legacy     --exclude='__pycache__' --exclude='./app/uploads/*' --exclude='./app/database/*' --exclude=./.env .
scp /tmp/pdf.tgz sysadmin-prod:~/pdf.tgz
ssh sysadmin-prod 'cd ~/pdf_tooloffice && tar xzf ~/pdf.tgz && docker compose -f docker-compose.prod.yml up -d --build'
```

Acceso: `http://192.168.1.250:3000`. Logs: `docker logs -f pdf_tooloffice`.

---

## Configuración

Archivo `.env` en la raíz del proyecto:

```env
ADMIN_PASSWORD=<genera una con: python -c "import secrets; print(secrets.token_hex(16))">
DATABASE_LOG_RETENTION_DAYS=30
UPLOAD_CLEANUP_DAYS=7        # temporales huérfanos en uploads/
EDIT_SESSION_HOURS=8         # las sesiones del editor se borran tras N horas sin uso
DEBUG=False
FLASK_HOST=0.0.0.0
FLASK_PORT=5000
LOG_LEVEL=INFO
# Opcionales
# SOFFICE_PATH=C:\Program Files\LibreOffice\program\soffice.com
# PDF_FONTS_DIR=/ruta/a/fuentes/extra
```

Si `ADMIN_PASSWORD` está vacía o es el valor de ejemplo `cambiar_esto_en_produccion`, `/admin/logs` queda **deshabilitado**.

---

## Dividir un PDF

Pestaña **Dividir**. Seis maneras de sacar páginas de un PDF:

| Modo | Qué entrega |
|---|---|
| Un rango | Un PDF con las páginas de la *a* a la *b* |
| Cada página por separado | Un ZIP con una página por archivo |
| Solo las pares / solo las impares | Un PDF con esas páginas |
| **Cada N páginas** | Un ZIP con un archivo cada N páginas (la última puede quedar más corta). Mientras se escribe N, la pantalla dice cuántos archivos saldrán |
| **Grupos personalizados** | Un ZIP con un archivo por grupo, escrito así: `1-2,3-5,6` (páginas 1 y 2 juntas, de la 3 a la 5 juntas, la 6 sola). Se pueden dejar páginas fuera |

Nombres dentro del ZIP: en *Cada N páginas* y *Grupos personalizados* son `nombre_01.pdf`, `nombre_02.pdf`… (el número sigue el orden de los grupos), para renombrarlos con facilidad; en *Cada página por separado* son `pagina_01.pdf`, `pagina_02.pdf`… (con tantos ceros como necesite el total de páginas).

*Cada N páginas* y *Grupos personalizados* entregan como máximo 500 archivos por división; pasado ese tope la pantalla lo avisa y sugiere *Cada página por separado*.

**Ver páginas** (en *Grupos personalizados*): muestra una miniatura de cada página, agrupadas en recuadros, una por documento. Se ajusta con el ratón o el dedo: **cortar** un grupo en dos, **unir** un grupo con el siguiente, **descartar** una página (por ejemplo, la cara en blanco de un documento de 3 hojas escaneado a doble cara) o **reagrupar** cada N páginas. Al abrirla parte de lo que esté escrito en el campo de grupos (o de grupos parejos si está vacío), y cada cambio vuelve a escribir el texto `1-2,3-5,6`; mientras la vista está abierta ese campo queda en solo lectura. Si los grupos escritos estaban en otro orden (por ejemplo `6-7,1-2`), la vista los ordena por página (`1-2,6-7`) y lo avisa: son los mismos archivos, pero cambia cuál es el `_01` y cuál el `_02`, es decir, qué páginas acaban en qué archivo. El texto también se puede escribir directamente, sin abrir la vista. Las miniaturas se dibujan en el navegador con el PDF.js que ya trae la app, sin enviar nada más al servidor.

---

## Editor de PDF

Pestaña **Editar PDF**. El documento se sube una vez y queda en una sesión del servidor con **versiones**: cada cambio guardado crea una versión nueva y el botón **Deshacer** vuelve a la anterior (hasta 30). La sesión se reanuda si se recarga la página y se borra sola tras `EDIT_SESSION_HOURS` sin uso o al pulsar **Cerrar**.

### Modo "Anotar, firmar y páginas" (PDF.js)

Visor de Mozilla PDF.js integrado con sus herramientas de edición:

| Herramienta | Qué hace |
|---|---|
| Texto | Escribe texto nuevo en cualquier parte (color y tamaño) |
| Firma | Firma escrita, dibujada o desde imagen; se puede guardar para reutilizar |
| Dibujar | Trazo libre (firmas a mano, marcas) |
| Imagen | Inserta logos, sellos o fotos |
| Resaltar / Comentarios | Resaltado de texto y notas |
| Formularios | Los campos rellenables se escriben directamente |
| Páginas | Panel lateral → seleccionar → *Administrar*: eliminar, copiar, cortar/mover, exportar selección |

**Guardar cambios** sube el resultado como nueva versión (también ocurre solo al descargar o al cambiar de modo).

### Modo "Editar texto existente" (PyMuPDF)

Clic sobre un texto resaltado, escribir y **Enter** (Esc cancela; vacío + Enter lo borra). Se conserva:

- **la misma fuente**: se busca la familia original instalada en el sistema (Calibri, Arial, Times…); si no está, un equivalente métrico libre (Liberation, Carlito, Caladea, DejaVu) y, en último caso, una fuente base14 — la app avisa cuando usa una aproximada;
- el **tamaño, color y línea base**, también en páginas rotadas;
- **bordes de tablas, fondos de color, subrayados e imágenes** (solo se elimina el texto, sin parche blanco);
- las líneas vecinas aunque el interlineado sea apretado.

Si el texto nuevo no cabe hasta el siguiente texto de la línea, se reduce hasta un 70 % y se avisa. La opción *Al reemplazar* permite mantener el inicio, el final (útil para cifras alineadas a la derecha) o centrar.

Limitaciones: edita una línea a la vez (no reacomoda párrafos); en páginas escaneadas no hay texto real — usa el modo Anotar para escribir encima.

### Descarga

**Aplanar** (activado por defecto) convierte anotaciones, firmas y formularios en contenido fijo de la página para que no se puedan mover ni borrar. Si el PDF tenía contraseña, se pide al abrirlo y el descargado sale sin contraseña (usa la pestaña Proteger después si hace falta).

---

## Conversión PDF → Excel / Word

El PDF → Excel se rehízo tras medir varias alternativas libres con documentos típicos (factura de Word con tabla con bordes, inventario de Excel de varias páginas sin bordes, extracto bancario y la factura escaneada). Detalle en `AUDITORIA_2026-10.md`.

| Tipo de tabla | Motor |
|---|---|
| Con bordes dibujados | PyMuPDF `find_tables` (conserva celdas de varias líneas) |
| Sin bordes (columnas alineadas) | Camelot 2 (`hybrid`) |
| Escaneada (imagen) | OCR Tesseract español/inglés + Camelot; las líneas de la tabla se borran solo para el OCR |

El Excel trae:

- **Resumen**: tablas encontradas, páginas, método usado y avisos (por ejemplo, páginas leídas con OCR).
- **Tabla 1, Tabla 2…**: una hoja por tabla, como *Tabla de Excel* con filtros. Las que continúan en varias páginas se unen y se quitan los encabezados repetidos.
- **Datos**: pares `Etiqueta: valor` fuera de las tablas (NIT, fecha, cliente, total…).
- **Texto**: todo el texto que no está en tablas, por página.

Los valores se convierten a **número, fecha o porcentaje** por columna, detectando si el documento usa `1.234,56` o `1,234.56`. Se quedan como texto los códigos con ceros a la izquierda y las columnas Código/NIT/Lote/Referencia/Cuenta…

PDF → Word usa pdf2docx (conserva diseño); si el PDF es escaneado arma un Word editable con el texto y las tablas leídos por OCR.

## Herramientas libres utilizadas

| Herramienta | Licencia | Uso |
|---|---|---|
| [PDF.js](https://github.com/mozilla/pdf.js) 6.4.299 (Mozilla) | Apache-2.0 | Visor y editor en el navegador (`app/static/pdfjs`, build *legacy* para navegadores no actualizados) |
| [PyMuPDF](https://github.com/pymupdf/PyMuPDF) | AGPL-3.0 | Motor PDF del servidor (unión, división en bloques y grupos, texto, tablas con bordes, compresión, cifrado, aplanado) |
| [Camelot](https://github.com/camelot-dev/camelot) 2 | MIT | Tablas sin bordes y escaneadas en PDF → Excel |
| [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) (español/inglés) | Apache-2.0 | Lectura de PDF escaneados (vía MuPDF) |
| [LibreOffice](https://www.libreoffice.org/) (opcional) | MPL-2.0 | Word/Excel → PDF con fidelidad completa |
| Liberation, Carlito, Caladea, DejaVu | OFL y licencias libres | Fuentes métricamente compatibles en Docker/Linux |
| [Bricolage Grotesque](https://github.com/ateliertriay/bricolage), [Atkinson Hyperlegible Next](https://www.brailleinstitute.org/freefont/) | OFL-1.1 | Tipografías de la interfaz, servidas desde `app/static/fonts` (no dependen de internet) |
| pdf2docx, python-docx, openpyxl, reportlab, Pillow, OpenCV | MIT/MIT/MIT/BSD/HPND/Apache-2.0 | Conversiones |

> La división en bloques (v2.4.0) no añadió ninguna dependencia: usa PyMuPDF, el PDF.js que ya viene incluido (miniaturas) y `zipfile` de la biblioteca estándar de Python.

> PyMuPDF es AGPL: para uso interno no hay obligación adicional; si la app se ofreciera a terceros por red habría que publicar su código fuente.

---

## Estructura del proyecto

```
pdf_tooloffice/
├── run.py                   # Arranque local: python run.py
├── docker-compose.yml       # docker compose up -d --build (contenedor app-web-1)
├── .env                     # Configuración (no versionar)
├── app/
│   ├── __init__.py          # Factory Flask, cabeceras de seguridad, límites
│   ├── routes.py            # Endpoints de unión, división, conversión, compresión, cifrado, admin
│   ├── routes_edicion.py    # API del editor (/api/edicion)
│   ├── services.py          # Procesamiento PDF / Office
│   ├── conversion_excel.py  # PDF → Excel (tablas, datos, OCR) y base del PDF → Word escaneado
│   ├── edicion_texto.py     # Detección y reemplazo de texto conservando la fuente
│   ├── sesiones.py          # Sesiones del editor con versiones y bloqueo
│   ├── database.py          # Logs SQLite
│   ├── cleanup.py           # Limpieza periódica (cada hora)
│   ├── templates/index.html
│   ├── static/css, static/pdfjs (PDF.js)
│   ├── static/js            # main.js, editor.js, grupos.js (lee y valida «1-2,3-5,6»), vista-paginas.js (miniaturas y cortes de Dividir)
│   ├── static/icons         # favicon.ico, icon.svg, apple-touch-icon, íconos 192/512 y manifiesto
│   ├── static/fonts         # tipografías libres de la interfaz (OFL)
│   ├── requirements.txt / requirements-dev.txt
│   └── Dockerfile
├── tests/                   # pytest (159 pruebas; 3 de OCR/Camelot solo corren dentro de Docker)
│   ├── test_division.py, test_grupos_js.py, test_vista_paginas_js.py   # Dividir: servidor y los dos scripts del navegador
└── legacy/                  # versión anterior (no se usa)
```

---

## Endpoints

| Path | Método | Descripción |
|------|--------|-------------|
| `/` | GET | Interfaz web |
| `/health` | GET | Estado y versión |
| `/favicon.ico` | GET | Ícono (también en `static/icons`) |
| `/api/paginas` | POST | Número de páginas |
| `/api/union` | POST | Unir PDFs (`archivos[]`, `nombre_salida`, `comprimir`, `nivel`) |
| `/api/division` | POST | Dividir (`modo`: rango/todas/pares/impares con `inicio`, `fin`; `cada` con `paginas_por_archivo`; `personalizado` con `grupos`, p. ej. `1-2,3-5,6`) |
| `/api/conversion` | POST | `direccion`: pdf-docx, pdf-xlsx, docx-pdf, xlsx-pdf, pdf_a_jpg, imagen_a_pdf |
| `/api/compresion` | POST | `nivel`: baja/media/alta/ultra |
| `/api/cifrado` | POST | Cifrado AES-256 (`contrasena`, `confirmar`) |
| `/api/edicion` | POST | Crea sesión de edición (`archivo`, `contrasena` opcional) |
| `/api/edicion/<id>` | GET / DELETE | Info / cerrar sesión |
| `/api/edicion/<id>/pdf` | GET | PDF actual |
| `/api/edicion/<id>/paginas/<n>/imagen` | GET | PNG de la página (`dpi` 36–220) |
| `/api/edicion/<id>/paginas/<n>/campos` | GET | Textos editables de la página |
| `/api/edicion/<id>/reemplazar` | POST (JSON) | `pagina`, `bbox`, `texto_original`, `texto_nuevo`, `alineacion` |
| `/api/edicion/<id>/version` | POST | Guarda el PDF anotado por el visor |
| `/api/edicion/<id>/deshacer` | POST | Vuelve a la versión anterior |
| `/api/edicion/<id>/descargar` | GET | Descarga (`aplanar=1` fija anotaciones) |
| `/admin/logs` | GET | Logs en HTML (header `X-Admin-Password`) |
| `/admin/logs/export` | GET | Logs en Excel (header `X-Admin-Password`) |

---

## Compresión

| Nivel | Qué hace |
|-------|----------|
| **baja** | Limpieza sin pérdida (objetos huérfanos + deflate) |
| **media** | Sin pérdida + imágenes de más de 300 dpi reducidas a 200 dpi (JPEG 85) |
| **alta** | Sin pérdida + imágenes de más de 170 dpi reducidas a 150 dpi (JPEG 70) |
| **ultra** | Cada página como imagen JPEG en grises a ~94 dpi. Máxima reducción; se pierde el texto seleccionable |

Si el resultado no es menor que el original, se devuelve el original. Las imágenes con transparencia y las bitonales (JBIG2/CCITT, típicas de escáner en blanco y negro) no se tocan.

---

## Conversión Office → PDF

Con LibreOffice instalado (o `SOFFICE_PATH`) Word/Excel se convierten con fidelidad completa (tablas, estilos, saltos de página). Sin LibreOffice se usa un renderizado básico: párrafos, títulos, tablas e imágenes en Word; todas las hojas visibles con valores calculados en Excel.

Windows: instalar LibreOffice desde libreoffice.org o `winget install TheDocumentFoundation.LibreOffice`; la app lo detecta en `Program Files` sin configurar nada.

---

## Seguridad

- Ids de sesión validados (`[0-9a-f]{32}`) antes de construir rutas: sin path traversal.
- `/admin/logs` escapa todo el contenido (los logs contienen entradas de usuario), compara la contraseña en tiempo constante y se deshabilita sin contraseña configurada.
- Errores internos → mensaje genérico; los detalles quedan en el log del servidor.
- Validación real de archivos: estructura PDF con PyMuPDF; DOCX/XLSX por estructura del paquete.
- Texto que empieza por `=` al exportar a Excel se guarda como texto (sin inyección de fórmulas).
- Cabeceras `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`, `Referrer-Policy`.
- Límite de 50 MB con respuesta JSON 413; DPI de render acotado.
- Cifrado AES-256 (antes RC4-128).
- Los documentos del editor se borran tras `EDIT_SESSION_HOURS` sin uso.

Recomendado en producción: HTTPS con proxy inverso y acceso solo desde la red interna.

---

## Pruebas

```bash
pip install -r app/requirements-dev.txt
python -m pytest
```

Cubren edición de texto (fuente, línea base, vecinos, rotación, tamaño de archivo, páginas que comparten fuente), la división en bloques y grupos (incluidos los scripts del navegador, que se prueban con Node cuando está instalado), sesiones (versiones, bloqueo, traversal, expiración), todas las operaciones y la seguridad del panel admin.

---

## Troubleshooting

| Problema | Solución |
|---|---|
| `ImportError: attempted relative import` | Ejecutar `python run.py` desde la raíz del proyecto (no `python app/run.py`) |
| El editor no carga / pantalla en blanco | Navegador muy antiguo: actualizar Chrome/Edge/Firefox |
| "Fuente similar…" al editar texto | La fuente original no está instalada en el equipo que corre la app; instalarla o usar Docker (trae equivalentes libres) |
| Word/Excel → PDF pierde formato | Instalar LibreOffice |
| Puerto en uso | Cambiar `FLASK_PORT` en `.env` |
| `/admin/logs` siempre 401 | Configurar `ADMIN_PASSWORD` en `.env` y enviarla en el header `X-Admin-Password` |

---

## Changelog

### v2.4.0 — 28 Octubre 2026

**Dividir un escaneo de muchos documentos en un solo paso**
- El problema: la impresora de la oficina separa sola una tanda continua en un archivo por documento, pero pierde esa ventaja cuando las hojas son a doble cara. Por eso había que escanear los documentos de uno en uno (50 facturas, 50 escaneos). Ahora se escanean los 50 de corrido en un solo PDF de unas 100 páginas y se corta aquí en 50 archivos.
- **Cada N páginas**: si todos los documentos tienen el mismo largo, se indica N y sale un ZIP con un archivo cada N páginas. La pantalla avisa cuántos archivos saldrán antes de empezar.
- **Grupos personalizados**: para documentos de largos distintos. Se escribe, por ejemplo, `1-2,3-5,6` (el primero con las páginas 1 y 2, el segundo con la 3 a la 5, el tercero con la 6) y sale un ZIP con un archivo por grupo. El texto se puede escribir directamente; el botón *Rellenar cada N páginas* lo llena solo como punto de partida.
- **Ver páginas**: muestra las páginas como miniaturas, en un recuadro por documento, para comprobar a simple vista dónde empieza y termina cada uno. Ahí mismo se corrige con un clic: *cortar* un documento en dos, *unir* uno con el siguiente, *descartar* una página (la cara en blanco de un documento de 3 hojas escaneado a doble cara, por ejemplo) o *reagrupar* todo cada N páginas. El texto de grupos se escribe solo con cada cambio. Con 100 páginas abre al instante: solo dibuja las miniaturas que se están viendo.
- Los archivos del ZIP se llaman `nombre_01.pdf`, `nombre_02.pdf`… para renombrarlos con el número de factura.
- Verificado de 320 a 1440 px de ancho (celular a monitor) sin desbordes, con la vista abierta y cerrada.
- Sin dependencias nuevas: usa PyMuPDF, el PDF.js ya incluido y `zipfile` de Python. Los modos de antes (rango, cada página, pares, impares) no cambian.

### v2.3.1 — 23 Octubre 2026

- Fondo azul con **recuadros claros**: las hojas de pasos, la barra del editor, el visor, el resultado y la tabla de `/admin/logs` son claros con texto oscuro. Cada herramienta tiene un tono fuerte de su color para textos y bordes sobre fondo claro (contraste mínimo 4.7:1).
- Visor PDF.js del editor en tema claro.
- Enlaces directos a cada herramienta: `http://192.168.1.250:3000/#compresion` (también `#union`, `#division`, `#conversion`, `#cifrado`, `#editar`); la dirección cambia al cambiar de pestaña, así se puede guardar como favorito.
- Celulares: las seis pestañas se ven a la vez en dos filas (antes había que deslizarlas). En el editor, la barra de PDF.js pasa a dos filas y deja de recortar Dibujar, Imagen y el menú »; se quita el ancho mínimo de 350 px del visor, que cortaba la página; el panel lateral ya no se abre solo encima del documento y la búsqueda y el diálogo de firma caben en pantalla. Verificado de 320 a 1440 px sin desbordes.
- Corrección: los ajustes del visor (ocultar "Abrir archivo" y "Descargar" de PDF.js) no se aplicaban porque la CSP de `viewer.html` bloquea los `<style>` en línea; ahora van en `static/css/visor.css`.

### v2.3.0 — 23 Octubre 2026

**Interfaz rediseñada en tema oscuro**
- Fondo tinta azul con textos claros (contraste AA o mejor). Cada herramienta tiene el color de un separador de carpeta (Unir azul, Dividir naranja, Convertir turquesa, Comprimir violeta, Proteger rosa, Editar amarillo); la pestaña activa se une al borde de la cabecera y su color tiñe botones, pasos y zonas de carga.
- Cada herramienta se muestra como pasos numerados en una sola hoja; los niveles de compresión explican qué hace cada uno; los campos de rango solo aparecen al dividir por rango.
- Pestañas con nombres de acción (Unir, Dividir, Convertir, Comprimir, Proteger, Editar), navegables con flechas del teclado; foco visible en todos los controles; respeta "reducir movimiento".
- El visor PDF.js del editor abre en tema oscuro; los textos editables se marcan como con resaltador.
- Tipografías Bricolage Grotesque (títulos) y Atkinson Hyperlegible Next (texto, diseñada para máxima legibilidad), alojadas en el propio servidor.
- Favicon nuevo (hoja con separadores de colores) según la guía *How to Favicon* de Evil Martians: `favicon.ico` 32 px, `icon.svg` con variante para modo oscuro, `apple-touch-icon` 180 px, íconos 192/512 y enmascarable, y manifiesto para instalar la app desde Chrome/Edge.
- CSS y JS se sirven con `?v=<fecha del archivo>`: tras desplegar, los navegadores no mezclan la página nueva con estilos viejos en caché.
- Página `/admin/logs` con el mismo tema.

### v2.2.0 — 23 Octubre 2026

**PDF → Excel reescrito** (antes reconstruía 0 % de las filas en facturas con bordes, inventarios y extractos; ahora 100 %, y 80 % en escaneados)
- Motores elegidos por banco de pruebas: PyMuPDF (bordes) + Camelot 2 (sin bordes) + OCR Tesseract (escaneados).
- Una hoja por tabla, tablas multipágina unidas, hojas Datos y Texto (antes se perdía todo lo que no era tabla), hoja Resumen.
- Números, fechas y porcentajes como valores reales con detección de separador decimal; códigos como texto.
- Corregido: el encabezado de la primera tabla se aplicaba a todas y las filas se fusionaban o recortaban para ajustarse a él; la detección por texto de pdfplumber se usaba primero y partía las tablas con bordes.

**PDF → Word**: los PDF escaneados ahora producen texto y tablas editables (antes, solo una imagen).

**Otros**: `docker-compose.yml` movido a la raíz del proyecto (mismo contenedor `app-web-1`); pdfplumber retirado.

### v2.1.0 — 23 Octubre 2026

**Editor de PDF nuevo**
- Visor/editor PDF.js 6.4.299: texto, firmas (escrita, dibujada, imagen), dibujo, imágenes, resaltado, comentarios, formularios y organización de páginas.
- Edición de texto existente rehecha: misma familia de fuente del sistema, línea base exacta, sin borrar líneas vecinas, sin parches blancos sobre fondos, soporte de páginas rotadas, recorte de fuentes (el archivo no crece por cada edición).
- Sesiones con versiones, deshacer, reanudación y expiración; descarga con aplanado.

**Correcciones**
- Path traversal en los endpoints de edición (`edit_id` sin validar).
- XSS almacenado en `/admin/logs`.
- Edición de texto: borraba la línea de abajo con interlineado apretado, borraba bordes de tabla y pintaba un rectángulo blanco; alias de fuente inválidos (`heob`, `hebb`, `coob`, `cobb`) hacían fallar textos en cursiva; recuadros desplazados en páginas rotadas.
- Compresión *ultra*: cambiaba el tamaño de página y perdía la compresión JPEG.
- PDF → Word fallaba con archivos `.PDF` en mayúsculas.
- Word → PDF fallaba con `&` o `<` y omitía todas las tablas.
- Excel → PDF mostraba fórmulas en vez de valores y solo la hoja activa.
- Imágenes → PDF: PNG transparentes salían con fondo negro, fotos de celular giradas, TIFF multipágina solo con la primera página.
- Validación MIME rechazaba DOCX/XLSX válidos generados fuera de Office.
- `python run.py` no funcionaba; `/api/*` devolvía rutas internas en errores 500; 413 devolvía HTML.

**Mejoras**
- PyPDF2 (abandonado) reemplazado por PyMuPDF; cifrado AES-256.
- Compresión media/alta ahora reduce imágenes de alta resolución.
- Conversión Office → PDF con LibreOffice cuando está disponible.
- Suite de 65 pruebas automatizadas; logging estándar; Dockerfile con usuario sin privilegios, fuentes libres y volúmenes corregidos.

### v1.1 — 16 Abril 2026
- Compresión ULTRA, exportación de logs a Excel, corrección de temporales en compresión.

### v1.0 — 13 Abril 2026
- Autenticación de `/admin/logs`, validación de archivos, sanitización de errores, `/health`, rotación de logs.
