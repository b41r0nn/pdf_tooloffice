"""
sesiones.py — Sesiones de edición persistentes en disco

Cada sesión es una carpeta <raiz>/<id>/ con:
  meta.json     nombre original y fechas
  v0001.pdf     versión original
  v0002.pdf ... una versión por cada cambio guardado (permite deshacer)

El id es un uuid4 en hex y se valida siempre con una expresión regular antes
de construir cualquier ruta (evita path traversal con ids como '../../x').
El bloqueo usa un archivo creado con O_EXCL para que funcione también con
varios workers de gunicorn (procesos distintos).
"""

import json
import logging
import os
import re
import shutil
import time
import uuid
from contextlib import contextmanager
from datetime import datetime

log = logging.getLogger(__name__)

ID_VALIDO = re.compile(r'^[0-9a-f]{32}$')
_RE_VERSION = re.compile(r'^v(\d{4})\.pdf$')
MAX_VERSIONES = 30
BLOQUEO_EXPIRA_SEG = 120


class SesionNoEncontrada(LookupError):
    pass


class SesionOcupada(RuntimeError):
    pass


class SesionEdicion:
    def __init__(self, raiz, sesion_id):
        if not isinstance(sesion_id, str) or not ID_VALIDO.match(sesion_id):
            raise SesionNoEncontrada('Sesión de edición no encontrada')
        self.id = sesion_id
        self.dir = os.path.join(raiz, sesion_id)

    # ── Creación / apertura ────────────────────────────────────────

    @classmethod
    def crear(cls, raiz, ruta_pdf, nombre):
        """Mueve ruta_pdf a una nueva sesión como versión 1."""
        os.makedirs(raiz, exist_ok=True)
        sesion = cls(raiz, uuid.uuid4().hex)
        os.makedirs(sesion.dir)
        shutil.move(ruta_pdf, sesion._ruta_version(1))
        ahora = datetime.now().isoformat(timespec='seconds')
        sesion._escribir_meta({'nombre': nombre, 'creada': ahora})
        return sesion

    @classmethod
    def abrir(cls, raiz, sesion_id):
        sesion = cls(raiz, sesion_id)
        if not os.path.isfile(os.path.join(sesion.dir, 'meta.json')):
            raise SesionNoEncontrada('Sesión de edición no encontrada o expirada')
        return sesion

    # ── Metadatos ──────────────────────────────────────────────────

    def _escribir_meta(self, meta):
        tmp = os.path.join(self.dir, 'meta.json.tmp')
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False)
        os.replace(tmp, os.path.join(self.dir, 'meta.json'))

    @property
    def meta(self):
        with open(os.path.join(self.dir, 'meta.json'), encoding='utf-8') as f:
            return json.load(f)

    @property
    def nombre(self):
        return self.meta.get('nombre') or 'documento.pdf'

    def tocar(self):
        """Renueva la expiración de la sesión."""
        try:
            os.utime(os.path.join(self.dir, 'meta.json'))
        except OSError:
            pass

    # ── Versiones ──────────────────────────────────────────────────

    def _ruta_version(self, n):
        return os.path.join(self.dir, f'v{n:04d}.pdf')

    def versiones(self):
        nums = []
        for nombre in os.listdir(self.dir):
            m = _RE_VERSION.match(nombre)
            if m:
                nums.append(int(m.group(1)))
        return sorted(nums)

    @property
    def version(self):
        versiones = self.versiones()
        if not versiones:
            raise SesionNoEncontrada('La sesión no tiene versiones')
        return versiones[-1]

    @property
    def ruta_actual(self):
        return self._ruta_version(self.version)

    def info(self):
        versiones = self.versiones()
        return {
            'id': self.id,
            'nombre': self.nombre,
            'version': versiones[-1],
            'puede_deshacer': len(versiones) > 1,
        }

    @contextmanager
    def bloqueo(self, espera_seg=15):
        ruta = os.path.join(self.dir, '.lock')
        limite = time.monotonic() + espera_seg
        while True:
            try:
                fd = os.open(ruta, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                break
            except FileExistsError:
                try:
                    if time.time() - os.path.getmtime(ruta) > BLOQUEO_EXPIRA_SEG:
                        os.remove(ruta)  # bloqueo huérfano de un proceso caído
                        continue
                except FileNotFoundError:
                    continue
                if time.monotonic() > limite:
                    raise SesionOcupada('El documento está procesando otro cambio. Inténtalo de nuevo.')
                time.sleep(0.1)
        try:
            yield
        finally:
            try:
                os.remove(ruta)
            except FileNotFoundError:
                pass

    def guardar_version(self, datos):
        """Guarda bytes como nueva versión. Debe llamarse dentro de bloqueo()."""
        nueva = self.version + 1
        tmp = os.path.join(self.dir, f'.v{nueva:04d}.tmp')
        with open(tmp, 'wb') as f:
            f.write(datos)
        os.replace(tmp, self._ruta_version(nueva))
        for vieja in self.versiones()[:-MAX_VERSIONES]:
            try:
                os.remove(self._ruta_version(vieja))
            except FileNotFoundError:
                pass
        self.tocar()
        return nueva

    def deshacer(self):
        """Descarta la última versión. Debe llamarse dentro de bloqueo()."""
        versiones = self.versiones()
        if len(versiones) < 2:
            raise ValueError('No hay cambios para deshacer')
        os.remove(self._ruta_version(versiones[-1]))
        self.tocar()
        return versiones[-2]

    def eliminar(self):
        shutil.rmtree(self.dir, ignore_errors=True)


def limpiar_sesiones(raiz, max_horas):
    """Elimina sesiones sin actividad en las últimas max_horas. Retorna cuántas borró."""
    if not os.path.isdir(raiz):
        return 0
    limite = time.time() - max_horas * 3600
    borradas = 0
    for nombre in os.listdir(raiz):
        carpeta = os.path.join(raiz, nombre)
        if not ID_VALIDO.match(nombre) or not os.path.isdir(carpeta):
            continue
        meta = os.path.join(carpeta, 'meta.json')
        try:
            ultima = os.path.getmtime(meta if os.path.exists(meta) else carpeta)
        except OSError:
            continue
        if ultima < limite:
            shutil.rmtree(carpeta, ignore_errors=True)
            borradas += 1
    if borradas:
        log.info('%d sesión(es) de edición expirada(s) eliminada(s)', borradas)
    return borradas
