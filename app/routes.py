"""
routes.py — Endpoints Flask
Cada endpoint recibe archivos via multipart/form-data,
llama a services.py, registra en SQLite y retorna el archivo procesado.
"""

import hmac
import html
import io
import logging
import os
import re
import tempfile
import uuid
from datetime import datetime

from flask import Blueprint, current_app, jsonify, render_template, request, send_file, send_from_directory
from werkzeug.exceptions import HTTPException
from werkzeug.utils import secure_filename

from . import __version__
from .database import exportar_logs_excel, obtener_logs, registrar_log
from .services import (
    NIVELES_COMPRESION,
    analizar_grupos,
    cifrar_pdf,
    comprimir_pdf,
    contar_paginas,
    convertir_imagenes_a_pdf,
    convertir_pdf_a_jpg,
    dividir_pdf,
    dividir_pdf_por_modo,
    dividir_por_grupos,
    docx_a_pdf,
    grupos_por_bloques,
    pdf_a_docx,
    pdf_a_xlsx,
    unir_pdfs,
    validar_mime_type,
    validar_pdf,
    xlsx_a_pdf,
)

log = logging.getLogger(__name__)

bp = Blueprint('main', __name__)

EXT_IMAGEN = {'jpg', 'jpeg', 'png', 'bmp', 'tiff', 'tif', 'webp'}
MIMETYPES = {
    'pdf':  'application/pdf',
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
}
# direccion -> (extensión de entrada, extensión de salida, función)
CONVERSIONES = {
    'pdf-docx': ('pdf', 'docx', pdf_a_docx),
    'pdf-xlsx': ('pdf', 'xlsx', pdf_a_xlsx),
    'docx-pdf': ('docx', 'pdf', docx_a_pdf),
    'xlsx-pdf': ('xlsx', 'pdf', xlsx_a_pdf),
}
MAX_CONTRASENA = 127  # límite de AES-256 (PDF 2.0)
_RE_CONTROL = re.compile(r'[\x00-\x1f\x7f"]')


# ── Helpers ───────────────────────────────────────────────────────

def extension(filename):
    return filename.rsplit('.', 1)[-1].lower() if filename and '.' in filename else ''


def nombre_base(filename, defecto='documento'):
    """Nombre original sin ruta ni extensión, apto para Content-Disposition (conserva tildes)."""
    nombre = os.path.basename((filename or '').replace('\\', '/'))
    nombre = _RE_CONTROL.sub('', nombre.rsplit('.', 1)[0] if '.' in nombre else nombre).strip()
    return nombre[:120] or defecto


def entero(nombre, defecto, minimo=None, maximo=None):
    """Lee un entero de form/query con validación y mensaje claro."""
    valor = request.values.get(nombre)
    if valor is None or str(valor).strip() == '':
        return defecto
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        raise ValueError(f'El parámetro "{nombre}" debe ser un número entero')
    if (minimo is not None and numero < minimo) or (maximo is not None and numero > maximo):
        # La frase se arma con los límites que REALMENTE existen: con solo `minimo`
        # el texto de antes decía "debe estar entre 1 y None", que no se puede leer.
        if minimo is not None and maximo is not None:
            limite = f'estar entre {minimo} y {maximo}'
        elif minimo is not None:
            limite = f'ser {minimo} o más'
        else:
            limite = f'ser {maximo} o menos'
        raise ValueError(f'El parámetro "{nombre}" debe {limite}')
    return numero


def sanitizar_error(msg):
    """Sanitiza mensajes de error para no exponer rutas internas."""
    if current_app.config.get('DEBUG'):
        return msg
    for clave, marcador in (('UPLOAD_FOLDER', '[UPLOAD]'), ('DATABASE_PATH', '[DATABASE]')):
        ruta = current_app.config.get(clave)
        if ruta:
            msg = msg.replace(ruta, marcador)
    if re.search(r'[A-Za-z]:\\|/(?:home|tmp|var|usr|opt|app)/', msg):
        return 'Error procesando archivo. Por favor, intenta de nuevo.'
    return msg


def validar_autenticacion_admin(password_header):
    """Valida la contraseña de admin en tiempo constante. Sin contraseña configurada no hay acceso."""
    admin_password = current_app.config.get('ADMIN_PASSWORD') or ''
    if not admin_password:
        return False
    return hmac.compare_digest(password_header.encode('utf-8'), admin_password.encode('utf-8'))


def guardar_temporal(file_obj, upload_folder):
    """Guarda un FileStorage en disco con nombre único. Retorna (ruta, nombre_seguro)."""
    nombre_seguro = secure_filename(file_obj.filename or '') or 'archivo'
    ruta = os.path.join(upload_folder, f'{uuid.uuid4().hex}_{nombre_seguro}')
    file_obj.save(ruta)
    return ruta, nombre_seguro


def eliminar_temporales(*rutas):
    for ruta in rutas:
        try:
            if ruta and os.path.isfile(ruta):
                os.remove(ruta)
        except OSError:
            pass


def registrar_log_seguro(modulo, archivo, tamano, resultado, detalle=None):
    """El registro nunca debe tumbar la respuesta (p. ej. SQLite bloqueado)."""
    try:
        registrar_log(current_app.config['DATABASE_PATH'], modulo, archivo, tamano, resultado, detalle)
    except Exception:
        log.exception('No se pudo registrar el log de %s', modulo)


def log_y_enviar(modulo, nombre, tamano, resultado_bytes, nombre_salida, mimetype, detalle=None):
    """Registra el log y retorna el archivo al cliente."""
    registrar_log_seguro(modulo, nombre, tamano, 'exito', detalle)
    return send_file(
        io.BytesIO(resultado_bytes),
        mimetype=mimetype,
        as_attachment=True,
        download_name=nombre_salida,
    )


def error_response(modulo, nombre, tamano, exc):
    """ValueError = error del usuario (400, mensaje visible). Otro = error interno (500, mensaje genérico)."""
    if isinstance(exc, HTTPException):
        raise exc  # p. ej. 413: lo responde el manejador registrado en la app
    if isinstance(exc, ValueError):
        registrar_log_seguro(modulo, nombre, tamano, 'error', str(exc))
        return jsonify({'error': sanitizar_error(str(exc))}), 400
    log.exception('Error interno en %s (%s)', modulo, nombre)
    registrar_log_seguro(modulo, nombre, tamano, 'error', f'{type(exc).__name__}: {exc}')
    return jsonify({'error': 'Error procesando el archivo. Verifica que no esté dañado e inténtalo de nuevo.'}), 500


def recibir_pdf(campo='archivo'):
    """Guarda el PDF subido y lo valida. Retorna (ruta, nombre_original, tamaño)."""
    f = request.files.get(campo)
    if not f or extension(f.filename) != 'pdf':
        raise ValueError('Se requiere un archivo PDF')
    ruta, _ = guardar_temporal(f, current_app.config['UPLOAD_FOLDER'])
    try:
        es_valido, msg_error = validar_mime_type(ruta, 'pdf')
        if es_valido:
            es_valido, msg_error = validar_pdf(ruta)
        if not es_valido:
            raise ValueError(msg_error or 'Archivo no es un PDF válido')
    except Exception:
        eliminar_temporales(ruta)
        raise
    return ruta, f.filename, os.path.getsize(ruta)


# ── Health Check ──────────────────────────────────────────────────

@bp.route('/health')
def health():
    """Endpoint para verificar si la aplicación está viva."""
    return jsonify({
        'status':  'ok',
        'version': __version__,
        'author':  'Bairon Nicolas Calle Rivera',
        'license': 'CC BY-NC 4.0',
    }), 200


# ── Página principal ──────────────────────────────────────────────

@bp.route('/')
def index():
    return render_template('index.html', version=__version__)


@bp.route('/favicon.ico')
def favicon():
    """Algunos navegadores y lectores de enlaces piden el ícono en la raíz sin leer el HTML."""
    return send_from_directory(os.path.join(current_app.static_folder, 'icons'), 'favicon.ico',
                               mimetype='image/x-icon', max_age=86400)


# ── Páginas de archivos ───────────────────────────────────────────

@bp.route('/api/paginas', methods=['POST'])
def paginas():
    """Retorna el número de páginas de un PDF."""
    ruta = None
    try:
        ruta, _, _ = recibir_pdf()
        return jsonify({'paginas': contar_paginas(ruta, request.form.get('contrasena', ''))})
    except ValueError as e:
        return jsonify({'error': sanitizar_error(str(e))}), 400
    except HTTPException:
        raise
    except Exception:
        log.exception('Error contando páginas')
        return jsonify({'error': 'No se pudo leer el PDF'}), 500
    finally:
        eliminar_temporales(ruta)


# ── Unión ─────────────────────────────────────────────────────────

@bp.route('/api/union', methods=['POST'])
def union():
    upload_folder = current_app.config['UPLOAD_FOLDER']
    archivos = request.files.getlist('archivos')
    rutas = []
    tamano = 0
    try:
        if len(archivos) < 2:
            raise ValueError('Se necesitan al menos 2 archivos PDF')
        for f in archivos:
            if extension(f.filename) != 'pdf':
                raise ValueError(f'"{nombre_base(f.filename)}" no es un PDF')
            ruta, _ = guardar_temporal(f, upload_folder)
            rutas.append(ruta)
            es_valido, msg_error = validar_mime_type(ruta, 'pdf')
            if not es_valido:
                raise ValueError(msg_error)
            tamano += os.path.getsize(ruta)

        comprimir = request.form.get('comprimir', 'false') == 'true'
        nivel = request.form.get('nivel', 'media')
        if comprimir and nivel not in NIVELES_COMPRESION:
            raise ValueError(f'Nivel inválido. Opciones: {", ".join(NIVELES_COMPRESION)}')

        resultado = unir_pdfs(rutas, contrasena=request.form.get('contrasena_union', ''))

        if comprimir:
            fd, tmp = tempfile.mkstemp(suffix='.pdf', dir=upload_folder)
            with os.fdopen(fd, 'wb') as fh:
                fh.write(resultado)
            rutas.append(tmp)
            resultado = comprimir_pdf(tmp, nivel)

        nombre_salida = nombre_base(request.form.get('nombre_salida'), 'documento_unido') + '.pdf'
        detalle = f'{len(archivos)} archivos; comprimir={comprimir}' + (f'; nivel={nivel}' if comprimir else '')
        return log_y_enviar('union', nombre_salida, tamano, resultado, nombre_salida,
                            MIMETYPES['pdf'], detalle=detalle)
    except Exception as e:
        return error_response('union', 'union_multiple.pdf', tamano, e)
    finally:
        eliminar_temporales(*rutas)


# ── División ──────────────────────────────────────────────────────

@bp.route('/api/division', methods=['POST'])
def division():
    ruta, nombre, tamano = None, 'archivo.pdf', 0
    try:
        ruta, nombre, tamano = recibir_pdf()
        base = nombre_base(nombre)
        modo = request.form.get('modo', 'rango')
        if modo == 'rango':
            inicio = entero('inicio', None, minimo=1)
            fin = entero('fin', None, minimo=1)
            if inicio is None or fin is None:
                raise ValueError('Indica la página de inicio y la de fin')
            resultado = dividir_pdf(ruta, inicio, fin)
            nombre_salida = f'{base}_paginas_{inicio}_a_{fin}.pdf'
            mimetype = MIMETYPES['pdf']
            detalle = f'modo=rango; paginas {inicio}-{fin}'
        elif modo == 'cada':
            paginas_por_archivo = entero('paginas_por_archivo', None, minimo=1)
            if paginas_por_archivo is None:
                raise ValueError('Indica cuántas páginas va a tener cada archivo')
            grupos = grupos_por_bloques(contar_paginas(ruta), paginas_por_archivo)
            resultado = dividir_por_grupos(ruta, grupos, base)
            nombre_salida, mimetype = f'{base}_dividido.zip', 'application/zip'
            detalle = f'modo=cada; paginas_por_archivo={paginas_por_archivo}; archivos={len(grupos)}'
        elif modo == 'personalizado':
            total = contar_paginas(ruta)
            grupos = analizar_grupos(request.form.get('grupos', ''), total)
            resultado = dividir_por_grupos(ruta, grupos, base)
            nombre_salida, mimetype = f'{base}_dividido.zip', 'application/zip'
            detalle = f'modo=personalizado; grupos={len(grupos)}; paginas={total}'
        else:
            resultado, tipo = dividir_pdf_por_modo(ruta, modo)
            if tipo == 'zip':
                nombre_salida, mimetype = f'{base}_paginas.zip', 'application/zip'
            else:
                nombre_salida, mimetype = f'{base}_{modo}.pdf', MIMETYPES['pdf']
            detalle = f'modo={modo}'
        return log_y_enviar('division', nombre, tamano, resultado, nombre_salida, mimetype, detalle=detalle)
    except Exception as e:
        return error_response('division', nombre, tamano, e)
    finally:
        eliminar_temporales(ruta)


# ── Conversión ────────────────────────────────────────────────────

@bp.route('/api/conversion', methods=['POST'])
def conversion():
    upload_folder = current_app.config['UPLOAD_FOLDER']
    direccion = request.form.get('direccion', '')

    # Caso especial: imagen_a_pdf recibe múltiples archivos
    if direccion == 'imagen_a_pdf':
        rutas_imagenes = []
        tamano = 0
        try:
            archivos = [f for f in request.files.getlist('archivos') if f.filename]
            if not archivos:
                raise ValueError('No se enviaron imágenes')
            for img_file in archivos:
                if extension(img_file.filename) not in EXT_IMAGEN:
                    raise ValueError(f'"{nombre_base(img_file.filename)}" no es una imagen soportada')
                ruta_img, _ = guardar_temporal(img_file, upload_folder)
                rutas_imagenes.append(ruta_img)
                tamano += os.path.getsize(ruta_img)

            resultado = convertir_imagenes_a_pdf(rutas_imagenes)
            nombre_salida = (nombre_base(archivos[0].filename) if len(archivos) == 1 else 'imagenes') + '.pdf'
            return log_y_enviar('conversion', f'{len(rutas_imagenes)} imágenes', tamano, resultado,
                                nombre_salida, MIMETYPES['pdf'], detalle='imagen_a_pdf')
        except Exception as e:
            return error_response('conversion', 'múltiples imágenes', tamano, e)
        finally:
            eliminar_temporales(*rutas_imagenes)

    ruta, nombre, tamano = None, 'archivo', 0
    try:
        f = request.files.get('archivo')
        if not f or not f.filename:
            raise ValueError('Se requiere un archivo')
        nombre = f.filename
        ext_entrada = extension(nombre)

        if direccion == 'pdf_a_jpg':
            ext_esperada = 'pdf'
        elif direccion in CONVERSIONES:
            ext_esperada = CONVERSIONES[direccion][0]
        else:
            raise ValueError('Dirección de conversión desconocida')
        if ext_entrada != ext_esperada:
            raise ValueError(f'Para esta conversión se requiere un archivo .{ext_esperada}')

        ruta, _ = guardar_temporal(f, upload_folder)
        tamano = os.path.getsize(ruta)
        es_valido, msg_error = validar_mime_type(ruta, ext_entrada)
        if es_valido and ext_entrada == 'pdf':
            es_valido, msg_error = validar_pdf(ruta)
        if not es_valido:
            raise ValueError(msg_error or 'Archivo de entrada no es válido')

        base = nombre_base(nombre)
        if direccion == 'pdf_a_jpg':
            resultado, paginas = convertir_pdf_a_jpg(ruta)
            if paginas == 1:
                mimetype, nombre_salida = 'image/jpeg', f'{base}.jpg'
            else:
                mimetype, nombre_salida = 'application/zip', f'{base}_jpg.zip'
            return log_y_enviar('conversion', nombre, tamano, resultado, nombre_salida, mimetype,
                                detalle=f'pdf_a_jpg; {paginas} páginas')

        _, ext_salida, funcion = CONVERSIONES[direccion]
        if direccion == 'pdf-xlsx':
            resultado = funcion(ruta, nombre_archivo=os.path.basename(nombre))  # aparece en la hoja Resumen
        else:
            resultado = funcion(ruta)
        return log_y_enviar('conversion', nombre, tamano, resultado, f'{base}_convertido.{ext_salida}',
                            MIMETYPES[ext_salida], detalle=direccion)
    except Exception as e:
        return error_response('conversion', nombre, tamano, e)
    finally:
        eliminar_temporales(ruta)


# ── Compresión ────────────────────────────────────────────────────

@bp.route('/api/compresion', methods=['POST'])
def compresion():
    ruta, nombre, tamano = None, 'archivo.pdf', 0
    try:
        nivel = request.form.get('nivel', 'media')
        if nivel not in NIVELES_COMPRESION:
            raise ValueError(f'Nivel inválido. Opciones: {", ".join(NIVELES_COMPRESION)}')
        ruta, nombre, tamano = recibir_pdf()
        resultado = comprimir_pdf(ruta, nivel, contrasena=request.form.get('contrasena', ''))
        return log_y_enviar('compresion', nombre, tamano, resultado,
                            f'{nombre_base(nombre)}_comprimido.pdf', MIMETYPES['pdf'],
                            detalle=f'nivel={nivel}; {tamano} -> {len(resultado)} bytes')
    except Exception as e:
        return error_response('compresion', nombre, tamano, e)
    finally:
        eliminar_temporales(ruta)


# ── Cifrado ───────────────────────────────────────────────────────

@bp.route('/api/cifrado', methods=['POST'])
def cifrado():
    ruta, nombre, tamano = None, 'archivo.pdf', 0
    try:
        contrasena = request.form.get('contrasena', '')
        if not contrasena:
            raise ValueError('La contraseña no puede estar vacía')
        if contrasena != request.form.get('confirmar', ''):
            raise ValueError('Las contraseñas no coinciden')
        if len(contrasena) > MAX_CONTRASENA:
            raise ValueError(f'La contraseña no puede superar {MAX_CONTRASENA} caracteres')
        ruta, nombre, tamano = recibir_pdf()
        resultado = cifrar_pdf(ruta, contrasena)
        return log_y_enviar('cifrado', nombre, tamano, resultado,
                            f'{nombre_base(nombre)}_cifrado.pdf', MIMETYPES['pdf'], detalle='AES-256')
    except Exception as e:
        return error_response('cifrado', nombre, tamano, e)
    finally:
        eliminar_temporales(ruta)


# ── Logs (acceso protegido con contraseña) ────────────────────────

@bp.route('/admin/logs')
def ver_logs():
    """Vista de logs — requiere contraseña en el header X-Admin-Password."""
    if not validar_autenticacion_admin(request.headers.get('X-Admin-Password', '')):
        return jsonify({'error': 'No autorizado'}), 401

    logs = obtener_logs(current_app.config['DATABASE_PATH'], limit=500)
    e = html.escape  # nombres y detalles vienen de entradas de usuario: escapar siempre
    filas = ''.join(
        f"<tr><td>{r['id']}</td><td>{e(r['fecha'])}</td><td>{e(r['hora'])}</td>"
        f"<td>{e(r['modulo'])}</td><td>{e(r['archivo'])}</td>"
        f"<td>{r['tamano_kb']} KB</td>"
        f"<td class=\"{'ok' if r['resultado'] == 'exito' else 'err'}\">{e(r['resultado'])}</td>"
        f"<td>{e(r['detalle'] or '')}</td></tr>"
        for r in logs
    )
    pagina = f"""<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Registro de operaciones | PDF ToolOffice</title>
    <link rel="icon" href="/static/icons/favicon.ico" sizes="32x32">
    <link rel="icon" href="/static/icons/icon.svg" type="image/svg+xml">
    <style>
      :root{{color-scheme:dark}}
      body{{font-family:'Segoe UI',system-ui,sans-serif;margin:0;padding:32px;background:#0F192D;color:#EEF3FB}}
      h1{{font-size:28px;margin:0 0 6px}}
      p{{color:#8597B9;margin:0 0 20px}}
      .tabla{{overflow-x:auto;border-radius:14px;color-scheme:light}}
      table{{border-collapse:collapse;width:100%;font-size:14px;background:#F5F8FD;color:#0F192D}}
      th{{background:#E3EAF5;color:#3A4863;padding:10px 12px;text-align:left;border-bottom:3px solid #1D63C4;white-space:nowrap}}
      td{{padding:8px 12px;border-bottom:1px solid #D5DEEC;vertical-align:top}}
      tr:nth-child(even) td{{background:#EDF2F9}}
      .ok{{color:#157A43;font-weight:700}}
      .err{{color:#C62828;font-weight:700}}
    </style></head><body>
    <h1>Registro de operaciones</h1>
    <p>Las últimas 500 operaciones de PDF ToolOffice. Acceso protegido con contraseña.</p>
    <div class="tabla">
    <table>
      <thead><tr>
        <th>#</th><th>Fecha</th><th>Hora</th><th>Módulo</th>
        <th>Archivo</th><th>Tamaño</th><th>Resultado</th><th>Detalle</th>
      </tr></thead>
      <tbody>{filas}</tbody>
    </table>
    </div>
    </body></html>"""
    return pagina, 200, {'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store'}


@bp.route('/admin/logs/export')
def exportar_logs():
    """Descarga todos los logs en un único Excel con histórico completo."""
    if not validar_autenticacion_admin(request.headers.get('X-Admin-Password', '')):
        return jsonify({'error': 'No autorizado'}), 401

    datos = exportar_logs_excel(current_app.config['DATABASE_PATH'])
    return send_file(
        io.BytesIO(datos),
        mimetype=MIMETYPES['xlsx'],
        as_attachment=True,
        download_name=f'logs_pdf_tooloffice_{datetime.now():%Y%m%d_%H%M}.xlsx',
    )
