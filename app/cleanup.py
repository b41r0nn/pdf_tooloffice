import logging
import os
import threading
import time
from datetime import datetime, timedelta

from .sesiones import limpiar_sesiones

log = logging.getLogger(__name__)

INTERVALO_SEG = 3600  # cada hora: las sesiones de edición expiran en horas, no en días

_iniciado = False
_iniciado_lock = threading.Lock()


def limpiar_uploads(upload_folder, cleanup_days=7):
    """Elimina archivos temporales con más de N días en la carpeta uploads (no recursivo)."""
    limite = datetime.now() - timedelta(days=cleanup_days)
    eliminados = 0
    for fname in os.listdir(upload_folder):
        fpath = os.path.join(upload_folder, fname)
        if fname.startswith('.'):
            continue
        # Cada worker de gunicorn tiene su propio hilo de limpieza: otro puede
        # borrar el archivo entre listdir() y getmtime()/remove().
        try:
            if not os.path.isfile(fpath) or datetime.fromtimestamp(os.path.getmtime(fpath)) >= limite:
                continue
            os.remove(fpath)
            eliminados += 1
        except OSError:
            continue
    if eliminados:
        log.info('%d archivo(s) temporal(es) eliminado(s)', eliminados)


def _loop(upload_folder, edit_folder, cleanup_days, session_hours):
    while True:
        try:
            limpiar_uploads(upload_folder, cleanup_days)
            if edit_folder:
                limpiar_sesiones(edit_folder, session_hours)
        except Exception:
            log.exception('Error en la limpieza periódica')
        time.sleep(INTERVALO_SEG)


def start_cleanup_scheduler(upload_folder, *, edit_folder=None, cleanup_days=7, session_hours=8):
    """Arranca el hilo de limpieza como daemon (muere con la app). Solo uno por proceso."""
    global _iniciado
    with _iniciado_lock:
        if _iniciado:
            return
        _iniciado = True
    t = threading.Thread(target=_loop, args=(upload_folder, edit_folder, cleanup_days, session_hours),
                         daemon=True, name='pdf-cleanup')
    t.start()
    log.info('Limpieza iniciada (uploads: %d días, sesiones de edición: %d h)', cleanup_days, session_hours)
