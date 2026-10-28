import logging
import mimetypes
import os
import threading

from dotenv import load_dotenv
from flask import Flask, jsonify

__author__    = 'Bairon Nicolas Calle Rivera'
__email__     = 'b41r0nn@gmail.com'
__version__   = '2.4.0'
__copyright__ = 'Copyright (c) 2026 Bairon Nicolas Calle Rivera'
__license__   = 'CC BY-NC 4.0 — Solo uso no comercial'

# Los blueprints importan __version__, por eso se importan después de definirlo.
from .cleanup import start_cleanup_scheduler  # noqa: E402
from .database import init_db  # noqa: E402
from .edicion_texto import precargar_fuentes  # noqa: E402
from .routes import bp  # noqa: E402
from .routes_edicion import bp_edicion  # noqa: E402

# Cargar variables del .env
load_dotenv()

# En Windows el registro puede asociar .js a text/plain; con nosniff el navegador
# no ejecutaría los scripts, y PDF.js necesita .mjs como JavaScript (módulos ES).
mimetypes.add_type('text/javascript', '.js')
mimetypes.add_type('text/javascript', '.mjs')
mimetypes.add_type('text/css', '.css')
mimetypes.add_type('application/wasm', '.wasm')
mimetypes.add_type('font/woff2', '.woff2')
mimetypes.add_type('image/svg+xml', '.svg')
mimetypes.add_type('image/x-icon', '.ico')
mimetypes.add_type('application/manifest+json', '.webmanifest')

BASE_DIR = os.path.dirname(__file__)
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
EDIT_FOLDER = os.path.join(UPLOAD_FOLDER, 'ediciones')
DATABASE_PATH = os.path.join(BASE_DIR, 'database', 'logs.db')
MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50 MB


def _env_int(nombre, defecto):
    try:
        return int(os.getenv(nombre, defecto))
    except (TypeError, ValueError):
        return defecto


def create_app(config=None):
    logging.basicConfig(
        level=getattr(logging, os.getenv('LOG_LEVEL', 'INFO').upper(), logging.INFO),
        format='%(asctime)s %(levelname)s [%(name)s] %(message)s',
    )

    app = Flask(__name__)
    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
    app.config['EDIT_FOLDER'] = EDIT_FOLDER
    app.config['DATABASE_PATH'] = DATABASE_PATH
    app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

    # Configuración desde .env
    admin_password = os.getenv('ADMIN_PASSWORD', '').strip()
    if admin_password == 'cambiar_esto_en_produccion':
        admin_password = ''  # una contraseña conocida equivale a no tener contraseña
    app.config['ADMIN_PASSWORD'] = admin_password
    app.config['LOG_RETENTION_DAYS'] = _env_int('DATABASE_LOG_RETENTION_DAYS', 30)
    app.config['UPLOAD_CLEANUP_DAYS'] = _env_int('UPLOAD_CLEANUP_DAYS', 7)
    app.config['EDIT_SESSION_HOURS'] = _env_int('EDIT_SESSION_HOURS', 8)
    app.config['DEBUG'] = os.getenv('DEBUG', 'False').lower() == 'true'
    app.config['CLEANUP_ENABLED'] = True
    if config:
        app.config.update(config)

    if not app.config['ADMIN_PASSWORD']:
        app.logger.warning('ADMIN_PASSWORD no configurada: /admin/logs queda deshabilitado')

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['EDIT_FOLDER'], exist_ok=True)
    os.makedirs(os.path.dirname(app.config['DATABASE_PATH']), exist_ok=True)

    init_db(app.config['DATABASE_PATH'], retention_days=app.config['LOG_RETENTION_DAYS'])
    if app.config['CLEANUP_ENABLED']:
        # Índice de fuentes del sistema en segundo plano: la primera edición de texto no espera.
        threading.Thread(target=precargar_fuentes, daemon=True, name='pdf-fuentes').start()
        start_cleanup_scheduler(
            app.config['UPLOAD_FOLDER'],
            edit_folder=app.config['EDIT_FOLDER'],
            cleanup_days=app.config['UPLOAD_CLEANUP_DAYS'],
            session_hours=app.config['EDIT_SESSION_HOURS'],
        )

    app.register_blueprint(bp)
    app.register_blueprint(bp_edicion)

    @app.errorhandler(413)
    def _demasiado_grande(_e):
        limite = app.config['MAX_CONTENT_LENGTH'] // (1024 * 1024)
        return jsonify({'error': f'El archivo supera el límite de {limite} MB'}), 413

    @app.url_defaults
    def _version_estaticos(endpoint, values):
        # ?v=<fecha del archivo>: tras un despliegue el navegador pide el CSS/JS nuevo
        # en vez de mezclar la plantilla nueva con estilos viejos en caché.
        # Las fuentes no: el CSS las pide sin ?v y el preload debe coincidir con esa URL.
        if (endpoint == 'static' and 'filename' in values and 'v' not in values
                and not values['filename'].startswith('fonts/')):
            try:
                values['v'] = int(os.stat(os.path.join(app.static_folder, values['filename'])).st_mtime)
            except OSError:
                pass

    @app.after_request
    def _cabeceras_seguridad(resp):
        resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
        resp.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')  # el visor PDF.js va en un iframe propio
        resp.headers.setdefault('Referrer-Policy', 'same-origin')
        return resp

    return app
