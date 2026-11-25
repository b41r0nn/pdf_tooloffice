import hashlib
import time

import pymupdf as fitz
import pytest

from app import services

CLAVE = 'clave-de-prueba-2026'
MENSAJE_RESTRICCIONES = (
    'Este PDF se abre sin contraseña pero no deja imprimir ni copiar. '
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
