import os
import time

from app import cleanup


def test_limpieza_tolera_archivos_borrados_por_otro_worker(tmp_path, monkeypatch):
    viejo = time.time() - 10 * 86400
    for nombre in ('a.pdf', 'b.pdf', 'c.pdf'):
        ruta = tmp_path / nombre
        ruta.write_bytes(b'x')
        os.utime(ruta, (viejo, viejo))
    nuevo = tmp_path / 'reciente.pdf'
    nuevo.write_bytes(b'x')

    getmtime_real = os.path.getmtime

    def getmtime_con_carrera(ruta):
        if str(ruta).endswith('b.pdf'):
            os.remove(ruta)  # otro worker lo borra justo antes
            raise FileNotFoundError(ruta)
        return getmtime_real(ruta)

    monkeypatch.setattr(cleanup.os.path, 'getmtime', getmtime_con_carrera)
    cleanup.limpiar_uploads(str(tmp_path), cleanup_days=7)
    assert sorted(os.listdir(tmp_path)) == ['reciente.pdf']
