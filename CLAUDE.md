# PDF ToolOffice — notas para trabajar en este proyecto

Herramienta web de PDF para la oficina de REDIHOS. **La usan personas no técnicas desde
la red interna**, no desarrolladores. Todo lo que ve el usuario va en español y escrito
para alguien que no sabe lo que es un endpoint.

El `README.md` explica qué hace la aplicación. Este archivo explica cómo trabajar en ella.

---

## Reglas que no se negocian

- **Español** en nombres de función, variables, comentarios y mensajes.
- **`ValueError` = culpa del usuario** → `error_response` lo convierte en 400 con el
  mensaje visible tal cual. Cualquier otra excepción → 500 con texto genérico. Si lanzas
  `ValueError`, su mensaje se le enseña a una persona: escríbelo para ella.
- **Sin dependencias nuevas.** PyMuPDF, PDF.js (ya incluido en `app/static/pdfjs`),
  LibreOffice y la biblioteca estándar. Añadir algo a `app/requirements.txt` es una
  decisión del dueño, no una conveniencia.
- **Nunca** `Co-Authored-By`, "Generated with Claude Code" ni menciones a Claude o a una
  IA en commits ni en PR. Regla permanente del dueño.
- **Finales de línea LF**, forzado en `.gitattributes`. El contenedor corre en Linux y con
  CRLF el Dockerfile falla.
- **Accesibilidad:** controles que son `<button>` de verdad, `aria-label` que nombra lo que
  afecta, foco visible, contraste AA. Nada comunicado solo por color.
- **Responsivo de 320 a 1440 px** sin desbordes horizontales. Se verifica, no se supone.

## Comandos

```bash
python -m pytest -q                                    # suite completa
python -m pytest tests/test_division.py -v             # un archivo
FLASK_HOST=127.0.0.1 FLASK_PORT=5077 python run.py     # servidor local
```

Las pruebas de JavaScript corren **node desde pytest** (`tests/test_grupos_js.py`,
`tests/test_vista_paginas_js.py`); se omiten solas si no hay node. Las de OCR y Camelot se
omiten fuera de Docker: 3 omitidas es lo normal en Windows.

## Despliegue — NO es `git push`

Producción es el contenedor `pdf_tooloffice` en **192.168.1.250:3000**, desde
`~/pdf_tooloffice` en el servidor. **Esa carpeta no es un repositorio**: se copia por tar.
Acceso por `ssh sysadmin-prod` (llave, nunca contraseña).

1. `tar -czf` excluyendo `.git`, `.superpowers`, `.venv*`, `legacy`, `__pycache__`,
   `app/uploads/*`, `app/database/*`, `.env`, `test_edit*`, `.pytest_cache`
2. `scp` a `sysadmin-prod:~/pdf.tgz`
3. **Etiquetar la imagen actual como punto de retorno**: `docker tag pdf_tooloffice:latest pdf_tooloffice:<versión anterior>`
4. Extraer y `docker build -t pdf_tooloffice:<nueva> ./app`
5. **Probar en un contenedor aparte** en `127.0.0.1:3058` antes de tocar nada
6. Solo entonces: retag a `latest` + `docker compose -f docker-compose.prod.yml up -d`
7. Verificar por la red y borrar `~/pdf.tgz`

**Nunca copiar el `.env` del PC al servidor**: el del servidor tiene su propia contraseña.
Volver atrás = retag de la imagen anterior a `latest` y `compose up -d`.

## Arquitectura, lo que no se deduce leyendo

**Los scripts del navegador son scripts clásicos que comparten un único ámbito global.**
`grupos.js`, `main.js`, `editor.js` y `vista-paginas.js` se cargan con `<script src>`. Un
`const` de nivel superior repetido entre dos de ellos es un `SyntaxError` que **mata la
página entera**, no solo esa función. `vista-paginas.js` se envuelve en una IIFE y no
expone nada; imita eso. Hay una prueba que fija que `grupos.js` carga antes que `main.js`.

**La sintaxis de grupos (`1-2,3-5,6`) está escrita dos veces a propósito**, en
`app/services.py` y en `app/static/js/grupos.js`. El servidor es la autoridad; el navegador
solo adelanta la cuenta de archivos. **Si tocas una, tienes que tocar la otra**: tres redes
de pruebas de paridad lo exigen, incluida una que recorre los 63 488 caracteres del plano
básico comprobando que ambas recortan los mismos espacios.

**La vista de páginas deriva los grupos de dos conjuntos** (páginas descartadas y puntos de
corte) y nunca los guarda. Cortar, unir y descartar son operaciones sobre esos conjuntos.
El invariante que sostiene todo: **la vista y el campo de texto no pueden discrepar**,
porque el servidor actúa sobre el texto. `refrescar()` es el único que escribe el campo.

## Trampas que ya nos costaron tiempo

**PDF.js 6.4.299**
- `PDFDocumentProxy.destroy()` **no existe**. Es `loadingTask.destroy()`.
- `viewer.html` trae una CSP con `style-src 'self'`: los `<style>` en línea se bloquean
  en silencio. Los ajustes al visor van en `static/css/visor.css`, enlazado.
- `#mainContainer` tiene `min-width: 350px`, que rompe el móvil. Se anula en `visor.css`.
- `viewerCssTheme`: 1 = claro, 2 = oscuro.

**Python / Flask**
- `int()` sobre más de 4300 dígitos lanza el `ValueError` propio de CPython **en inglés**,
  y `error_response` se lo enseña al usuario. Acota los dígitos en la expresión regular.
- `str.strip()` y `trim()` de JS recortan conjuntos **distintos** (el BOM, `\x1c-\x1f`,
  `\x85`). Hay un conjunto explícito compartido en `services.py` y `grupos.js`: van en pareja.
- `?v=<mtime>` se añade solo a las URLs estáticas (`url_defaults` en `__init__.py`), menos
  a `fonts/`. El JS no puede escribir rutas a mano: llegan desde la plantilla en `data-…`.

**CSS**
- `var()` dentro de una propiedad personalizada se resuelve **donde se declara**. Por eso
  `--marca: var(--acento)` va en `body` y no en `:root`.

## Si vas a verificar algo en el navegador

Chrome headless por CDP con Node (que ya trae `WebSocket`). **Cinco errores de medición
reales en una sola sesión, todos atribuidos primero a la aplicación y ninguno cierto:**

1. **Navegar a la misma URL con el mismo `#hash` NO recarga la página.** El DOM sobrevive
   entre vueltas y los conmutadores alternan. Añade una consulta única por iteración.
2. **`canvas.width > 0` es cierto para un lienzo vacío** (mide 300×150 por defecto). Usa la
   marca que pone el propio código: `canvas[data-listo]`.
3. **Buscar un botón por el final de su `aria-label`** casa con varios: "Cortar después de
   la página 5" y "Descartar la página 5" acaban igual. Compara la etiqueta completa.
4. **`const` repetido entre dos `Runtime.evaluate`** en la misma página lanza `SyntaxError`
   y la acción no ocurre. Envuelve cada evaluación en una IIFE.
5. **`Page.captureScreenshot` con `captureBeyondViewport` se cuelga** si hay lienzos de
   PDF.js. Usa ventana alta y captura solo el viewport.

Y la regla de fondo: **comprueba la herramienta de medición antes de acusar al código.**

## Documentos del proyecto

| Archivo | Qué es |
|---|---|
| `README.md` | **Al día.** Qué hace y cómo se despliega |
| `CLAUDE.md` | Este archivo: cómo trabajar aquí |
| `DISENO_DIVISION_BLOQUES.md` | Diseño de la división en bloques (v2.4.0), con las decisiones y por qué |
| `AUDITORIA_2026-10.md` | Registro histórico de la auditoría de seguridad de octubre |
| `ANALISIS_PROFUNDO_PDF_TOOLS.md` | **Foto de abril de 2026, no el estado actual.** Tiene cabecera de aviso |
| `docs/superpowers/plans/` | Planes de implementación por tarea |
