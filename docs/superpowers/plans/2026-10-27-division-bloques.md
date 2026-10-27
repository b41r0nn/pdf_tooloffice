# Dividir en bloques de N páginas y grupos personalizados — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Añadir a la pestaña *Dividir* dos modos nuevos — cortar cada N páginas y cortar en grupos definidos por el usuario — con una vista de miniaturas para ajustar los grupos.

**Architecture:** El servidor recibe los grupos como un texto `1-2,3-5,6` y los dos modos nuevos convergen en una sola función que arma el ZIP. El navegador tiene su propia copia del analizador de esa sintaxis (`grupos.js`) para contar archivos y para dibujar la vista; el servidor sigue siendo la autoridad que valida. Las miniaturas se dibujan en el navegador con la PDF.js que ya viene con la aplicación, así que la pestaña sigue sin guardar estado en el servidor.

**Tech Stack:** Flask, PyMuPDF (`pymupdf as fitz`), `zipfile` de la biblioteca estándar, JavaScript sin framework, PDF.js 6.4.299 ya incluido en `app/static/pdfjs/`.

**Spec:** `DISENO_DIVISION_BLOQUES.md` (raíz del proyecto)

## Global Constraints

- **Sin dependencias nuevas.** PyMuPDF, PDF.js y `zipfile` ya están. No se añade nada a `app/requirements.txt`.
- **Español en el código**: nombres de función, variables y comentarios, como el resto del proyecto.
- **Mensajes de error en español dirigidos a quien usa la herramienta.** `ValueError` para lo que es culpa del usuario — `error_response` lo convierte en 400 con el mensaje visible. Cualquier otra excepción es 500 con mensaje genérico.
- **Máximo 500 archivos de salida**, en los dos modos nuevos.
- **Máximo 10 000 caracteres** en el texto de grupos.
- **Sintaxis de grupos:** la coma separa archivos; cada trozo es `a-b` o `a`. Los grupos pueden ir en cualquier orden. Se pueden dejar páginas fuera. Dos grupos no pueden compartir página.
- **Siempre ZIP** en los modos `cada` y `personalizado`, aunque salga un solo archivo. El ZIP se llama `{base}_dividido.zip` y sus entradas `{base}_01.pdf`.
- **Accesibilidad:** los controles son `<button>` de verdad, con `aria-label` que nombra la página. Contraste AA. Foco visible.
- **Responsivo de 320 a 1440 px**, sin desbordes horizontales.
- **`MAX_CONTENT_LENGTH` sigue en 50 MB.** No se toca.
- **La opción marcada por defecto sigue siendo *Un rango*.**
- El modo `rango` que ya existe **no cambia**, ni siquiera su recorte silencioso (`fin = min(fin, total)`).

## Review Focus

Entradas que el diseño da por supuestas y que conviene fijar con una prueba:

1. **Texto pegado con espacios y coma final** (`' 1-2 , 3-5, '`): es lo que sale de copiar y pegar. Debe aceptarse, no fallar. → Tarea 1 y Tarea 3.
2. **Nombre de archivo con separadores de ruta** (`../../factura.pdf`): las entradas del ZIP se construyen con ese nombre por primera vez en el proyecto. No debe salirse de la carpeta. → Tarea 2.
3. **Campos manipulados fuera del formulario** (`paginas_por_archivo` igual a `0`, `-3` o `abc`): el endpoint es público dentro de la red. Debe dar 400 con mensaje, no 500. → Tarea 2.
4. **PDF cifrado en los modos nuevos**: debe dar 400 pidiendo la contraseña, igual que los modos de hoy, no un 500 genérico. → Tarea 2.
5. **Texto de grupos desmesurado** (pegar un documento entero en el campo): debe cortarse por el límite de longitud antes de intentar analizarlo. → Tarea 1.

---

## File Structure

| Archivo | Responsabilidad |
|---|---|
| `app/services.py` *(modificar)* | Analizar la sintaxis, generar los grupos de N páginas y armar el ZIP. Sin Flask. |
| `app/routes.py` *(modificar)* | Los dos modos nuevos dentro de `/api/division`, que ya existe. |
| `app/static/js/grupos.js` *(crear)* | La misma sintaxis en JavaScript: analizar, generar y formatear. Sin DOM, para poder probarla con node. |
| `app/static/js/main.js` *(modificar)* | Enganchar los campos nuevos y el contador en vivo. |
| `app/static/js/vista-paginas.js` *(crear)* | La vista de miniaturas: PDF.js, recuadros por documento, cortar / unir / descartar / reagrupar. |
| `app/templates/index.html` *(modificar)* | Las dos opciones nuevas y el armazón de la vista. |
| `app/static/css/style.css` *(modificar)* | Estilos de los campos nuevos y de la vista. |
| `tests/test_division.py` *(crear)* | El analizador y el generador, probados directamente. |
| `tests/test_routes.py` *(modificar)* | Los dos modos nuevos a través del endpoint, y el contrato del HTML. |
| `tests/test_grupos_js.py` *(crear)* | `grupos.js` ejecutado con node, contra los mismos casos que el Python. |

---

### Task 1: La sintaxis de grupos en Python

**Files:**
- Modify: `app/services.py` (junto a `dividir_pdf_por_modo`, línea 164)
- Test: `tests/test_division.py` (crear)

**Interfaces:**
- Consumes: nada.
- Produces:
  - `MAX_ARCHIVOS_DIVISION = 500`
  - `MAX_TEXTO_GRUPOS = 10_000`
  - `analizar_grupos(texto: str, total: int) -> list[tuple[int, int]]` — páginas en base 1, inclusive, en el orden escrito. Lanza `ValueError` con mensaje para el usuario.
  - `grupos_por_bloques(total: int, paginas_por_archivo: int) -> list[tuple[int, int]]` — lanza `ValueError`.

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
# tests/test_division.py
import pytest

from app.services import analizar_grupos, grupos_por_bloques


def test_analizar_grupos_acepta_tramos_y_paginas_sueltas():
    assert analizar_grupos('1-2,3-5,6', 10) == [(1, 2), (3, 5), (6, 6)]


def test_analizar_grupos_tolera_espacios_y_coma_final():
    assert analizar_grupos(' 1-2 , 3-5, ', 10) == [(1, 2), (3, 5)]


def test_analizar_grupos_respeta_el_orden_escrito():
    assert analizar_grupos('6-7,1-2', 10) == [(6, 7), (1, 2)]


def test_analizar_grupos_permite_dejar_paginas_fuera():
    assert analizar_grupos('1-3,5-6', 10) == [(1, 3), (5, 6)]


def test_analizar_grupos_rechaza_solapamiento_y_nombra_la_pagina():
    with pytest.raises(ValueError, match='4'):
        analizar_grupos('1-4,3-6', 10)


def test_analizar_grupos_rechaza_pagina_fuera_del_documento():
    with pytest.raises(ValueError, match='10'):
        analizar_grupos('1-2,9-12', 10)


def test_analizar_grupos_rechaza_inicio_mayor_que_fin():
    with pytest.raises(ValueError):
        analizar_grupos('5-3', 10)


@pytest.mark.parametrize('texto', ['', '   ', ',', '1-2,hola', '1--2', '0-2', '-3'])
def test_analizar_grupos_rechaza_texto_invalido(texto):
    with pytest.raises(ValueError):
        analizar_grupos(texto, 10)


def test_analizar_grupos_rechaza_mas_de_500_grupos():
    with pytest.raises(ValueError, match='500'):
        analizar_grupos(','.join(str(i) for i in range(1, 502)), 600)


def test_analizar_grupos_corta_el_texto_desmesurado_antes_de_analizarlo():
    with pytest.raises(ValueError, match='largo'):
        analizar_grupos('1-2,' * 5000, 10)


def test_grupos_por_bloques_divide_exacto():
    assert grupos_por_bloques(10, 2) == [(1, 2), (3, 4), (5, 6), (7, 8), (9, 10)]


def test_grupos_por_bloques_deja_el_ultimo_mas_corto():
    assert grupos_por_bloques(10, 3) == [(1, 3), (4, 6), (7, 9), (10, 10)]


def test_grupos_por_bloques_con_n_mayor_que_el_total_da_un_solo_grupo():
    assert grupos_por_bloques(5, 10) == [(1, 5)]


def test_grupos_por_bloques_rechaza_mas_de_500_archivos():
    with pytest.raises(ValueError, match='Cada página por separado'):
        grupos_por_bloques(600, 1)


@pytest.mark.parametrize('n', [0, -3])
def test_grupos_por_bloques_rechaza_n_menor_que_uno(n):
    with pytest.raises(ValueError):
        grupos_por_bloques(10, n)
```

- [ ] **Step 2: Comprobar que fallan**

Run: `python -m pytest tests/test_division.py -q`
Expected: FAIL — `ImportError: cannot import name 'analizar_grupos'`

- [ ] **Step 3: Implementar las dos funciones y las dos constantes en `app/services.py`**

Orden de comprobaciones en `analizar_grupos`, porque los mensajes dependen de cuál salta primero: longitud del texto → texto vacío → formato de cada trozo → límites `1..total` → `inicio <= fin` → número de grupos → solapamiento.

El solapamiento se busca por conjunto de páginas, no comparando vecinos, porque los grupos pueden ir desordenados. El mensaje nombra la primera página repetida.

`grupos_por_bloques` comprueba el tope **antes** de construir la lista, para no armar 10 000 tuplas y luego descartarlas. Su mensaje remite a la opción que ya existe: `'Saldrían {n} archivos, más de los {MAX_ARCHIVOS_DIVISION} permitidos. Usa «Cada página por separado».'`

- [ ] **Step 4: Comprobar que pasan**

Run: `python -m pytest tests/test_division.py -q`
Expected: PASS, 20 pruebas

- [ ] **Step 5: Confirmar**

```bash
git add app/services.py tests/test_division.py
git commit -m "Analizador de la sintaxis de grupos y generador de bloques de N paginas"
```

---

### Task 2: Armar el ZIP y los dos modos del endpoint

**Files:**
- Modify: `app/services.py` (`MODOS_DIVISION`, línea 45; función nueva junto a `dividir_pdf_por_modo`)
- Modify: `app/routes.py` (importaciones línea 22-39; función `division`, línea 269)
- Test: `tests/test_routes.py`

**Interfaces:**
- Consumes: `analizar_grupos`, `grupos_por_bloques`, `MAX_ARCHIVOS_DIVISION` de la Tarea 1. De lo que ya existe: `abrir_pdf(ruta, contrasena='')`, `_guardar(doc, **extra)`, `nombre_base(filename, defecto='documento')`, `entero(nombre, defecto, minimo=None, maximo=None)`, `log_y_enviar(modulo, nombre, tamano, resultado_bytes, nombre_salida, mimetype, detalle=None)`.
- Produces: `dividir_por_grupos(ruta: str, grupos: list[tuple[int, int]], base: str = 'documento') -> bytes` (ZIP). `/api/division` acepta `modo=cada` con `paginas_por_archivo`, y `modo=personalizado` con `grupos`.

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
# tests/test_routes.py — junto a test_division_rango_y_modos

def test_division_cada_entrega_un_archivo_por_bloque(client):
    r = client.post('/api/division', data={'archivo': _archivo(pdf_bytes(paginas=10), 'escaneo.pdf'),
                                           'modo': 'cada', 'paginas_por_archivo': '2'})
    assert r.status_code == 200
    assert r.mimetype == 'application/zip'
    zf = zipfile.ZipFile(io.BytesIO(r.data))
    assert zf.namelist() == [f'escaneo_{i:02d}.pdf' for i in range(1, 6)]
    assert all(fitz.open('pdf', zf.read(n)).page_count == 2 for n in zf.namelist())


def test_division_personalizado_respeta_los_grupos_y_su_orden(client):
    r = client.post('/api/division', data={'archivo': _archivo(pdf_bytes(paginas=10), 'tanda.pdf'),
                                           'modo': 'personalizado', 'grupos': '6-7,1-2,3-5'})
    assert r.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(r.data))
    assert [fitz.open('pdf', zf.read(n)).page_count for n in zf.namelist()] == [2, 2, 3]


def test_division_personalizado_deja_fuera_las_paginas_no_listadas(client):
    r = client.post('/api/division', data={'archivo': _archivo(pdf_bytes(paginas=10), 't.pdf'),
                                           'modo': 'personalizado', 'grupos': '1-3'})
    zf = zipfile.ZipFile(io.BytesIO(r.data))
    assert len(zf.namelist()) == 1
    assert fitz.open('pdf', zf.read(zf.namelist()[0])).page_count == 3


@pytest.mark.parametrize('datos', [
    {'modo': 'cada', 'paginas_por_archivo': '0'},
    {'modo': 'cada', 'paginas_por_archivo': '-3'},
    {'modo': 'cada', 'paginas_por_archivo': 'abc'},
    {'modo': 'cada'},
    {'modo': 'personalizado', 'grupos': '1-4,3-6'},
    {'modo': 'personalizado', 'grupos': '1-2,40-50'},
    {'modo': 'personalizado', 'grupos': ''},
    {'modo': 'personalizado'},
    {'modo': 'inventado'},
])
def test_division_rechaza_entradas_invalidas(client, datos):
    r = client.post('/api/division', data={'archivo': _archivo(pdf_bytes(paginas=10), 'd.pdf'), **datos})
    assert r.status_code == 400
    assert 'error' in r.get_json()


def test_division_cada_con_pdf_cifrado_pide_la_contrasena(client):
    cifrado = client.post('/api/cifrado', data={'archivo': _archivo(pdf_bytes(paginas=4), 'c.pdf'),
                                                'contrasena': 'clave', 'confirmar': 'clave'}).data
    r = client.post('/api/division', data={'archivo': _archivo(cifrado, 'c.pdf'),
                                           'modo': 'cada', 'paginas_por_archivo': '2'})
    assert r.status_code == 400
    assert 'contraseña' in r.get_json()['error']


def test_division_nombre_con_ruta_no_escapa_del_zip(client):
    r = client.post('/api/division', data={'archivo': _archivo(pdf_bytes(paginas=4), '../../factura.pdf'),
                                           'modo': 'cada', 'paginas_por_archivo': '2'})
    nombres = zipfile.ZipFile(io.BytesIO(r.data)).namelist()
    assert nombres == ['factura_01.pdf', 'factura_02.pdf']
    assert not any('..' in n or '/' in n or '\\' in n for n in nombres)
```

- [ ] **Step 2: Comprobar que fallan**

Run: `python -m pytest tests/test_routes.py -q -k "division"`
Expected: FAIL — los modos nuevos caen en `dividir_pdf_por_modo` y dan "Modo de división no soportado"

- [ ] **Step 3: Implementar `dividir_por_grupos` en `app/services.py`**

Abre el PDF una vez y, por cada grupo, copia su tramo a un documento nuevo con `insert_pdf(src, from_page=inicio-1, to_page=fin-1)` y lo escribe en el ZIP con `zipfile.ZIP_DEFLATED`, igual que hace hoy el modo `todas` (líneas 173-181).

Ancho de los ceros: `max(2, len(str(len(grupos))))`, de modo que 5 archivos salen como `_01`…`_05`.

`base` llega ya limpio desde `nombre_base`, que quita rutas con `os.path.basename` y recorta a 120 caracteres; no hace falta volver a sanearlo, pero la prueba lo vigila.

- [ ] **Step 4: Añadir los dos modos en `app/routes.py`**

En `division()`, antes de la rama `else` que llama a `dividir_pdf_por_modo`:

- `modo == 'cada'`: `paginas_por_archivo = entero('paginas_por_archivo', None, minimo=1)`; si es `None`, `ValueError('Indica cuántas páginas va a tener cada archivo')`. Total de páginas con `contar_paginas(ruta)`. Luego `grupos_por_bloques` y `dividir_por_grupos`.
- `modo == 'personalizado'`: `analizar_grupos(request.form.get('grupos', ''), total)` y `dividir_por_grupos`.

Los dos: `nombre_salida = f'{base}_dividido.zip'`, `mimetype = 'application/zip'`.

`detalle` para el log, sin el texto completo de los grupos: `f'modo=cada; paginas_por_archivo={n}; archivos={len(grupos)}'` y `f'modo=personalizado; grupos={len(grupos)}; paginas={total}'`.

Añadir `analizar_grupos`, `grupos_por_bloques` y `dividir_por_grupos` a la lista de importaciones de `.services`, en orden alfabético.

**No** añadir `cada` ni `personalizado` a `MODOS_DIVISION`: esa constante es la lista de modos que atiende `dividir_pdf_por_modo` y su mensaje de error. Ampliar en su lugar ese mensaje para que nombre los seis modos.

- [ ] **Step 5: Comprobar que pasan, y que no se rompió nada**

Run: `python -m pytest -q`
Expected: PASS — las 105 de antes más las nuevas, 3 omitidas

- [ ] **Step 6: Confirmar**

```bash
git add app/services.py app/routes.py tests/test_routes.py
git commit -m "Modos de division cada N paginas y grupos personalizados"
```

---

### Task 3: La misma sintaxis en JavaScript

**Files:**
- Create: `app/static/js/grupos.js`
- Test: `tests/test_grupos_js.py` (crear)

**Interfaces:**
- Consumes: nada.
- Produces, como variables globales del navegador y también como `module.exports` para node:
  - `analizarGrupos(texto, total) -> {grupos: [[ini, fin], …]} | {error: 'mensaje'}`
  - `gruposPorBloques(total, paginasPorArchivo) -> {grupos} | {error}`
  - `formatearGrupos(grupos) -> '1-2,3-5,6'` — un grupo de una página se escribe como una sola cifra.

Las dos primeras **no lanzan excepciones**: devuelven `{error}` porque alimentan un contador que se recalcula a cada tecla. Mismos límites y mismos mensajes que el Python.

- [ ] **Step 1: Escribir la prueba que falla**

```python
# tests/test_grupos_js.py
import json
import os
import shutil
import subprocess

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GRUPOS_JS = os.path.join(RAIZ, 'app', 'static', 'js', 'grupos.js')

GUION = '''
const g = require(process.argv[2]);
const r = [
  g.analizarGrupos('1-2,3-5,6', 10).grupos,
  g.analizarGrupos(' 1-2 , 3-5, ', 10).grupos,
  g.analizarGrupos('6-7,1-2', 10).grupos,
  g.analizarGrupos('1-3,5-6', 10).grupos,
  !!g.analizarGrupos('1-4,3-6', 10).error,
  !!g.analizarGrupos('1-2,9-12', 10).error,
  !!g.analizarGrupos('5-3', 10).error,
  !!g.analizarGrupos('1-2,hola', 10).error,
  !!g.analizarGrupos('   ', 10).error,
  g.gruposPorBloques(10, 2).grupos,
  g.gruposPorBloques(10, 3).grupos,
  g.gruposPorBloques(5, 10).grupos,
  !!g.gruposPorBloques(600, 1).error,
  !!g.gruposPorBloques(10, 0).error,
  g.formatearGrupos([[1, 2], [3, 5], [6, 6]]),
];
console.log(JSON.stringify(r));
'''


@pytest.mark.skipif(not shutil.which('node'), reason='node no está instalado')
def test_grupos_js_coincide_con_el_analizador_de_python(tmp_path):
    guion = tmp_path / 'comprobar.js'
    guion.write_text(GUION, encoding='utf-8')
    salida = subprocess.run(['node', str(guion), GRUPOS_JS],
                            capture_output=True, text=True, timeout=30, check=True)
    assert json.loads(salida.stdout) == [
        [[1, 2], [3, 5], [6, 6]],
        [[1, 2], [3, 5]],
        [[6, 7], [1, 2]],
        [[1, 3], [5, 6]],
        True, True, True, True, True,
        [[1, 2], [3, 4], [5, 6], [7, 8], [9, 10]],
        [[1, 3], [4, 6], [7, 9], [10, 10]],
        [[1, 5]],
        True, True,
        '1-2,3-5,6',
    ]
```

- [ ] **Step 2: Comprobar que falla**

Run: `python -m pytest tests/test_grupos_js.py -q`
Expected: FAIL — `grupos.js` no existe

- [ ] **Step 3: Implementar `app/static/js/grupos.js`**

Mismo orden de comprobaciones que el Python (Tarea 1, paso 3) y los mismos mensajes, para que el usuario lea lo mismo venga de donde venga.

El archivo termina con la cola que lo hace servir en los dos sitios:

```js
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { analizarGrupos, gruposPorBloques, formatearGrupos };
}
```

Un comentario de cabecera explica por qué estas reglas están repetidas en Python y en JavaScript: el servidor valida de verdad, el navegador solo adelanta la cuenta de archivos y dibuja la vista.

- [ ] **Step 4: Comprobar que pasa**

Run: `python -m pytest tests/test_grupos_js.py -q`
Expected: PASS

- [ ] **Step 5: Confirmar**

```bash
git add app/static/js/grupos.js tests/test_grupos_js.py
git commit -m "grupos.js: la sintaxis de grupos en el navegador, con pruebas por node"
```

---

### Task 4: Los campos nuevos en la pestaña Dividir

**Files:**
- Modify: `app/templates/index.html` (panel `#panel-division`, líneas 128-191; scripts al final, línea 544)
- Modify: `app/static/js/main.js` (`updatePreview`, línea 140; el `change` de `modo-div`, línea 52; el click de división, línea 268)
- Modify: `app/static/css/style.css`
- Test: `tests/test_routes.py`

**Interfaces:**
- Consumes: `analizarGrupos`, `gruposPorBloques`, `formatearGrupos` de la Tarea 3. El endpoint de la Tarea 2.
- Produces: `window._totalPaginasDivision` (número o `null`), que la Tarea 5 lee para dibujar. Los identificadores `#div-cada-campos`, `#div-paginas-por-archivo`, `#div-cuenta`, `#div-grupos-campos`, `#div-grupos`, `#div-rellenar-n`, `#div-rellenar`, `#div-grupos-cuenta`, `#div-ver-paginas`.

- [ ] **Step 1: Escribir la prueba que falla**

```python
# tests/test_routes.py

def test_panel_division_ofrece_los_seis_modos(client):
    html = client.get('/').get_data(as_text=True)
    for valor in ('rango', 'todas', 'pares', 'impares', 'cada', 'personalizado'):
        assert f'value="{valor}"' in html
    # Un rango sigue siendo el que viene marcado
    assert re.search(r'id="div-rango"[^>]*\bchecked\b', html)
    assert 'id="div-paginas-por-archivo"' in html and 'value="2"' in html
    assert 'id="div-grupos"' in html and 'id="div-rellenar"' in html
    assert re.search(r'/static/js/grupos\.js\?v=\d+', html)
```

- [ ] **Step 2: Comprobar que falla**

Run: `python -m pytest tests/test_routes.py -q -k "panel_division"`
Expected: FAIL — no existe `value="cada"`

- [ ] **Step 3: Añadir el marcado en `app/templates/index.html`**

Dos `.pill-option` más dentro del `.pill-group` del paso 2, con las etiquetas **Cada N páginas** y **Grupos personalizados**, siguiendo exactamente la forma de las cuatro que ya están. `div-rango` conserva su `checked`.

Después de `#div-rango-campos`, dos bloques hermanos que se muestran y ocultan igual:

- `#div-cada-campos` (`hidden`): un `.form-group` con `<input type="number" id="div-paginas-por-archivo" min="1" value="2" inputmode="numeric">` etiquetado *Páginas por archivo*, y un `<p class="form-hint" id="div-cuenta">` para el recuento en vivo.
- `#div-grupos-campos` (`hidden`): un `<input type="text" id="div-grupos" placeholder="1-2,3-5,6">` etiquetado *Grupos*; una fila con `<input type="number" id="div-rellenar-n" min="1" value="2">` y `<button type="button" id="div-rellenar">Rellenar cada N páginas</button>`; un `<p class="form-hint" id="div-grupos-cuenta">`; y `<button type="button" class="btn-secundario" id="div-ver-paginas">Ver páginas</button>`.

Cargar `grupos.js` **antes** de `main.js` en el pie de la plantilla, con `url_for` como los demás.

Actualizar el `panel-desc` de la pestaña para que nombre los modos nuevos.

- [ ] **Step 4: Enganchar la lógica en `app/static/js/main.js`**

- En `updatePreview`, guardar el total: `window._totalPaginasDivision = d.paginas || null` dentro del `.then`, y ponerlo a `null` en el `.catch` y al empezar. Al llegar, recalcular los dos contadores.
- Ampliar el `change` de `modo-div` (línea 52) para mostrar el bloque que toca de los tres y ocultar los otros dos.
- `#div-paginas-por-archivo` y `#div-grupos`, al escribir, actualizan su `form-hint` llamando a `gruposPorBloques` / `analizarGrupos` con `window._totalPaginasDivision`: *"Saldrán 50 archivos."*, o *"El último archivo tendrá 1 página."* cuando no es exacto, o el mensaje de error que devuelva el analizador. Sin total todavía, el texto queda vacío.
- `#div-rellenar` escribe en `#div-grupos` el `formatearGrupos(gruposPorBloques(total, n).grupos)`.
- En el click de `.btn-process` (línea 268), dos ramas nuevas que añaden `modo` y `paginas_por_archivo` o `grupos` al `FormData`, con la misma forma que las que ya hay. Antes de enviar, si el analizador da `error`, `showToast(error)` y no se envía.

- [ ] **Step 5: Estilos en `app/static/css/style.css`**

`.pill-group` ya reparte seis opciones; comprobar que a 320 px siguen cabiendo. `#div-rellenar` y `#div-ver-paginas` usan los estilos de botón secundario que ya existen, o se añade `.btn-secundario` si no hay.

- [ ] **Step 6: Comprobar**

Run: `python -m pytest -q`
Expected: PASS

Y a mano, con el servidor local (`FLASK_HOST=127.0.0.1 FLASK_PORT=5077 python run.py`): subir un PDF de 10 páginas, elegir *Cada N páginas* con 2 y comprobar que llegan 5 archivos; elegir *Grupos personalizados*, pulsar *Rellenar*, ver `1-2,3-4,5-6,7-8,9-10` y que el contador dice 5 archivos.

- [ ] **Step 7: Confirmar**

```bash
git add app/templates/index.html app/static/js/main.js app/static/css/style.css tests/test_routes.py
git commit -m "Pestana Dividir: campos de cada N paginas y de grupos personalizados"
```

---

### Task 5: La vista de páginas

**Files:**
- Create: `app/static/js/vista-paginas.js`
- Modify: `app/templates/index.html` (armazón de la vista dentro de `#div-grupos-campos`; script al final)
- Modify: `app/static/css/style.css`
- Test: `tests/test_routes.py`

**Interfaces:**
- Consumes: `analizarGrupos`, `formatearGrupos`, `gruposPorBloques` (Tarea 3); `#div-grupos`, `#div-ver-paginas`, `window._totalPaginasDivision` (Tarea 4).
- Produces: nada que consuma otra tarea.

- [ ] **Step 1: Escribir la prueba que falla**

```python
# tests/test_routes.py

def test_vista_de_paginas_recibe_las_rutas_de_pdfjs(client):
    # vista-paginas.js no puede usar url_for: las rutas llegan por data-… con su ?v=
    html = client.get('/').get_data(as_text=True)
    m = re.search(r'id="div-vista"[^>]*data-pdfjs="(/static/pdfjs/build/pdf\.mjs\?v=\d+)"'
                  r'[^>]*data-worker="(/static/pdfjs/build/pdf\.worker\.mjs\?v=\d+)"', html)
    assert m
    for ruta in m.groups():
        r = client.get(ruta)
        assert r.status_code == 200 and r.mimetype == 'text/javascript'
        r.close()
    assert re.search(r'/static/js/vista-paginas\.js\?v=\d+', html)
```

- [ ] **Step 2: Comprobar que falla**

Run: `python -m pytest tests/test_routes.py -q -k "vista_de_paginas"`
Expected: FAIL — no existe `id="div-vista"`

- [ ] **Step 3: Añadir el armazón en `app/templates/index.html`**

Dentro de `#div-grupos-campos`, después del botón *Ver páginas*:

```html
<div id="div-vista" class="vista-paginas" hidden
     data-pdfjs="{{ url_for('static', filename='pdfjs/build/pdf.mjs') }}"
     data-worker="{{ url_for('static', filename='pdfjs/build/pdf.worker.mjs') }}">
  <div class="vista-barra">
    <span id="vista-resumen" role="status"></span>
    <label for="vista-n">Reagrupar cada</label>
    <input type="number" id="vista-n" min="1">
    <button type="button" id="vista-reagrupar">Reagrupar</button>
    <button type="button" id="vista-cerrar">Cerrar</button>
  </div>
  <div id="vista-grupos"></div>
</div>
```

Cargar `vista-paginas.js` al final, después de `main.js`.

- [ ] **Step 4: Implementar `app/static/js/vista-paginas.js`**

Estado interno: el total de páginas, un `Set` de páginas descartadas y un `Set` de los puntos de corte (la página tras la cual se corta). De ahí se derivan los grupos; nunca al revés. Así cortar, unir y descartar son tres operaciones sobre dos conjuntos, y el dibujo siempre refleja el estado.

- **Abrir:** al pulsar *Ver páginas*, copiar el valor de `#div-rellenar-n` a `#vista-n` — hay un solo número de reagrupar, el de la vista es el mismo campo trasladado — y leer `#div-grupos` con `analizarGrupos`. Si da `error`, `showToast` y no abrir. Si está vacío, sembrar con `gruposPorBloques(total, n)`. Pasar los grupos al estado interno: los cortes son los finales de cada grupo salvo el último, y las páginas que no aparecen en ningún grupo empiezan descartadas. Poner `#div-grupos` en `readOnly = true` y quitarlo al cerrar.
- **PDF.js:** `const { getDocument, GlobalWorkerOptions } = await import(vista.dataset.pdfjs)`, luego `GlobalWorkerOptions.workerSrc = vista.dataset.worker`. El `File` se lee con `arrayBuffer()` desde el `.file-item` del panel. Si lanza `PasswordException`, mostrar el mismo mensaje que da el servidor y cerrar la vista.
- **Dibujo:** un `<section class="vista-grupo">` por grupo, con cabecera *Documento N · X páginas* y un `<button>` *Unir con el siguiente* (ausente en el último). Dentro, un `<figure class="vista-pagina">` por página con su `<canvas>`, el número y un `<button>` *Descartar*. Entre dos páginas del mismo grupo, un `<button>` con `✂` y `aria-label="Cortar después de la página N"`. Las descartadas llevan la clase `apagada` y su botón pasa a *Recuperar*.
- **Miniaturas perezosas:** un `IntersectionObserver` sobre los `<canvas>`; al entrar en pantalla, `page.render` a escala calculada para ~120 px de ancho. Cada página se dibuja una sola vez; guardar el resultado para que redibujar los grupos no vuelva a renderizar.
- **Cada acción** recalcula los grupos, redibuja, escribe `formatearGrupos(...)` en `#div-grupos` y actualiza `#vista-resumen` con *"N documentos · M páginas"*. Tras cortar o unir, devolver el foco al botón equivalente del nodo nuevo.
- **Reagrupar** vacía los cortes y los vuelve a sembrar con `gruposPorBloques`; **no** toca las descartadas.

Si todas las páginas quedan descartadas, `#div-grupos` queda vacío y el resumen avisa; el botón de dividir ya lo rechaza por el camino de la Tarea 4.

- [ ] **Step 5: Estilos en `app/static/css/style.css`**

`.vista-grupo` es un recuadro con el borde en `var(--marca)` y cabecera propia; `.vista-pagina` lleva el `<canvas>` sobre fondo blanco con sombra suave. Las páginas van en `flex` con `flex-wrap`, para que a 320 px bajen de línea en vez de desbordarse. `.apagada` baja la opacidad y tacha el número. Respetar `prefers-reduced-motion`, como el resto de la hoja.

- [ ] **Step 6: Comprobar**

Run: `python -m pytest -q`
Expected: PASS

A mano, con un PDF de 10 páginas: abrir la vista, ver 5 recuadros de 2; cortar dentro del tercero y comprobar que `#div-grupos` pasa a `1-2,3-4,5,6,7-8,9-10`; unir el primero con el segundo y que quede `1-4`; descartar la página 10 y que el último grupo pase a `9`; *Reagrupar* y que vuelva a `1-2,…` conservando la 10 descartada; dividir y comprobar que el ZIP coincide con lo que mostraba la vista.

Comprobar también el ancho: a 320 px no debe haber desbordes.

- [ ] **Step 7: Confirmar**

```bash
git add app/static/js/vista-paginas.js app/templates/index.html app/static/css/style.css tests/test_routes.py
git commit -m "Vista de paginas para ajustar los grupos de la division"
```

---

### Task 6: Cierre

**Files:**
- Modify: `app/__init__.py` (línea 11)
- Modify: `README.md`
- Test: `tests/test_routes.py`

- [ ] **Step 1: Subir la versión a 2.4.0**

`__version__ = '2.4.0'` en `app/__init__.py`. `test_index_usa_rutas_estaticas_y_version` ya comprueba que la versión sale en el HTML.

- [ ] **Step 2: README**

Entrada de changelog para v2.4.0 contando los dos modos, la vista y para qué sirve (escanear la tanda de corrido en vez de documento a documento). Actualizar la descripción de la pestaña *Dividir*, el número de pruebas y la estructura de carpetas con `grupos.js`, `vista-paginas.js` y los dos archivos de pruebas nuevos.

- [ ] **Step 3: Repaso de anchos**

Con el servidor local, comprobar de 320 a 1440 px que la pestaña *Dividir* no desborda en ninguno de los seis modos, con la vista abierta y cerrada.

- [ ] **Step 4: Comprobar todo**

Run: `python -m pytest -q`
Expected: PASS

- [ ] **Step 5: Confirmar**

```bash
git add app/__init__.py README.md
git commit -m "Version 2.4.0: division en bloques y grupos personalizados"
```

---

## Pendiente después de entregar

Medir con una tanda real escaneada (§12 del diseño): tamaño del PDF frente al límite de 50 MB y memoria del contenedor al armar el ZIP. Ese archivo lo aporta quien usa la impresora; hasta que llegue, los dos riesgos siguen abiertos.
