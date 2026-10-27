import os
import time

import pytest

from app.sesiones import MAX_VERSIONES, SesionEdicion, SesionNoEncontrada, SesionOcupada, limpiar_sesiones


def _crear(tmp_path, contenido=b'%PDF-1.7 v1'):
    origen = tmp_path / 'origen.pdf'
    origen.write_bytes(contenido)
    return SesionEdicion.crear(str(tmp_path / 'ses'), str(origen), 'Informe Ñ.pdf')


@pytest.mark.parametrize('sesion_id', ['../../secreto', '..', 'ABC', 'a' * 31, 'g' * 32, '', None])
def test_ids_invalidos_no_construyen_rutas(tmp_path, sesion_id):
    with pytest.raises(SesionNoEncontrada):
        SesionEdicion.abrir(str(tmp_path), sesion_id)


def test_versiones_y_deshacer(tmp_path):
    s = _crear(tmp_path)
    assert s.version == 1 and s.nombre == 'Informe Ñ.pdf'
    with s.bloqueo():
        assert s.guardar_version(b'%PDF v2') == 2
        assert s.guardar_version(b'%PDF v3') == 3
    assert open(s.ruta_actual, 'rb').read() == b'%PDF v3'
    with s.bloqueo():
        assert s.deshacer() == 2
        assert s.deshacer() == 1
        with pytest.raises(ValueError):
            s.deshacer()
    assert s.info()['puede_deshacer'] is False


def test_limite_de_versiones(tmp_path):
    s = _crear(tmp_path)
    with s.bloqueo():
        for i in range(MAX_VERSIONES + 5):
            s.guardar_version(f'%PDF {i}'.encode())
    assert len(s.versiones()) == MAX_VERSIONES


def test_bloqueo_exclusivo(tmp_path):
    s = _crear(tmp_path)
    with s.bloqueo():
        with pytest.raises(SesionOcupada):
            with s.bloqueo(espera_seg=0.3):
                pass
    with s.bloqueo(espera_seg=0.3):  # liberado
        pass


def test_limpieza_de_sesiones_expiradas(tmp_path):
    vieja = _crear(tmp_path)
    nueva = _crear(tmp_path)
    hace_un_dia = time.time() - 86400
    os.utime(os.path.join(vieja.dir, 'meta.json'), (hace_un_dia, hace_un_dia))
    assert limpiar_sesiones(str(tmp_path / 'ses'), max_horas=8) == 1
    assert not os.path.exists(vieja.dir)
    assert os.path.exists(nueva.dir)
