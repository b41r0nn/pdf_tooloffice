import hashlib
import io
import logging
import time

import pymupdf as fitz
import pytest

from app import services
from app.database import obtener_logs

CLAVE = 'clave-de-prueba-2026'
MENSAJE_RESTRICCIONES = (
    'Este PDF se abre sin contraseña pero tiene restricciones (imprimir, copiar o editar). '
    'Marca «Quitar también las restricciones» para quitárselas.'
)


def pdf_sin_cifrar(paginas=1):
    """PDF de prueba sin contraseña ni restricciones, con texto y metadatos."""
    with fitz.open() as doc:
        for i in range(paginas):
            pagina = doc.new_page()
            pagina.insert_text((72, 100), f'Pagina {i + 1} del documento de prueba', fontsize=12)
        doc.set_metadata({'title': 'Titulo original', 'author': 'REDIHOS'})
        return doc.tobytes()


def pdf_con_contrasena(clave=CLAVE, paginas=1):
    """PDF que pide contraseña para abrirse (usuario y dueño con la misma clave)."""
    with fitz.open() as doc:
        for i in range(paginas):
            pagina = doc.new_page()
            pagina.insert_text((72, 100), f'Pagina {i + 1} del documento de prueba', fontsize=12)
        doc.set_metadata({'title': 'Titulo original', 'author': 'REDIHOS'})
        return doc.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, user_pw=clave, owner_pw=clave)


def pdf_solo_restringido():
    """Se abre sin contraseña, pero solo con permiso de accesibilidad (sin imprimir ni copiar)."""
    with fitz.open() as doc:
        pagina = doc.new_page()
        pagina.insert_text((72, 100), 'Texto que no se puede copiar', fontsize=12)
        return doc.tobytes(
            encryption=fitz.PDF_ENCRYPT_AES_256,
            owner_pw='duenio-2026',
            user_pw='',
            permissions=int(fitz.PDF_PERM_ACCESSIBILITY),
        )


def pdf_escaneado_con_contrasena(clave=CLAVE):
    """Página con una imagen y ningún texto, como un escaneo, que pide contraseña."""
    with fitz.open() as doc:
        pagina = doc.new_page(width=300, height=300)
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 200, 200), False)
        pix.set_rect(pix.irect, (200, 200, 200))
        pagina.insert_image(pagina.rect, pixmap=pix)
        return doc.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, user_pw=clave, owner_pw=clave)


def pdf_con_contrasena_y_restringido(clave=CLAVE):
    """Pide contraseña para abrirse y, además, va sin permiso de imprimir ni copiar."""
    with fitz.open() as doc:
        pagina = doc.new_page()
        pagina.insert_text((72, 100), 'Pagina 1 del documento de prueba', fontsize=12)
        return doc.tobytes(
            encryption=fitz.PDF_ENCRYPT_AES_256,
            user_pw=clave,
            owner_pw='duenio-2026',
            permissions=int(fitz.PDF_PERM_ACCESSIBILITY),
        )


def _pdf_con_textos(textos, **guardado):
    with fitz.open() as doc:
        for texto in textos:
            doc.new_page().insert_text((72, 100), texto, fontsize=12)
        return doc.tobytes(**guardado)


def _en_archivo(tmp_path, datos, nombre='entrada.pdf'):
    ruta = tmp_path / nombre
    ruta.write_bytes(datos)
    return str(ruta)


def _abrir(datos, clave=''):
    doc = fitz.open(stream=datos, filetype='pdf')
    if doc.needs_pass:
        assert doc.authenticate(clave), 'la clave de prueba no abre el resultado'
    return doc


def _textos(datos, clave=''):
    with _abrir(datos, clave) as doc:
        return [pagina.get_text() for pagina in doc]


def _libre(datos):
    """El resultado se abre sin contraseña y sin restricciones (predicado, no el valor -4)."""
    with fitz.open(stream=datos, filetype='pdf') as doc:
        return doc.needs_pass == 0 and not services.tiene_restricciones(doc)


def test_con_la_contrasena_correcta_el_pdf_sale_sin_contrasena(tmp_path):
    ruta = _en_archivo(tmp_path, pdf_con_contrasena())

    resultado = services.desbloquear_pdf(ruta, CLAVE)

    with fitz.open(stream=resultado, filetype='pdf') as doc:
        assert doc.needs_pass == 0
        assert not services.tiene_restricciones(doc)


def test_el_contenido_y_las_paginas_se_conservan(tmp_path):
    original = pdf_con_contrasena(paginas=3)
    ruta = _en_archivo(tmp_path, original)

    resultado = services.desbloquear_pdf(ruta, CLAVE)

    assert _textos(resultado) == _textos(original, CLAVE)
    with fitz.open(stream=resultado, filetype='pdf') as doc:
        assert doc.page_count == 3


def test_los_metadatos_se_conservan(tmp_path):
    ruta = _en_archivo(tmp_path, pdf_con_contrasena())

    resultado = services.desbloquear_pdf(ruta, CLAVE)

    with fitz.open(stream=resultado, filetype='pdf') as doc:
        assert doc.metadata['title'] == 'Titulo original'
        assert doc.metadata['author'] == 'REDIHOS'


def test_la_contrasena_incorrecta_avisa_sin_tocar_nada(tmp_path):
    ruta = _en_archivo(tmp_path, pdf_con_contrasena())
    clave_probada = 'otra-clave-equivocada'

    with pytest.raises(ValueError) as error:
        services.desbloquear_pdf(ruta, clave_probada)

    assert 'contraseña' in str(error.value)
    assert clave_probada not in str(error.value)


def test_la_contrasena_vacia_en_un_pdf_que_la_pide_da_el_mismo_aviso(tmp_path):
    ruta = _en_archivo(tmp_path, pdf_con_contrasena())

    with pytest.raises(ValueError, match='contraseña'):
        services.desbloquear_pdf(ruta, '')


def test_la_contrasena_con_tildes_y_espacios_funciona_tal_cual(tmp_path):
    clave = ' Ñandú 2026 '
    ruta = _en_archivo(tmp_path, pdf_con_contrasena(clave=clave))

    resultado = services.desbloquear_pdf(ruta, clave)

    assert _libre(resultado)


def test_un_pdf_sin_proteccion_dice_que_no_hay_nada_que_quitar(tmp_path):
    ruta = _en_archivo(tmp_path, pdf_sin_cifrar())

    with pytest.raises(ValueError, match='no hay nada que quitar'):
        services.desbloquear_pdf(ruta)


def test_un_pdf_solo_restringido_no_se_toca_si_no_se_pide(tmp_path):
    ruta = _en_archivo(tmp_path, pdf_solo_restringido())

    with pytest.raises(ValueError) as error:
        services.desbloquear_pdf(ruta, quitar_restricciones=False)

    assert str(error.value) == MENSAJE_RESTRICCIONES


def test_un_pdf_solo_restringido_se_libera_si_se_pide(tmp_path):
    ruta = _en_archivo(tmp_path, pdf_solo_restringido())

    resultado = services.desbloquear_pdf(ruta, quitar_restricciones=True)

    assert _libre(resultado)


def test_un_pdf_escaneado_sin_texto_se_desbloquea_igual(tmp_path):
    original = pdf_escaneado_con_contrasena()
    ruta = _en_archivo(tmp_path, original)

    resultado = services.desbloquear_pdf(ruta, CLAVE)

    assert _libre(resultado)
    assert _textos(resultado) == _textos(original, CLAVE) == ['']


def test_un_pdf_de_muchas_paginas_se_desbloquea_en_un_tiempo_razonable(tmp_path):
    ruta = _en_archivo(tmp_path, pdf_con_contrasena(paginas=200))

    inicio = time.monotonic()
    resultado = services.desbloquear_pdf(ruta, CLAVE)
    duracion = time.monotonic() - inicio

    assert duracion < 30
    with fitz.open(stream=resultado, filetype='pdf') as doc:
        assert doc.page_count == 200


def test_el_archivo_original_no_cambia(tmp_path):
    ruta = _en_archivo(tmp_path, pdf_con_contrasena())
    antes = hashlib.sha256(open(ruta, 'rb').read()).hexdigest()

    services.desbloquear_pdf(ruta, CLAVE)

    despues = hashlib.sha256(open(ruta, 'rb').read()).hexdigest()
    assert antes == despues


def test_con_contrasena_y_restricciones_sin_marcar_la_casilla_sale_libre(tmp_path):
    # Decisión del diseño aprobado: los permisos viven en el cifrado y se van con la contraseña.
    ruta = _en_archivo(tmp_path, pdf_con_contrasena_y_restringido())

    resultado = services.desbloquear_pdf(ruta, CLAVE, quitar_restricciones=False)

    assert _libre(resultado)


def test_comprobacion_rechaza_resultado_con_distinto_numero_de_paginas():
    original = pdf_sin_cifrar(paginas=2)
    with fitz.open(stream=original, filetype='pdf') as doc_original:
        with pytest.raises(ValueError, match='no coincide'):
            services._comprobar_desbloqueo(pdf_sin_cifrar(paginas=1), doc_original)


def test_comprobacion_rechaza_resultado_que_no_se_puede_reabrir():
    with fitz.open(stream=pdf_sin_cifrar(), filetype='pdf') as doc_original:
        with pytest.raises(ValueError, match='no coincide'):
            services._comprobar_desbloqueo(b'esto no es un pdf', doc_original)


def test_comprobacion_rechaza_texto_distinto_en_una_pagina():
    original = _pdf_con_textos(['Pagina 1 del documento', 'Pagina 2 del documento'])
    alterado = _pdf_con_textos(['Pagina 1 del documento', 'Pagina 2 alterada'])
    with fitz.open(stream=original, filetype='pdf') as doc_original:
        with pytest.raises(ValueError, match='no coincide'):
            services._comprobar_desbloqueo(alterado, doc_original)


def test_comprobacion_rechaza_resultado_que_sigue_restringido():
    original = _pdf_con_textos(['Pagina 1 del documento'])
    restringido = _pdf_con_textos(
        ['Pagina 1 del documento'],
        encryption=fitz.PDF_ENCRYPT_AES_256,
        owner_pw='duenio-2026',
        user_pw='',
        permissions=int(fitz.PDF_PERM_ACCESSIBILITY),
    )
    with fitz.open(stream=original, filetype='pdf') as doc_original:
        with pytest.raises(ValueError, match='no coincide'):
            services._comprobar_desbloqueo(restringido, doc_original)


def test_comprobacion_registra_el_motivo_sin_contenido_del_pdf(caplog):
    original = pdf_sin_cifrar(paginas=2)
    with fitz.open(stream=original, filetype='pdf') as doc_original:
        with caplog.at_level(logging.ERROR, logger='app.services'):
            with pytest.raises(ValueError):
                services._comprobar_desbloqueo(pdf_sin_cifrar(paginas=1), doc_original)

    assert 'páginas esperadas 2, obtenidas 1' in caplog.text
    assert 'Pagina 1' not in caplog.text


# ── Endpoint /api/desbloqueo ──────────────────────────────────────

CLAVE_MALA = 'clave-mala-secreta-998'


def _archivo(datos, nombre='contrato.pdf'):
    return (io.BytesIO(datos), nombre)


def test_desbloqueo_devuelve_un_pdf_que_abre_sin_contrasena(client):
    r = client.post('/api/desbloqueo', data={'archivo': _archivo(pdf_con_contrasena()),
                                             'contrasena': CLAVE})

    assert r.status_code == 200
    assert r.mimetype == 'application/pdf'
    assert 'contrato_sin_contrasena.pdf' in r.headers['Content-Disposition']
    with fitz.open(stream=r.data, filetype='pdf') as doc:
        assert doc.needs_pass == 0


def test_desbloqueo_con_contrasena_mala_da_400_con_mensaje_claro(client):
    r = client.post('/api/desbloqueo', data={'archivo': _archivo(pdf_con_contrasena()),
                                             'contrasena': CLAVE_MALA})

    assert r.status_code == 400
    assert 'contraseña' in r.get_json()['error']
    assert CLAVE_MALA not in r.get_data(as_text=True)


def test_desbloqueo_con_contrasena_vacia_en_un_pdf_que_la_pide_da_400(client):
    # El caso más probable del primer día: se sube el PDF y se olvida escribir la contraseña
    r = client.post('/api/desbloqueo', data={'archivo': _archivo(pdf_con_contrasena()),
                                             'contrasena': ''})

    assert r.status_code == 400
    assert 'contraseña' in r.get_json()['error']


def test_desbloqueo_sin_archivo_da_400(client):
    r = client.post('/api/desbloqueo', data={'contrasena': CLAVE})

    assert r.status_code == 400
    assert 'PDF' in r.get_json()['error']


def test_desbloqueo_de_un_pdf_restringido_necesita_la_casilla(client):
    sin_casilla = client.post('/api/desbloqueo', data={'archivo': _archivo(pdf_solo_restringido())})

    assert sin_casilla.status_code == 400
    assert sin_casilla.get_json()['error'] == MENSAJE_RESTRICCIONES

    con_casilla = client.post('/api/desbloqueo', data={'archivo': _archivo(pdf_solo_restringido()),
                                                       'quitar_restricciones': 'true'})

    assert con_casilla.status_code == 200
    assert _libre(con_casilla.data)


def test_el_log_no_guarda_la_contrasena(client, app):
    client.post('/api/desbloqueo', data={'archivo': _archivo(pdf_con_contrasena()),
                                         'contrasena': CLAVE})
    client.post('/api/desbloqueo', data={'archivo': _archivo(pdf_con_contrasena(), 'fallo.pdf'),
                                         'contrasena': CLAVE_MALA})

    filas = obtener_logs(app.config['DATABASE_PATH'])
    modulos = {fila['modulo'] for fila in filas}
    assert 'desbloqueo' in modulos
    for fila in filas:
        for valor in fila.values():
            assert CLAVE not in str(valor)
            assert CLAVE_MALA not in str(valor)


def test_el_error_queda_en_el_log_con_el_nombre_del_archivo(client, app):
    client.post('/api/desbloqueo', data={'archivo': _archivo(pdf_con_contrasena(), 'fallo.pdf'),
                                         'contrasena': CLAVE_MALA})

    fila = obtener_logs(app.config['DATABASE_PATH'], limit=1)[0]
    assert fila['modulo'] == 'desbloqueo'
    assert fila['resultado'] == 'error'
    assert fila['archivo'] == 'fallo.pdf'


def test_un_fallo_interno_da_500_generico_y_no_guarda_la_contrasena(client, app, monkeypatch):
    def fallo(*args, **kwargs):
        raise RuntimeError('fallo interno')
    monkeypatch.setattr('app.routes.desbloquear_pdf', fallo)

    r = client.post('/api/desbloqueo', data={'archivo': _archivo(pdf_con_contrasena()),
                                             'contrasena': CLAVE})

    assert r.status_code == 500
    assert 'Error procesando el archivo' in r.get_json()['error']
    assert 'fallo interno' not in r.get_data(as_text=True)
    for fila in obtener_logs(app.config['DATABASE_PATH']):
        for valor in fila.values():
            assert CLAVE not in str(valor)


def test_el_detalle_registra_la_casilla_pedida_no_el_resultado(client, app):
    # Con contraseña y restricciones, sin casilla: el archivo sale libre, pero el detalle
    # dice lo que se pidió (casilla no marcada), no lo que ocurrió.
    r = client.post('/api/desbloqueo', data={'archivo': _archivo(pdf_con_contrasena_y_restringido()),
                                             'contrasena': CLAVE})

    assert r.status_code == 200
    assert _libre(r.data)
    fila = obtener_logs(app.config['DATABASE_PATH'], limit=1)[0]
    assert 'casilla de restricciones: no' in fila['detalle']
    assert 'quitar restricciones' not in fila['detalle']


def _comprobar_que_caplog_ve_app_routes(caplog):
    # Control positivo: sin esto, las pruebas de abajo pasarían vacías si el logger de
    # las rutas no llegara a caplog.
    logging.getLogger('app.routes').info('control-positivo-caplog')
    assert 'control-positivo-caplog' in caplog.text


def test_la_contrasena_no_aparece_en_los_registros_de_python_en_exito(client, caplog):
    caplog.set_level(logging.DEBUG)
    _comprobar_que_caplog_ve_app_routes(caplog)

    r = client.post('/api/desbloqueo', data={'archivo': _archivo(pdf_con_contrasena()),
                                             'contrasena': CLAVE})

    assert r.status_code == 200
    assert CLAVE not in caplog.text


def test_la_contrasena_no_aparece_en_los_registros_de_python_en_fallo(client, caplog):
    caplog.set_level(logging.DEBUG)
    _comprobar_que_caplog_ve_app_routes(caplog)

    r = client.post('/api/desbloqueo', data={'archivo': _archivo(pdf_con_contrasena()),
                                             'contrasena': CLAVE_MALA})

    assert r.status_code == 400
    assert CLAVE_MALA not in caplog.text
    assert CLAVE_MALA not in r.get_data(as_text=True)
