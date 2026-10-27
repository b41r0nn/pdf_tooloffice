"""
edicion_texto.py — Edición de texto existente en un PDF (PyMuPDF)

Flujo de reemplazo de un fragmento (span):
1) Se localiza el span original: fuente, tamaño, color, línea base y dirección.
2) Se elimina SOLO ese texto con una redacción en banda estrecha sobre su
   línea base, sin relleno y sin tocar imágenes ni trazos (bordes de tablas,
   subrayados y fondos de color quedan intactos). Una banda estrecha evita
   borrar también las líneas vecinas cuando el interlineado es apretado.
3) Se escribe el texto nuevo en la misma línea base con la misma familia de
   fuente instalada en el sistema; si no existe, con un equivalente métrico
   libre (Liberation, Carlito, Caladea, DejaVu) y, como último recurso, con
   una fuente base14 de PDF.
4) Se recortan (subset) las fuentes del documento completo para no inflar el
   archivo. Recortar solo la página editada rompe las demás páginas que
   comparten la misma fuente, por eso se hace a nivel de documento.

Las fuentes embebidas del PDF no se reutilizan: casi siempre son subsets sin
tabla cmap (Type0/Identity-H de Word) y escribir con ellas produce glifos
vacíos.
"""

import glob
import logging
import os
import re
import sys
import threading
import uuid
from functools import lru_cache

import pymupdf as fitz  # PyMuPDF

log = logging.getLogger(__name__)

MAX_CARACTERES = 200
TAMANO_MINIMO = 4.0
REDUCCION_MAXIMA = 0.7      # el texto nuevo no se reduce a menos del 70 % del tamaño original
MARGEN_PAGINA = 12.0        # pt que se respetan contra el borde de la página
ALINEACIONES = ('izquierda', 'derecha', 'centro')

# Flags de span de PyMuPDF
_FLAG_CURSIVA = 2
_FLAG_SERIF = 4
_FLAG_MONO = 8
_FLAG_NEGRITA = 16

BASE14_SHORT = {
    'Helvetica': 'helv',
    'Helvetica-Bold': 'hebo',
    'Helvetica-Oblique': 'heit',
    'Helvetica-BoldOblique': 'hebi',
    'Times-Roman': 'tiro',
    'Times-Bold': 'tibo',
    'Times-Italic': 'tiit',
    'Times-BoldItalic': 'tibi',
    'Courier': 'cour',
    'Courier-Bold': 'cobo',
    'Courier-Oblique': 'coit',
    'Courier-BoldOblique': 'cobi',
}

# Equivalentes de familia, en orden de preferencia. Los libres (Liberation,
# Carlito, Caladea, Arimo, Tinos, Cousine) son métricamente compatibles con
# las fuentes de Microsoft, así el texto ocupa el mismo ancho.
_SUSTITUTOS = {
    'helvetica': ['arial', 'liberationsans', 'arimo', 'nimbussans'],
    'arial': ['liberationsans', 'arimo', 'helvetica', 'nimbussans'],
    'calibri': ['carlito'],
    'cambria': ['caladea'],
    'timesnewroman': ['liberationserif', 'tinos', 'times', 'nimbusroman'],
    'times': ['timesnewroman', 'liberationserif', 'tinos', 'nimbusroman'],
    'couriernew': ['liberationmono', 'cousine', 'courier', 'nimbusmono'],
    'courier': ['couriernew', 'liberationmono', 'cousine', 'nimbusmono'],
}
_GENERICAS_SANS = ['arial', 'liberationsans', 'arimo', 'dejavusans', 'notosans']
_GENERICAS_SERIF = ['timesnewroman', 'liberationserif', 'tinos', 'dejavuserif', 'notoserif']
_GENERICAS_MONO = ['couriernew', 'liberationmono', 'cousine', 'dejavusansmono']

_RE_ESTILO = re.compile(r'^(bold|italic|oblique|regular|roman|normal|book|it|bd)+$')
_RE_SEPARADORES = re.compile(r'[\s,\-_]+')
_RE_CONTROL = re.compile(r'[\x00-\x1f\x7f]')


# ── Utilidades de texto ───────────────────────────────────────────

def normalizar_texto(texto):
    """Normaliza artefactos de extracción (NBSP, guiones Unicode) para comparar y mostrar."""
    return (texto or '').replace('\xa0', ' ').replace('\u2010', '-').replace('\u2011', '-')


def _limpiar_texto_nuevo(texto, max_caracteres):
    texto = texto or ''
    if '\n' in texto or '\r' in texto:
        raise ValueError('El texto de reemplazo debe ser de una sola línea')
    texto = _RE_CONTROL.sub('', texto)
    if len(texto) > max_caracteres:
        raise ValueError(f'El texto de reemplazo no puede superar {max_caracteres} caracteres')
    return texto


def _color_hex(color):
    return f'#{(color or 0):06X}'


def _color_rgb(color):
    color = color or 0
    return (((color >> 16) & 0xFF) / 255.0, ((color >> 8) & 0xFF) / 255.0, (color & 0xFF) / 255.0)


# ── Índice de fuentes del sistema ─────────────────────────────────

def analizar_nombre_fuente(nombre):
    """
    Devuelve (clave_familia, negrita, cursiva) a partir del nombre de una fuente.

    'ABCDEF+Arial-BoldMT' -> ('arial', True, False)
    'TimesNewRomanPS-BoldItalicMT' -> ('timesnewroman', True, True)
    'Calibri Light Regular' -> ('calibrilight', False, False)
    """
    base = (nombre or '').split('+', 1)[-1]
    familia = []
    negrita = cursiva = False
    for parte in _RE_SEPARADORES.split(base.lower()):
        if not parte:
            continue
        for sufijo in ('psmt', 'mt', 'ps'):
            if parte.endswith(sufijo) and len(parte) - len(sufijo) >= 3:
                parte = parte[: -len(sufijo)]
                break
        if _RE_ESTILO.match(parte):
            negrita = negrita or 'bold' in parte or parte == 'bd'
            cursiva = cursiva or 'italic' in parte or 'oblique' in parte or parte == 'it'
            continue
        if parte in ('black', 'heavy'):
            negrita = True
        familia.append(parte)
    return ''.join(familia), negrita, cursiva


def _directorios_fuentes():
    dirs = []
    extra = os.environ.get('PDF_FONTS_DIR')
    if extra:
        dirs.append(extra)
    if sys.platform.startswith('win'):
        dirs.append(os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts'))
        local = os.environ.get('LOCALAPPDATA')
        if local:
            dirs.append(os.path.join(local, 'Microsoft', 'Windows', 'Fonts'))
    elif sys.platform == 'darwin':
        dirs += ['/Library/Fonts', '/System/Library/Fonts', os.path.expanduser('~/Library/Fonts')]
    else:
        dirs += ['/usr/share/fonts', '/usr/local/share/fonts',
                 os.path.expanduser('~/.local/share/fonts'), os.path.expanduser('~/.fonts')]
    return [d for d in dirs if os.path.isdir(d)]


_indice_lock = threading.Lock()
_indice = None


def _indice_fuentes():
    """{clave_familia: [(negrita, cursiva, ruta), ...]} — se construye una vez (≈0,5-2 s en Windows)."""
    global _indice
    if _indice is not None:
        return _indice
    with _indice_lock:
        if _indice is not None:
            return _indice
        indice = {}
        for carpeta in _directorios_fuentes():
            for ruta in glob.glob(os.path.join(carpeta, '**', '*'), recursive=True):
                if os.path.splitext(ruta)[1].lower() not in ('.ttf', '.otf'):
                    continue
                try:
                    fuente = fitz.Font(fontfile=ruta)
                except Exception:
                    continue
                clave, neg_nombre, cur_nombre = analizar_nombre_fuente(fuente.name)
                if not clave:
                    continue
                negrita = bool(fuente.is_bold) or neg_nombre
                cursiva = bool(fuente.is_italic) or cur_nombre
                indice.setdefault(clave, []).append((negrita, cursiva, ruta))
        log.info('Índice de fuentes del sistema: %d familias', len(indice))
        _indice = indice
        return _indice


def precargar_fuentes():
    try:
        _indice_fuentes()
    except Exception:
        log.exception('No se pudo indexar las fuentes del sistema')


def _buscar_fuente_sistema(clave, negrita, cursiva):
    variantes = _indice_fuentes().get(clave)
    if not variantes:
        return None
    for criterio in (
        lambda n, c: n == negrita and c == cursiva,
        lambda n, c: n == negrita and not c,
        lambda n, c: not n and not c,
    ):
        for n, c, ruta in variantes:
            if criterio(n, c):
                return ruta
    return variantes[0][2]


@lru_cache(maxsize=64)
def _fuente_archivo(ruta):
    return fitz.Font(fontfile=ruta)


def _cubre_texto(fuente, texto):
    return all(fuente.has_glyph(ord(ch)) for ch in set(texto) if not ch.isspace())


def _base14_para(clave, negrita, cursiva, flags):
    if (flags & _FLAG_MONO) or 'courier' in clave or 'mono' in clave or 'consola' in clave:
        familia = 'Courier'
    elif (flags & _FLAG_SERIF) or 'times' in clave or 'serif' in clave.replace('sansserif', ''):
        familia = 'Times'
    else:
        familia = 'Helvetica'
    if familia == 'Times':
        nombre = {(False, False): 'Times-Roman', (True, False): 'Times-Bold',
                  (False, True): 'Times-Italic', (True, True): 'Times-BoldItalic'}[(negrita, cursiva)]
    else:
        sufijo = {(False, False): '', (True, False): '-Bold',
                  (False, True): '-Oblique', (True, True): '-BoldOblique'}[(negrita, cursiva)]
        nombre = familia + sufijo
    return nombre


def resolver_fuente(nombre_original, flags, texto):
    """
    Elige la fuente con la que se escribirá el texto nuevo.

    Retorna dict con: tipo ('sistema'|'base14'), ruta (o None), nombre_pymupdf
    (alias base14 o None), nombre (legible) y aproximada (True si no es la
    misma familia ni un equivalente métrico de ella, p. ej. Carlito por Calibri).
    """
    clave, negrita, cursiva = analizar_nombre_fuente(nombre_original)
    negrita = negrita or bool(flags & _FLAG_NEGRITA)
    cursiva = cursiva or bool(flags & _FLAG_CURSIVA)

    if flags & _FLAG_MONO:
        genericas = _GENERICAS_MONO
    elif flags & _FLAG_SERIF:
        genericas = _GENERICAS_SERIF
    else:
        genericas = _GENERICAS_SANS

    equivalentes = [clave, *_SUSTITUTOS.get(clave, [])]
    candidatos = []
    for c in [*equivalentes, *genericas]:
        if c and c not in candidatos:
            candidatos.append(c)

    for candidato in candidatos:
        ruta = _buscar_fuente_sistema(candidato, negrita, cursiva)
        if not ruta:
            continue
        try:
            fuente = _fuente_archivo(ruta)
        except Exception:
            continue
        if _cubre_texto(fuente, texto):
            return {
                'tipo': 'sistema',
                'ruta': ruta,
                'nombre_pymupdf': None,
                'nombre': fuente.name,
                'aproximada': candidato not in equivalentes,
            }

    base14 = _base14_para(clave, negrita, cursiva, flags)
    return {
        'tipo': 'base14',
        'ruta': None,
        'nombre_pymupdf': BASE14_SHORT[base14],
        'nombre': base14,
        'aproximada': True,
    }


def _ancho_texto(info_fuente, texto, tamano):
    if info_fuente['tipo'] == 'sistema':
        return _fuente_archivo(info_fuente['ruta']).text_length(texto, fontsize=tamano)
    return fitz.get_text_length(texto, fontname=info_fuente['nombre_pymupdf'], fontsize=tamano)


# ── Geometría ─────────────────────────────────────────────────────

def _cargar_pagina(doc, pagina_num):
    if not isinstance(pagina_num, int) or pagina_num < 0 or pagina_num >= doc.page_count:
        raise ValueError(f'Página {pagina_num + 1 if isinstance(pagina_num, int) else pagina_num} '
                         f'fuera de rango (1-{doc.page_count})')
    return doc.load_page(pagina_num)


def _rotacion_desde_dir(direccion):
    """Ángulo (0/90/180/270) de insert_text para la dirección de escritura del span."""
    dx, dy = direccion
    if abs(dy) < 0.02:
        return 0 if dx > 0 else 180
    if abs(dx) < 0.02:
        return 90 if dy < 0 else 270
    return None


def _proyectar(rect, origen, u):
    """Extensiones de un rect a lo largo de la dirección u (a) y su perpendicular (b), relativas a origen."""
    ox, oy = origen
    ux, uy = u
    esquinas = (rect.tl, rect.tr, rect.bl, rect.br)
    a = [(p.x - ox) * ux + (p.y - oy) * uy for p in esquinas]
    b = [-(p.x - ox) * uy + (p.y - oy) * ux for p in esquinas]
    return min(a), max(a), min(b), max(b)


def _punto(origen, u, a, b=0.0):
    ux, uy = u
    return fitz.Point(origen[0] + a * ux - b * uy, origen[1] + a * uy + b * ux)


_ANOTACIONES_CON_TEXTO = {fitz.PDF_ANNOT_FREE_TEXT, fitz.PDF_ANNOT_STAMP, fitz.PDF_ANNOT_TEXT}


def _rects_anotaciones(page):
    """
    Rectángulos de anotaciones que dibujan su propio texto (texto libre, sellos,
    notas, campos de formulario). La extracción de texto las incluye, pero no son
    contenido de la página: redactarlas no las borra y se duplicaría el texto.
    Los resaltados no se excluyen porque cubren texto real de la página.
    """
    rects = [a.rect for a in page.annots() if a.type[0] in _ANOTACIONES_CON_TEXTO]
    rects += [w.rect for w in page.widgets()]
    return rects


def _iterar_spans(page):
    """Itera (id, line, span) sobre el texto del contenido de la página."""
    excluir = _rects_anotaciones(page)
    for bi, block in enumerate(page.get_text('dict')['blocks']):
        if block.get('type') != 0:
            continue
        for li, line in enumerate(block.get('lines', [])):
            for si, span in enumerate(line.get('spans', [])):
                if excluir and _centro_dentro(span['bbox'], excluir):
                    continue
                yield f'{bi}-{li}-{si}', line, span


def _bboxes_invisibles(page):
    """Rectángulos de texto invisible (capas OCR, render mode 3)."""
    try:
        return [fitz.Rect(t['bbox']) for t in page.get_texttrace() if t.get('type') == 3]
    except Exception:
        return []


def _centro_dentro(bbox, rects):
    """True si el centro de bbox cae dentro de alguno de los rects."""
    r = fitz.Rect(bbox)
    centro = fitz.Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)
    return any(centro in otro for otro in rects)


def _fraccion_imagenes(page):
    area_pagina = abs(page.rect)
    if not area_pagina:
        return 0.0
    area = 0.0
    for info in page.get_image_info():
        area += abs(fitz.Rect(info['bbox']) & page.rect)
    return min(1.0, area / area_pagina)


# ── Detección ─────────────────────────────────────────────────────

def detectar_campos_pdf(ruta_pdf, pagina_num=0, max_caracteres=MAX_CARACTERES):
    """
    Detecta los fragmentos de texto editables de una página.

    Retorna dict con: pagina, ancho/alto (pt de la vista, ya rotada), rotacion,
    escaneada (página sin texto real y cubierta por imágenes) y campos. Cada
    campo trae 'bbox' (coordenadas PDF sin rotar, para reemplazar) y 'vista'
    (coordenadas de la página tal como se ve, para dibujar el overlay).
    """
    with fitz.open(ruta_pdf) as doc:
        page = _cargar_pagina(doc, pagina_num)
        matriz = page.rotation_matrix
        invisibles = _bboxes_invisibles(page)
        campos = []
        texto_invisible = 0

        for campo_id, line, span in _iterar_spans(page):
            texto = normalizar_texto(span.get('text', ''))
            if not texto.strip() or len(texto) > max_caracteres:
                continue
            if invisibles and _centro_dentro(span['bbox'], invisibles):
                texto_invisible += 1
                continue
            flags = span.get('flags', 0)
            _, negrita, cursiva = analizar_nombre_fuente(span.get('font', ''))
            vista = fitz.Rect(span['bbox']) * matriz
            campos.append({
                'id': campo_id,
                'texto': texto,
                'bbox': [round(v, 2) for v in span['bbox']],
                'vista': [round(v, 2) for v in vista],
                'fuente': span.get('font', '').split('+', 1)[-1],
                'tamano': round(span.get('size', 0), 2),
                'color': _color_hex(span.get('color')),
                'negrita': negrita or bool(flags & _FLAG_NEGRITA),
                'cursiva': cursiva or bool(flags & _FLAG_CURSIVA),
                'editable': _rotacion_desde_dir(line.get('dir', (1, 0))) is not None,
            })

        escaneada = not campos and (texto_invisible > 0 or _fraccion_imagenes(page) >= 0.5)
        return {
            'pagina': pagina_num,
            'ancho': round(page.rect.width, 2),
            'alto': round(page.rect.height, 2),
            'rotacion': page.rotation,
            'escaneada': escaneada,
            'total_campos': len(campos),
            'campos': campos,
        }


# ── Reemplazo ─────────────────────────────────────────────────────

def _localizar_span(page, bbox, texto_original):
    objetivo = fitz.Rect(bbox)
    if objetivo.is_empty or objetivo.is_infinite:
        raise ValueError('bbox inválido')
    mejor = None
    mejor_area = 0.0
    for _, line, span in _iterar_spans(page):
        area = abs(objetivo & fitz.Rect(span['bbox']))
        if area > mejor_area:
            mejor, mejor_area = (line, span), area
    if not mejor or mejor_area < 0.3 * min(abs(objetivo), abs(fitz.Rect(mejor[1]['bbox'])) or 1):
        raise ValueError('No se encontró el texto en esa posición. Recarga la página e inténtalo de nuevo.')
    if texto_original is not None and normalizar_texto(mejor[1]['text']).strip() != normalizar_texto(texto_original).strip():
        raise ValueError('El texto de la página cambió. Recarga la página e inténtalo de nuevo.')
    return mejor


def _espacio_disponible(page, span, origen, u):
    """Límites (a lo largo de u) hasta el texto vecino más cercano en la misma línea o el margen."""
    a0, a1, b0, b1 = _proyectar(fitz.Rect(span['bbox']), origen, u)
    alto = max(b1 - b0, 0.1)
    izq = None
    der = None
    for _, _, otro in _iterar_spans(page):
        if otro is span or not otro.get('text', '').strip():
            continue
        oa0, oa1, ob0, ob1 = _proyectar(fitz.Rect(otro['bbox']), origen, u)
        solape = min(b1, ob1) - max(b0, ob0)
        if solape < 0.5 * min(alto, max(ob1 - ob0, 0.1)):
            continue
        if oa0 >= a1 - 0.5:
            der = oa0 if der is None else min(der, oa0)
        elif oa1 <= a0 + 0.5:
            izq = oa1 if izq is None else max(izq, oa1)

    pa0, pa1, _, _ = _proyectar(page.rect * page.derotation_matrix, origen, u)
    lim_izq = pa0 + MARGEN_PAGINA if izq is None else izq + 1.0
    lim_der = pa1 - MARGEN_PAGINA if der is None else der - 1.0
    return a0, a1, b0, b1, lim_izq, lim_der


def reemplazar_texto_pdf(ruta_pdf, pagina_num, bbox, texto_nuevo, *, texto_original=None,
                         alineacion='izquierda', max_caracteres=MAX_CARACTERES):
    """
    Reemplaza (o elimina, si texto_nuevo es vacío) un fragmento de texto de una página.

    Retorna (bytes_del_pdf, metadata).
    """
    if alineacion not in ALINEACIONES:
        raise ValueError(f'Alineación inválida. Opciones: {", ".join(ALINEACIONES)}')
    texto_nuevo = _limpiar_texto_nuevo(texto_nuevo, max_caracteres)

    with fitz.open(ruta_pdf) as doc:
        if doc.needs_pass:
            raise ValueError('El PDF está protegido con contraseña')
        page = _cargar_pagina(doc, pagina_num)

        if any(a.type[0] == fitz.PDF_ANNOT_REDACT for a in page.annots()):
            raise ValueError('La página tiene marcas de redacción pendientes. '
                             'Aplícalas o elimínalas antes de editar el texto.')

        line, span = _localizar_span(page, bbox, texto_original)
        u = tuple(line.get('dir', (1, 0)))
        rotacion = _rotacion_desde_dir(u)
        if rotacion is None:
            raise ValueError('El texto está inclinado y no se puede reemplazar. Usa el modo "Anotar y firmar".')
        u = {0: (1, 0), 90: (0, -1), 180: (-1, 0), 270: (0, 1)}[rotacion]

        origen = tuple(span['origin'])
        tamano_original = float(span.get('size') or 11)
        flags = span.get('flags', 0)
        nombre_original = span.get('font', '')
        a0, a1, _, _, lim_izq, lim_der = _espacio_disponible(page, span, origen, u)

        # 1) Eliminar solo el texto original (banda estrecha sobre la línea base).
        banda = fitz.Quad(
            _punto(origen, u, a0 + 0.3, -tamano_original * 0.5),
            _punto(origen, u, a1 - 0.3, -tamano_original * 0.5),
            _punto(origen, u, a0 + 0.3, -tamano_original * 0.2),
            _punto(origen, u, a1 - 0.3, -tamano_original * 0.2),
        )
        page.add_redact_annot(banda, fill=False, cross_out=False)
        page.apply_redactions(
            images=fitz.PDF_REDACT_IMAGE_NONE,
            graphics=fitz.PDF_REDACT_LINE_ART_NONE,
            text=fitz.PDF_REDACT_TEXT_REMOVE,
        )

        metadata = {
            'fuente_original': nombre_original.split('+', 1)[-1],
            'tamano_original': round(tamano_original, 2),
            'alineacion': alineacion,
            'eliminado': not texto_nuevo,
        }

        if texto_nuevo:
            # 2) Ajustar tamaño al espacio disponible según la alineación.
            fuente = resolver_fuente(nombre_original, flags, texto_nuevo)
            ancho = _ancho_texto(fuente, texto_nuevo, tamano_original)
            if alineacion == 'izquierda':
                disponible = lim_der - a0
            elif alineacion == 'derecha':
                disponible = a1 - lim_izq
            else:
                centro = (a0 + a1) / 2
                disponible = 2 * min(centro - lim_izq, lim_der - centro)
            disponible = max(disponible, a1 - a0)

            tamano = tamano_original
            if ancho > disponible > 0:
                tamano = max(tamano_original * REDUCCION_MAXIMA, tamano_original * disponible / ancho, TAMANO_MINIMO)
                ancho = _ancho_texto(fuente, texto_nuevo, tamano)

            if alineacion == 'izquierda':
                inicio = a0
            elif alineacion == 'derecha':
                inicio = a1 - ancho
            else:
                inicio = (a0 + a1) / 2 - ancho / 2

            # 3) Escribir en la misma línea base.
            opciones = {
                'fontsize': tamano,
                'color': _color_rgb(span.get('color')),
                'rotate': rotacion,
            }
            if fuente['tipo'] == 'sistema':
                # Alias único: si se reutilizara el de una edición previa, PyMuPDF
                # tomaría esa fuente ya recortada y faltarían glifos.
                opciones['fontname'] = f'PTO{uuid.uuid4().hex[:8]}'
                opciones['fontfile'] = fuente['ruta']
            else:
                opciones['fontname'] = fuente['nombre_pymupdf']
            page.insert_text(_punto(origen, u, inicio), texto_nuevo, **opciones)

            # 4) Recortar fuentes (documento completo; ver docstring del módulo).
            # En formularios no se recorta: los campos pueden necesitar glifos que
            # el contenido de la página no usa.
            if fuente['tipo'] == 'sistema' and not doc.is_form_pdf:
                try:
                    doc.subset_fonts()
                except Exception:
                    log.warning('No se pudieron recortar las fuentes; el archivo quedará más grande', exc_info=True)

            metadata.update({
                'fuente_usada': fuente['nombre'],
                'tipo_fuente': fuente['tipo'],
                'fuente_aproximada': fuente['aproximada'],
                'tamano': round(tamano, 2),
                'tamano_reducido': tamano < tamano_original - 0.01,
                'desborda': ancho > disponible + 0.5,
            })

        return doc.tobytes(garbage=3, deflate=True), metadata
