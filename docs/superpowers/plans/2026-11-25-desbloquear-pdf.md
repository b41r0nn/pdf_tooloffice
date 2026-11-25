# Quitar la contraseña de un PDF · plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Añadir al módulo *Proteger* un modo que quita la contraseña y las restricciones de un PDF, sin tocar su contenido ni el archivo original.

**Architecture:** Un servicio nuevo (`desbloquear_pdf`) que abre el PDF con la contraseña del usuario, lo guarda con `encryption=PDF_ENCRYPT_NONE` y comprueba su propio resultado antes de devolverlo; un endpoint nuevo `/api/desbloqueo` que lo expone; y en el panel de *Proteger* dos pastillas de modo que cambian el paso de la contraseña y el endpoint al que manda `procesarTanda`.

**Tech Stack:** Flask, PyMuPDF 1.24.14, JavaScript clásico sin dependencias, pytest, node para las pruebas de JS.

**Spec:** `docs/superpowers/specs/2026-11-25-desbloquear-pdf-design.md`

## Global Constraints

- **Sin dependencias nuevas**: PyMuPDF, PDF.js ya incluido, LibreOffice y la biblioteca estándar. Añadir algo a `app/requirements.txt` es decisión del dueño.
- **Español** en nombres de función, variables, comentarios y mensajes.
- **`ValueError` = culpa del usuario** → 400 con el mensaje visible tal cual; cualquier otra excepción → 500 genérico.
- **La contraseña nunca se registra**: ni en el log de SQLite, ni en los logs del servidor, ni en el mensaje de error.
- Scripts del navegador con **ámbito global compartido**: un `const` repetido de nivel superior mata la página entera.
- **Accesibilidad**: las pastillas son `input[type=radio]` con su `label`; el campo de contraseña con etiqueta; nada comunicado solo por color.
- **Responsivo de 320 a 1440 px** sin desbordes, verificado en el navegador.
- **Finales de línea LF**. Para comprobarlo, `git ls-files --eol` (no `grep -c $'\r'`).
- Datos de PyMuPDF ya verificados, que el código debe dar por ciertos:
  - PDF sin cifrar → `needs_pass=0`, `permissions=-4`.
  - PDF con contraseña de apertura → `needs_pass=1`; `authenticate(clave)` devuelve 0 si falla.
  - **PDF con solo contraseña de dueño → `needs_pass=0` y `is_encrypted=False`, pero `permissions` restringido.** `is_encrypted` NO sirve para detectar restricciones.
  - `PERMISOS_COMPLETOS = 3900` (los 8 bits `PDF_PERM_*`). Restringido es `(permissions & 3900) != 3900`.
  - Guardar sin `encryption=` **conserva** el cifrado (`PDF_ENCRYPT_KEEP`).

## Review Focus

- **PDF escaneado, sin texto extraíble**: la comprobación del resultado no puede exigir texto; un PDF de imágenes debe desbloquearse igual. → Task 1.
- **Contraseña vacía en un PDF que la pide**: mensaje de contraseña incorrecta, nunca un error técnico ni un 500. → Task 1.
- **Contraseña con tildes, espacios o mayúsculas**: se usa tal cual, sin recortar ni normalizar. → Task 1.
- **La contraseña en los registros**: el detalle del log y el mensaje de error no pueden contenerla. → Task 2.
- **PDF de muchas páginas**: la comprobación del resultado no puede tardar más que el propio desbloqueo. → Task 1.

---

### Task 1: El servicio `desbloquear_pdf`

**Files:**
- Modify: `app/services.py` (sección Cifrado, junto a `cifrar_pdf:752`)
- Test: `tests/test_desbloqueo.py` (crear)

**Interfaces:**
- Consumes: `abrir_pdf(ruta, contrasena='')` y `validar_pdf(ruta)` de `app/services.py`.
- Produces:
  - `PERMISOS_COMPLETOS = 3900`
  - `tiene_restricciones(doc) -> bool`
  - `desbloquear_pdf(ruta_pdf, contrasena='', quitar_restricciones=False) -> bytes`

- [ ] **Step 1: Escribir las pruebas que fallan**

En `tests/test_desbloqueo.py`, con ayudantes propios que generen los tres tipos de PDF (sin cifrar; con `user_pw`; con solo `owner_pw` y `permissions=int(fitz.PDF_PERM_ACCESSIBILITY)`):

```python
def test_con_la_contrasena_correcta_el_pdf_sale_sin_contrasena()
    # abre el resultado: needs_pass == 0 y permissions == -4

def test_el_contenido_y_las_paginas_se_conservan()
    # mismo page_count y mismo texto por página que el original

def test_los_metadatos_se_conservan()
    # title "Titulo original" y author "REDIHOS" siguen ahí

def test_la_contrasena_incorrecta_avisa_sin_tocar_nada()
    # ValueError que contiene "contraseña" y NO contiene la clave probada

def test_la_contrasena_vacia_en_un_pdf_que_la_pide_da_el_mismo_aviso()

def test_la_contrasena_con_tildes_y_espacios_funciona_tal_cual()
    # clave " Ñandú 2026 " cifra y desbloquea sin recortar

def test_un_pdf_sin_proteccion_dice_que_no_hay_nada_que_quitar()
    # ValueError con "no hay nada que quitar"

def test_un_pdf_solo_restringido_no_se_toca_si_no_se_pide()
    # quitar_restricciones=False -> ValueError que nombra las restricciones

def test_un_pdf_solo_restringido_se_libera_si_se_pide()
    # quitar_restricciones=True -> permissions == -4 y needs_pass == 0

def test_un_pdf_escaneado_sin_texto_se_desbloquea_igual()
    # PDF de una imagen sin texto: no falla la comprobación del resultado

def test_un_pdf_de_muchas_paginas_se_desbloquea_en_un_tiempo_razonable()
    # 200 páginas, con tope de tiempo holgado (p. ej. < 20 s)

def test_el_archivo_original_no_cambia()
    # hash del archivo en disco antes y después
```

- [ ] **Step 2: Correr las pruebas y ver que fallan**

Run: `python -m pytest tests/test_desbloqueo.py -q`
Expected: FAIL con `AttributeError: module 'app.services' has no attribute 'desbloquear_pdf'`

- [ ] **Step 3: Implementar en `app/services.py`**

- `PERMISOS_COMPLETOS`: el OR de los 8 `fitz.PDF_PERM_*`.
- `tiene_restricciones(doc)`: `(doc.permissions & PERMISOS_COMPLETOS) != PERMISOS_COMPLETOS`.
- `desbloquear_pdf(ruta_pdf, contrasena='', quitar_restricciones=False) -> bytes`:
  1. `validar_pdf`; si no es válido, `ValueError` con su mensaje.
  2. Abrir con `fitz.open`. Si `needs_pass` y `authenticate(contrasena)` devuelve 0 →
     `ValueError('La contraseña no es correcta. Escribe la contraseña con la que se abre este PDF.')`
     (el mensaje no incluye la contraseña).
  3. Si no pedía contraseña: sin restricciones → `ValueError('Este PDF no tiene contraseña ni restricciones: no hay nada que quitar.')`; con restricciones y `quitar_restricciones=False` → `ValueError('Este PDF se abre sin contraseña pero no deja imprimir ni copiar. Marca «Quitar también las restricciones» para quitárselas.')`
  4. Guardar con `doc.tobytes(encryption=fitz.PDF_ENCRYPT_NONE)`, **sin** `garbage` ni `deflate` (fidelidad antes que tamaño; por eso no usa `_guardar`).
  5. Comprobar el resultado antes de devolverlo con el ayudante del paso siguiente.

- [ ] **Step 4: Implementar la comprobación del resultado**

`_comprobar_desbloqueo(datos, doc_original) -> None`, privada, que reabre `datos` y exige:
`needs_pass == 0`, mismo `page_count`, y el **texto de cada página igual** al del original. El texto vacío es válido (un escaneado no tiene texto): lo que se compara es la igualdad, no la presencia. Si algo no cuadra, `ValueError('El PDF se desbloqueó pero el resultado no coincide con el original, así que no se entrega. Avisa a Sistemas con el nombre del archivo.')`

- [ ] **Step 5: Correr las pruebas y ver que pasan**

Run: `python -m pytest tests/test_desbloqueo.py -q`
Expected: PASS (12 pruebas)

- [ ] **Step 6: Correr la suite completa**

Run: `python -m pytest -q`
Expected: PASS, sin regresiones (201 + las nuevas)

- [ ] **Step 7: Commit**

```bash
git add app/services.py tests/test_desbloqueo.py
git commit -m "Desbloquear un PDF: quitar cifrado y restricciones conservando el contenido"
```

---

### Task 2: El endpoint `/api/desbloqueo`

**Files:**
- Modify: `app/routes.py` (sección Cifrado, junto a `cifrado():498`)
- Test: `tests/test_desbloqueo.py` (añadir la sección del endpoint)

**Interfaces:**
- Consumes: `desbloquear_pdf` de Task 1; `recibir_pdf()`, `nombre_base()`, `log_y_enviar()`, `error_response()`, `eliminar_temporales()` de `app/routes.py`.
- Produces: `POST /api/desbloqueo` con campos `archivo`, `contrasena` (opcional), `quitar_restricciones` (`'true'`/ausente). Devuelve `<base>_sin_contrasena.pdf` con `application/pdf`.

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
def test_desbloqueo_devuelve_un_pdf_que_abre_sin_contrasena(client)
    # 200, mimetype application/pdf, needs_pass == 0, nombre "_sin_contrasena.pdf"

def test_desbloqueo_con_contrasena_mala_da_400_con_mensaje_claro(client)
    # 400 y 'contraseña' en r.json['error']

def test_desbloqueo_sin_archivo_da_400(client)

def test_desbloqueo_de_un_pdf_restringido_necesita_la_casilla(client)
    # sin quitar_restricciones -> 400; con quitar_restricciones='true' -> 200

def test_el_log_no_guarda_la_contrasena(client)
    # tras un desbloqueo correcto y uno fallido, ninguna fila de logs contiene la clave
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `python -m pytest tests/test_desbloqueo.py -q`
Expected: FAIL solo en las pruebas nuevas, con 404 en `/api/desbloqueo`

- [ ] **Step 3: Implementar el endpoint en `app/routes.py`**

`@bp.route('/api/desbloqueo', methods=['POST'])` → `def desbloqueo():` con el mismo patrón que `cifrado()`: `recibir_pdf()`, llamada a `desbloquear_pdf`, `log_y_enviar('desbloqueo', nombre, tamano, resultado, f'{nombre_base(nombre)}_sin_contrasena.pdf', MIMETYPES['pdf'], detalle=...)`, `error_response` y `eliminar_temporales` en el `finally`. El `detalle` dice si se pidió quitar restricciones y el tamaño, **nunca** la contraseña.

- [ ] **Step 4: Correr las pruebas del endpoint y la suite**

Run: `python -m pytest tests/test_desbloqueo.py -q` y `python -m pytest -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/routes.py tests/test_desbloqueo.py
git commit -m "Endpoint /api/desbloqueo para quitar la contraseña de un PDF"
```

---

### Task 3: Los dos modos en el panel Proteger

**Files:**
- Modify: `app/templates/index.html:425-500` (panel `#panel-cifrado`)
- Modify: `app/static/js/main.js:682-696` (manejador de Cifrado)
- Test: `tests/test_desbloqueo_ui.py` (crear)

**Interfaces:**
- Consumes: `/api/desbloqueo` de Task 2; `procesarTanda(panel, endpoint, formDataDe, {baseZip})` de `main.js`.
- Produces: los identificadores que las pruebas fijan: `cif-modo-poner`, `cif-modo-quitar` (radios `name="cif-modo"`), `cif-pass-actual`, `cif-restricciones`, y los pasos `#paso-poner` y `#paso-quitar` que se esconden con `hidden`.

- [ ] **Step 1: Escribir las pruebas de la pantalla que fallan**

```python
def test_el_panel_proteger_ofrece_los_dos_modos(client)
    # radios cif-modo-poner (checked) y cif-modo-quitar, ambos con <label for=...>

def test_el_paso_de_quitar_viene_escondido(client)
    # #paso-quitar tiene hidden; #paso-poner no

def test_el_modo_quitar_tiene_un_solo_campo_de_contrasena(client)
    # dentro de #paso-quitar hay exactamente un input[type=password]: cif-pass-actual

def test_la_casilla_de_restricciones_viene_desmarcada(client)
    # cif-restricciones sin 'checked'

def test_la_pantalla_explica_que_la_contrasena_puede_ir_vacia(client)
    # el paso de quitar menciona que se deja vacío si el PDF abre sin pedirla
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `python -m pytest tests/test_desbloqueo_ui.py -q`
Expected: FAIL (los identificadores no existen)

- [ ] **Step 3: Añadir las pastillas y el paso de quitar en `index.html`**

Un `<div class="pill-group" role="radiogroup" aria-label="Qué hacer con la contraseña">` como primer paso del panel, con los dos radios. El paso actual de las dos contraseñas pasa a `<li class="card paso" id="paso-poner">`; se añade `<li class="card paso" id="paso-quitar" hidden>` con el campo `cif-pass-actual` (etiqueta *Contraseña actual*, nota de que se deja vacío si el PDF se abre sin pedirla) y la casilla `cif-restricciones` (*Quitar también las restricciones de impresión y copia*). La casilla del ZIP y la lista de archivos no se mueven.

- [ ] **Step 4: Conmutar el modo y mandar al endpoint que toca en `main.js`**

Un manejador del `change` de `input[name="cif-modo"]` que alterna el `hidden` de los dos pasos y el texto del botón (*Proteger PDF* / *Quitar contraseña*). El manejador del botón, según el modo: en *poner*, lo de hoy (valida que las dos contraseñas coincidan) contra `/api/cifrado`; en *quitar*, `procesarTanda(panel, '/api/desbloqueo', ...)` con `contrasena` y `quitar_restricciones`, y `baseZip: 'sin_contrasena'`. En modo quitar **no** se exige contraseña antes de enviar: un PDF solo restringido no tiene ninguna.

- [ ] **Step 5: Correr las pruebas de la pantalla y la suite**

Run: `python -m pytest tests/test_desbloqueo_ui.py -q` y `python -m pytest -q`
Expected: PASS

- [ ] **Step 6: Verificar en el navegador de verdad**

Levantar `FLASK_HOST=127.0.0.1 FLASK_PORT=5077 python run.py` y manejar Chrome headless por CDP (ver las siete trampas en `CLAUDE.md`, incluida la del objetivo `page`). Comprobar, con PDF generados al momento: (1) modo quitar con la contraseña correcta descarga un PDF que abre sin pedirla; (2) con la contraseña mala sale el aviso y no hay descarga; (3) un PDF solo restringido avisa de la casilla, y marcándola se descarga; (4) una tanda de 3 PDF cifrados con la misma clave, sueltos y en ZIP; (5) volver al modo poner sigue protegiendo como antes; (6) sin desbordes a 320, 768 y 1440 px.

- [ ] **Step 7: Commit**

```bash
git add app/templates/index.html app/static/js/main.js tests/test_desbloqueo_ui.py
git commit -m "Proteger: pastillas para poner o quitar la contraseña"
```

---

### Task 4: Versión 2.6.0 y documentación

**Files:**
- Modify: `app/__init__.py:11` (`__version__`)
- Modify: `README.md` (cabecera, Endpoints, Changelog, Estructura)
- Modify: `CLAUDE.md` (sección de trampas)

- [ ] **Step 1: Subir la versión a 2.6.0 y comprobar que la pantalla la muestra**

Run: `python -m pytest tests/test_routes.py -q -k version`
Expected: PASS

- [ ] **Step 2: Documentar**

- `README.md`: versión y fecha; `/api/desbloqueo` en la tabla de endpoints; entrada del changelog **v2.6.0** contando el caso real (un PDF propio cuya contraseña se conoce, que queda listo para usar) y lo que NO hace (no adivina contraseñas, no toca Excel ni Word); `tests/test_desbloqueo*.py` en la estructura.
- `CLAUDE.md`, en Trampas: **`is_encrypted` es `False` en un PDF con solo contraseña de dueño**, así que las restricciones se detectan comparando `doc.permissions` con `PERMISOS_COMPLETOS` (3900); y guardar sin `encryption=` conserva el cifrado.

- [ ] **Step 3: Suite completa y finales de línea**

Run: `python -m pytest -q` y `git ls-files --eol tests/test_desbloqueo.py`
Expected: PASS y `i/lf w/lf`

- [ ] **Step 4: Commit**

```bash
git add app/__init__.py README.md CLAUDE.md
git commit -m "Version 2.6.0: documentacion del desbloqueo de PDF"
```
