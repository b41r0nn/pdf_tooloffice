"""
routes.py — Endpoints Flask
Cada endpoint recibe archivos via multipart/form-data,
llama a services.py, registra en SQLite y retorna el archivo procesado.
"""

import io
import os
import uuid

from flask import Blueprint, current_app, jsonify, render_template, request, send_file
from werkzeug.utils import secure_filename

from .database import registrar_log
from .services import (
	cifrar_pdf,
	comprimir_pdf,
	contar_paginas,
	dividir_pdf,
	dividir_pdf_por_modo,
	docx_a_pdf,
	pdf_a_docx,
	pdf_a_xlsx,
	unir_pdfs,
	xlsx_a_pdf,
	validar_pdf,
	validar_mime_type,
	convertir_imagenes_a_pdf,
	convertir_pdf_a_jpg,
)

bp = Blueprint('main', __name__)

ALLOWED_PDF  = {'pdf'}
ALLOWED_CONV = {'pdf', 'xlsx', 'docx', 'jpg', 'jpeg', 'png', 'bmp', 'tiff', 'tif', 'webp'}


# ── Helpers ───────────────────────────────────────────────────────

def extension(filename):
	return filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''


def sanitizar_error(msg):
	"""Sanitiza mensajes de error para no exponer rutas internas."""
	# En desarrollo se pueden ver todos los detalles
	if current_app.config.get('DEBUG'):
		return msg
	
	# En producción, ocultar paths y detalles técnicos
	msg_sanitizado = msg
	msg_sanitizado = msg_sanitizado.replace(current_app.config.get('UPLOAD_FOLDER', ''), '[UPLOAD]')
	msg_sanitizado = msg_sanitizado.replace(current_app.config.get('DATABASE_PATH', ''), '[DATABASE]')
	
	# Si aún contiene rutas, usar genérico
	if '/' in msg_sanitizado or '\\' in msg_sanitizado:
		return 'Error procesando archivo. Por favor, intenta de nuevo.'
	
	return msg_sanitizado


def validar_autenticacion_admin(password_header):
	"""Valida la contraseña para acceso a admin."""
	admin_password = current_app.config.get('ADMIN_PASSWORD', 'cambiar_esto_en_produccion')
	return password_header == admin_password


def guardar_temporal(file_obj, upload_folder):
	"""Guarda un FileStorage en disco con nombre único. Retorna la ruta."""
	nombre_seguro = secure_filename(file_obj.filename)
	nombre_unico  = f"{uuid.uuid4().hex}_{nombre_seguro}"
	ruta = os.path.join(upload_folder, nombre_unico)
	file_obj.save(ruta)
	return ruta, nombre_seguro


def eliminar_temporales(*rutas):
	for ruta in rutas:
		try:
			if ruta and os.path.isfile(ruta):
				os.remove(ruta)
		except Exception:
			pass


def log_y_enviar(db_path, modulo, nombre, tamano, resultado_bytes,
				 nombre_salida, mimetype, detalle=None):
	"""Registra el log y retorna el archivo al cliente."""
	registrar_log(db_path, modulo, nombre, tamano, 'exito', detalle)
	return send_file(
		io.BytesIO(resultado_bytes),
		mimetype=mimetype,
		as_attachment=True,
		download_name=nombre_salida
	)


def error_response(db_path, modulo, nombre, tamano, msg):
	msg_sanitizado = sanitizar_error(msg)
	registrar_log(db_path, modulo, nombre, tamano, 'error', msg)  # Log completo internamente
	return jsonify({'error': msg_sanitizado}), 400  # Respuesta sanitizada al cliente


# ── Health Check ──────────────────────────────────────────────────

@bp.route('/health')
def health():
	"""Endpoint para verificar si la aplicación está viva."""
	return jsonify({
		'status':    'ok',
		'version':   '2.0.0',
		'author':    'Bairon Nicolas Calle Rivera',
		'license':   'CC BY-NC 4.0'
	}), 200


# ── Página principal ──────────────────────────────────────────────

@bp.route('/')
def index():
	return render_template('index.html')


# ── Páginas de archivos ───────────────────────────────────────────

@bp.route('/api/paginas', methods=['POST'])
def paginas():
	"""Retorna el número de páginas de un PDF."""
	upload_folder = current_app.config['UPLOAD_FOLDER']
	f = request.files.get('archivo')
	if not f or extension(f.filename) != 'pdf':
		return jsonify({'error': 'Se requiere un archivo PDF'}), 400

	ruta = None
	try:
		ruta, _ = guardar_temporal(f, upload_folder)
		
		# Validar MIME type
		es_valido, msg_error = validar_mime_type(ruta, 'pdf')
		if not es_valido:
			return jsonify({'error': 'Archivo no es un PDF válido'}), 400
		
		total = contar_paginas(ruta)
		return jsonify({'paginas': total})
	except Exception as e:
		return jsonify({'error': str(e)}), 500
	finally:
		eliminar_temporales(ruta)


# ── Unión ─────────────────────────────────────────────────────────

@bp.route('/api/union', methods=['POST'])
def union():
	upload_folder = current_app.config['UPLOAD_FOLDER']
	db_path       = current_app.config['DATABASE_PATH']
	archivos = request.files.getlist('archivos')
	contrasena = request.form.get('contrasena_union', '')

	if len(archivos) < 2:
		return jsonify({'error': 'Se necesitan al menos 2 archivos PDF'}), 400

	rutas  = []
	nombre = 'union_multiple.pdf'
	tamano = 0

	try:
		for f in archivos:
			if extension(f.filename) != 'pdf':
				return jsonify({'error': f'"{f.filename}" no es un PDF'}), 400
			ruta, _ = guardar_temporal(f, upload_folder)

			es_valido, msg_error = validar_mime_type(ruta, 'pdf')
			if not es_valido:
				eliminar_temporales(ruta)
				return jsonify({'error': f'{msg_error}'}), 400

			rutas.append(ruta)
			tamano += os.path.getsize(ruta)

		nombre_salida = request.form.get('nombre_salida', 'documento_unido.pdf')
		resultado     = unir_pdfs(rutas, contrasena=contrasena)

		# Compresión opcional post-unión
		comprimir = request.form.get('comprimir', 'false') == 'true'
		if comprimir:
			import tempfile, os as _os
			nivel = request.form.get('nivel', 'media')
			tmp   = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
			tmp.write(resultado)
			tmp.close()
			try:
				resultado = comprimir_pdf(tmp.name, nivel)
			finally:
				_os.remove(tmp.name)

		# detalle = f'comprimir={comprimir}' + (f'; nivel={request.form.get("nivel","media")}' if comprimir else '')
		# Fix: Use request.form instead of direct get if possible or ensure default
		nivel_comp = request.form.get("nivel", "media")
		detalle = f'comprimir={comprimir}' + (f'; nivel={nivel_comp}' if comprimir else '')
		return log_y_enviar(db_path, 'union', nombre_salida, tamano,
							resultado, nombre_salida, 'application/pdf',
							detalle=detalle)
	except Exception as e:
		return error_response(db_path, 'union', 'union_multiple.pdf', tamano, str(e))
	finally:
		eliminar_temporales(*rutas)


# ── División ──────────────────────────────────────────────────────

@bp.route('/api/division', methods=['POST'])
def division():
	upload_folder = current_app.config['UPLOAD_FOLDER']
	db_path       = current_app.config['DATABASE_PATH']
	f = request.files.get('archivo')

	if not f or extension(f.filename) != 'pdf':
		return jsonify({'error': 'Se requiere un archivo PDF'}), 400

	ruta, nombre = guardar_temporal(f, upload_folder)
	tamano = os.path.getsize(ruta)

	try:
		# Validar MIME type y estructura PDF
		es_valido, msg_error = validar_mime_type(ruta, 'pdf')
		if not es_valido:
			return jsonify({'error': 'Archivo no es un PDF válido'}), 400
		
		modo = request.form.get('modo', 'rango')
		if modo == 'rango':
			inicio = int(request.form.get('inicio', 1))
			fin    = int(request.form.get('fin', 1))
			resultado = dividir_pdf(ruta, inicio, fin)
			nombre_salida = f'paginas_{inicio}_a_{fin}.pdf'
			mimetype = 'application/pdf'
			detalle = f'modo=rango; paginas {inicio}-{fin}'
		else:
			resultado, tipo = dividir_pdf_por_modo(ruta, modo)
			if tipo == 'zip':
				nombre_salida = 'division_todas.zip'
				mimetype = 'application/zip'
			else:
				nombre_salida = f'division_{modo}.pdf'
				mimetype = 'application/pdf'
			detalle = f'modo={modo}'

		return log_y_enviar(db_path, 'division', nombre, tamano,
							resultado, nombre_salida, mimetype,
							detalle=detalle)
	except ValueError as e:
		return error_response(db_path, 'division', nombre, tamano, str(e))
	except Exception as e:
		return error_response(db_path, 'division', nombre, tamano, str(e))
	finally:
		eliminar_temporales(ruta)


# ── Conversión ────────────────────────────────────────────────────

_MIMETYPES = {
	'pdf':  'application/pdf',
	'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
	'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
}

@bp.route('/api/conversion', methods=['POST'])
def conversion():
	upload_folder = current_app.config['UPLOAD_FOLDER']
	db_path       = current_app.config['DATABASE_PATH']
	direccion     = request.form.get('direccion', '')

	# Caso especial: imagen_a_pdf recibe múltiples archivos
	if direccion == 'imagen_a_pdf':
		archivos = request.files.getlist('archivos')
		if not archivos:
			return jsonify({'error': 'No se enviaron imágenes'}), 400
		
		rutas_imagenes = []
		try:
			for img_file in archivos:
				if img_file.filename:
					ruta_img, _ = guardar_temporal(img_file, upload_folder)
					rutas_imagenes.append(ruta_img)
			
			if not rutas_imagenes:
				return jsonify({'error': 'No se procesaron imágenes válidas'}), 400

			resultado = convertir_imagenes_a_pdf(rutas_imagenes)
			nombre_salida = 'resultado.pdf'
			registrar_log(db_path, 'conversion', f'{len(rutas_imagenes)} imágenes', 0, 'exito', f'{len(rutas_imagenes)} imágenes')
			return send_file(
				io.BytesIO(resultado),
				mimetype='application/pdf',
				as_attachment=True,
				download_name=nombre_salida
			)
		except Exception as e:
			return error_response(db_path, 'conversion', 'múltiples imágenes', 0, str(e))
		finally:
			eliminar_temporales(*rutas_imagenes)

	# Casos estándar: requieren un único archivo
	f = request.files.get('archivo')
	if not f:
		return jsonify({'error': 'Se requiere un archivo'}), 400

	ext_entrada = extension(f.filename)
	if ext_entrada not in ALLOWED_CONV:
		return jsonify({'error': 'Formato no permitido'}), 400

	ruta, nombre = guardar_temporal(f, upload_folder)
	tamano = os.path.getsize(ruta)

	try:
		if direccion == 'pdf_a_jpg':
			# Validar MIME type del archivo de entrada
			es_valido, msg_error = validar_mime_type(ruta, ext_entrada)
			if not es_valido:
				return jsonify({'error': 'Archivo de entrada no es válido'}), 400
			
			import fitz
			doc = fitz.open(ruta)
			paginas = doc.page_count
			doc.close()
			
			resultado = convertir_pdf_a_jpg(ruta)
			if paginas == 1:
				mimetype = 'image/jpeg'
				nombre_salida = nombre.rsplit('.', 1)[0] + '_convertido.jpg'
			else:
				mimetype = 'application/zip'
				nombre_salida = nombre.rsplit('.', 1)[0] + '_convertido.zip'
				
			return log_y_enviar(db_path, 'conversion', nombre, tamano,
								resultado, nombre_salida, mimetype,
								detalle=f'{paginas} páginas')
								
		# Validar MIME type para las demás conversiones
		es_valido, msg_error = validar_mime_type(ruta, ext_entrada)
		if not es_valido:
			return jsonify({'error': 'Archivo de entrada no es válido'}), 400
		
		if direccion == 'pdf-docx':
			resultado   = pdf_a_docx(ruta)
			ext_salida  = 'docx'
		elif direccion == 'pdf-xlsx':
			resultado   = pdf_a_xlsx(ruta)
			ext_salida  = 'xlsx'
		elif direccion == 'docx-pdf':
			resultado   = docx_a_pdf(ruta)
			ext_salida  = 'pdf'
		elif direccion == 'xlsx-pdf':
			resultado   = xlsx_a_pdf(ruta)
			ext_salida  = 'pdf'
		else:
			return jsonify({'error': f'Dirección desconocida: {direccion}'}), 400

		nombre_salida = nombre.rsplit('.', 1)[0] + '_convertido.' + ext_salida
		return log_y_enviar(db_path, 'conversion', nombre, tamano,
							resultado, nombre_salida, _MIMETYPES[ext_salida],
							detalle=direccion)
	except Exception as e:
		return error_response(db_path, 'conversion', nombre, tamano, str(e))
	finally:
		eliminar_temporales(ruta)


# ── Compresión ────────────────────────────────────────────────────

@bp.route('/api/compresion', methods=['POST'])
def compresion():
	upload_folder = current_app.config['UPLOAD_FOLDER']
	db_path       = current_app.config['DATABASE_PATH']
	f = request.files.get('archivo')

	if not f or extension(f.filename) != 'pdf':
		return jsonify({'error': 'Se requiere un archivo PDF'}), 400

	ruta, nombre = guardar_temporal(f, upload_folder)
	tamano = os.path.getsize(ruta)

	try:
		# Validar MIME type y estructura PDF
		es_valido, msg_error = validar_mime_type(ruta, 'pdf')
		if not es_valido:
			return jsonify({'error': 'Archivo no es un PDF válido'}), 400

		# Validar nivel de compresión
		nivel = request.form.get('nivel', 'media')
		niveles_validos = ['baja', 'media', 'alta', 'ultra']
		if nivel not in niveles_validos:
			return jsonify({'error': f'Nivel inválido. Opciones: {", ".join(niveles_validos)}'}), 400

		resultado = comprimir_pdf(ruta, nivel)
		nombre_salida = nombre.rsplit('.', 1)[0] + '_comprimido.pdf'
		return log_y_enviar(db_path, 'compresion', nombre, tamano,
							resultado, nombre_salida, 'application/pdf',
							detalle=f'nivel={nivel}')
	except Exception as e:
		return error_response(db_path, 'compresion', nombre, tamano, str(e))
	finally:
		eliminar_temporales(ruta)

@bp.route('/api/cifrado', methods=['POST'])
def cifrado():
	upload_folder = current_app.config['UPLOAD_FOLDER']
	db_path       = current_app.config['DATABASE_PATH']
	f = request.files.get('archivo')

	if not f or extension(f.filename) != 'pdf':
		return jsonify({'error': 'Se requiere un archivo PDF'}), 400

	ruta, nombre = guardar_temporal(f, upload_folder)
	tamano = os.path.getsize(ruta)

	try:
		# Validar MIME type y estructura PDF
		es_valido, msg_error = validar_mime_type(ruta, 'pdf')
		if not es_valido:
			return jsonify({'error': 'Archivo no es un PDF válido'}), 400
		
		contrasena = request.form.get('contrasena', '')
		confirmar  = request.form.get('confirmar', '')

		if not contrasena:
			return jsonify({'error': 'La contraseña no puede estar vacía'}), 400
		if contrasena != confirmar:
			return jsonify({'error': 'Las contraseñas no coinciden'}), 400

		resultado = cifrar_pdf(ruta, contrasena)
		nombre_salida = nombre.rsplit('.', 1)[0] + '_cifrado.pdf'
		return log_y_enviar(db_path, 'cifrado', nombre, tamano,
							resultado, nombre_salida, 'application/pdf')
	except Exception as e:
		return error_response(db_path, 'cifrado', nombre, tamano, str(e))
	finally:
		eliminar_temporales(ruta)


# ── Logs (acceso protegido con contraseña) ────────────────────────

@bp.route('/admin/logs')
def ver_logs():
	"""Vista de logs — requiere contraseña."""
	from .database import obtener_logs
	
	# Verificar autenticación
	admin_password = request.headers.get('X-Admin-Password', '')
	if not validar_autenticacion_admin(admin_password):
		return jsonify({'error': 'No autorizado'}), 401
	
	db_path = current_app.config['DATABASE_PATH']
	logs = obtener_logs(db_path, limit=500)

	# Construye tabla HTML simple
	filas = ''.join(
		f"<tr><td>{r['id']}</td><td>{r['fecha']}</td><td>{r['hora']}</td>"
		f"<td>{r['modulo']}</td><td>{r['archivo']}</td>"
		f"<td>{r['tamano_kb']} KB</td><td>{r['resultado']}</td>"
		f"<td>{r['detalle'] or ''}</td></tr>"
		for r in logs
	)
	html = f"""<!DOCTYPE html><html><head><meta charset=\"UTF-8\"> 
	<title>Logs — PDF ToolOffice</title>
	<style>
	  body{{font-family:sans-serif;padding:24px;background:#f5f7fc}}
	  h2{{color:#0f1e3d;margin-bottom:16px}}
	  table{{border-collapse:collapse;width:100%;font-size:13px}}
	  th{{background:#1b4fd8;color:white;padding:8px 12px;text-align:left}}
	  td{{padding:7px 12px;border-bottom:1px solid #dde6f5}}
	  tr:nth-child(even){{background:#ebf2ff}}
	  .ok{{color:#16a34a;font-weight:600}}
	  .err{{color:#dc2626;font-weight:600}}
	</style></head><body>
	<h2>Registro de operaciones — PDF ToolOffice</h2>
	<p style="color:#4b5680;margin-bottom:16px">Últimas 500 operaciones · acceso protegido</p>
	<table>
	  <thead><tr>
		<th>#</th><th>Fecha</th><th>Hora</th><th>Módulo</th>
		<th>Archivo</th><th>Tamaño</th><th>Resultado</th><th>Detalle</th>
	  </tr></thead>
	  <tbody>{filas}</tbody>
	</table>
	</body></html>"""
	return html

# ── Exportar logs a Excel (acceso protegido) ──────────────────────

@bp.route('/admin/logs/export')
def exportar_logs():
    """Descarga todos los logs en un único Excel con histórico completo."""
    admin_password = request.headers.get('X-Admin-Password', '')
    if not validar_autenticacion_admin(admin_password):
        return jsonify({'error': 'No autorizado'}), 401

    from .database import exportar_logs_excel
    from datetime import datetime
    db_path  = current_app.config['DATABASE_PATH']
    datos    = exportar_logs_excel(db_path)
    filename = f'logs_pdf_tooloffice_{datetime.now():%Y%m%d_%H%M}.xlsx'
    return send_file(
        io.BytesIO(datos),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )
