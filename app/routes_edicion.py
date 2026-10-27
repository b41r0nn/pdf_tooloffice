"""
routes_edicion.py — API del editor de PDF (sesiones persistentes con versiones)

  POST   /api/edicion                         sube un PDF y crea la sesión
  GET    /api/edicion/<id>                    info (nombre, versión, deshacer)
  GET    /api/edicion/<id>/pdf                PDF actual (lo abre el visor PDF.js)
  GET    /api/edicion/<id>/paginas/<n>/imagen PNG de la página n (0-based)
  GET    /api/edicion/<id>/paginas/<n>/campos texto editable de la página n
  POST   /api/edicion/<id>/reemplazar         reemplaza/borra un texto existente
  POST   /api/edicion/<id>/version            guarda el PDF anotado por PDF.js
  POST   /api/edicion/<id>/deshacer           vuelve a la versión anterior
  GET    /api/edicion/<id>/descargar          descarga (aplanar=1 fija anotaciones)
  DELETE /api/edicion/<id>                    cierra la sesión y borra sus archivos
"""

import io
import logging
import os

import pymupdf as fitz  # PyMuPDF
from flask import Blueprint, current_app, jsonify, request, send_file

from .edicion_texto import ALINEACIONES, MAX_CARACTERES, detectar_campos_pdf, reemplazar_texto_pdf
from .routes import (
    eliminar_temporales,
    entero,
    error_response,
    nombre_base,
    recibir_pdf,
    registrar_log_seguro,
    sanitizar_error,
)
from .services import abrir_pdf, aplanar_pdf
from .sesiones import SesionEdicion, SesionNoEncontrada, SesionOcupada

log = logging.getLogger(__name__)

bp_edicion = Blueprint('edicion', __name__, url_prefix='/api/edicion')

DPI_MIN, DPI_MAX = 36, 220


def _raiz():
    return current_app.config['EDIT_FOLDER']


def _sesion(sesion_id):
    sesion = SesionEdicion.abrir(_raiz(), sesion_id)
    sesion.tocar()
    return sesion


def _info(sesion):
    with fitz.open(sesion.ruta_actual) as doc:
        paginas = doc.page_count
    return {**sesion.info(), 'paginas': paginas}


@bp_edicion.errorhandler(SesionNoEncontrada)
def _no_encontrada(e):
    return jsonify({'error': str(e)}), 404


@bp_edicion.errorhandler(SesionOcupada)
def _ocupada(e):
    return jsonify({'error': str(e)}), 409


# ── Sesión ────────────────────────────────────────────────────────

@bp_edicion.route('', methods=['POST'])
def crear():
    ruta, nombre, tamano = None, 'archivo.pdf', 0
    try:
        ruta, nombre, tamano = recibir_pdf()
        contrasena = request.form.get('contrasena', '')
        with fitz.open(ruta) as doc:
            protegido = bool(doc.needs_pass)
        if protegido:
            # El editor trabaja sobre una copia desbloqueada.
            with abrir_pdf(ruta, contrasena) as doc:
                datos = doc.tobytes(garbage=1)
            with open(ruta, 'wb') as f:
                f.write(datos)

        sesion = SesionEdicion.crear(_raiz(), ruta, nombre_base(nombre) + '.pdf')
        ruta = None  # ya pertenece a la sesión
        registrar_log_seguro('edicion', nombre, tamano, 'exito', 'sesión creada')
        return jsonify({**_info(sesion), 'desbloqueado': protegido}), 201
    except Exception as e:
        return error_response('edicion', nombre, tamano, e)
    finally:
        eliminar_temporales(ruta)


@bp_edicion.route('/<sesion_id>', methods=['GET'])
def info(sesion_id):
    return jsonify(_info(_sesion(sesion_id)))


@bp_edicion.route('/<sesion_id>', methods=['DELETE'])
def cerrar(sesion_id):
    SesionEdicion.abrir(_raiz(), sesion_id).eliminar()
    return '', 204


@bp_edicion.route('/<sesion_id>/pdf', methods=['GET'])
def pdf_actual(sesion_id):
    sesion = _sesion(sesion_id)
    resp = send_file(sesion.ruta_actual, mimetype='application/pdf', as_attachment=False,
                     download_name=sesion.nombre, conditional=True)
    resp.headers['Cache-Control'] = 'no-store'
    return resp


# ── Edición de texto existente ────────────────────────────────────

@bp_edicion.route('/<sesion_id>/paginas/<int:pagina>/imagen', methods=['GET'])
def imagen_pagina(sesion_id, pagina):
    sesion = _sesion(sesion_id)
    try:
        dpi = entero('dpi', 110, minimo=DPI_MIN, maximo=DPI_MAX)
        with fitz.open(sesion.ruta_actual) as doc:
            if pagina >= doc.page_count:
                raise ValueError(f'Página {pagina + 1} fuera de rango (1-{doc.page_count})')
            png = doc.load_page(pagina).get_pixmap(dpi=dpi, alpha=False).tobytes('png')
        resp = send_file(io.BytesIO(png), mimetype='image/png')
        resp.headers['Cache-Control'] = 'no-store'
        return resp
    except ValueError as e:
        return jsonify({'error': sanitizar_error(str(e))}), 400


@bp_edicion.route('/<sesion_id>/paginas/<int:pagina>/campos', methods=['GET'])
def campos_pagina(sesion_id, pagina):
    sesion = _sesion(sesion_id)
    try:
        return jsonify(detectar_campos_pdf(sesion.ruta_actual, pagina))
    except ValueError as e:
        return jsonify({'error': sanitizar_error(str(e))}), 400


@bp_edicion.route('/<sesion_id>/reemplazar', methods=['POST'])
def reemplazar(sesion_id):
    sesion = _sesion(sesion_id)
    datos = request.get_json(silent=True) or {}
    try:
        pagina = datos.get('pagina')
        bbox = datos.get('bbox')
        texto_nuevo = datos.get('texto_nuevo', '')
        alineacion = datos.get('alineacion', 'izquierda')
        if not isinstance(pagina, int) or isinstance(pagina, bool):
            raise ValueError('"pagina" debe ser un entero')
        if (not isinstance(bbox, list) or len(bbox) != 4
                or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in bbox)):
            raise ValueError('"bbox" debe ser una lista de 4 números')
        if not isinstance(texto_nuevo, str):
            raise ValueError('"texto_nuevo" debe ser texto')
        if alineacion not in ALINEACIONES:
            raise ValueError(f'Alineación inválida. Opciones: {", ".join(ALINEACIONES)}')
        texto_original = datos.get('texto_original')
        if texto_original is not None and not isinstance(texto_original, str):
            raise ValueError('"texto_original" debe ser texto')

        with sesion.bloqueo():
            resultado, metadata = reemplazar_texto_pdf(
                sesion.ruta_actual, pagina, bbox, texto_nuevo,
                texto_original=texto_original, alineacion=alineacion, max_caracteres=MAX_CARACTERES,
            )
            sesion.guardar_version(resultado)

        detalle = 'texto eliminado' if metadata['eliminado'] else (
            f"fuente={metadata['fuente_usada']}; tamaño={metadata['tamano']}")
        registrar_log_seguro('edicion_texto', sesion.nombre, len(resultado), 'exito', detalle)
        return jsonify({'ok': True, 'metadata': metadata, **_info(sesion)})
    except (SesionNoEncontrada, SesionOcupada):
        raise
    except Exception as e:
        return error_response('edicion_texto', sesion.nombre, 0, e)


# ── Anotaciones (PDF.js) ──────────────────────────────────────────

@bp_edicion.route('/<sesion_id>/version', methods=['POST'])
def guardar_version(sesion_id):
    """Recibe el PDF guardado por el visor PDF.js (anotaciones, firmas, formularios, páginas)."""
    sesion = _sesion(sesion_id)
    ruta, tamano = None, 0
    try:
        ruta, _, tamano = recibir_pdf()
        with open(ruta, 'rb') as f:
            datos = f.read()
        with sesion.bloqueo():
            sesion.guardar_version(datos)
        registrar_log_seguro('edicion_anotar', sesion.nombre, tamano, 'exito', 'cambios del visor guardados')
        return jsonify({'ok': True, **_info(sesion)})
    except (SesionNoEncontrada, SesionOcupada):
        raise
    except Exception as e:
        return error_response('edicion_anotar', sesion.nombre, tamano, e)
    finally:
        eliminar_temporales(ruta)


@bp_edicion.route('/<sesion_id>/deshacer', methods=['POST'])
def deshacer(sesion_id):
    sesion = _sesion(sesion_id)
    try:
        with sesion.bloqueo():
            sesion.deshacer()
        return jsonify({'ok': True, **_info(sesion)})
    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@bp_edicion.route('/<sesion_id>/descargar', methods=['GET'])
def descargar(sesion_id):
    sesion = _sesion(sesion_id)
    aplanar = request.args.get('aplanar') == '1'
    try:
        if aplanar:
            datos = aplanar_pdf(sesion.ruta_actual)
        else:
            with open(sesion.ruta_actual, 'rb') as f:
                datos = f.read()
        registrar_log_seguro('edicion', sesion.nombre, len(datos), 'exito',
                             f'descarga v{sesion.version}; aplanar={aplanar}')
        return send_file(io.BytesIO(datos), mimetype='application/pdf', as_attachment=True,
                         download_name=nombre_base(sesion.nombre) + '_editado.pdf')
    except Exception as e:
        return error_response('edicion', sesion.nombre, 0, e)
