"""Empaquetado de varios PDF ya procesados en un ZIP (tandas de la oficina).

El navegador comprime archivo por archivo y, si se pidió un solo ZIP, manda los
resultados aquí en partes que caben en el correo. Por eso el ZIP NO recomprime:
los PDF ya vienen comprimidos y el tamaño de la parte tiene que ser predecible.
"""

import io
import zipfile

import openpyxl
import pytest
from docx import Document

from app import services

from .conftest import pdf_bytes


def _archivo(datos, nombre):
    return (io.BytesIO(datos), nombre)


def _zip(datos):
    return zipfile.ZipFile(io.BytesIO(datos))


def xlsx_bytes():
    libro = openpyxl.Workbook()
    libro.active['A1'] = 'NIT'
    out = io.BytesIO()
    libro.save(out)
    return out.getvalue()


def docx_bytes():
    doc = Document()
    doc.add_paragraph('Factura')
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


# ── services.empaquetar_en_zip ────────────────────────────────────

def test_empaqueta_cada_pdf_con_su_nombre():
    uno, dos = pdf_bytes(), pdf_bytes(paginas=2)
    with _zip(services.empaquetar_en_zip([('factura_1.pdf', uno), ('factura_2.pdf', dos)])) as zf:
        assert zf.namelist() == ['factura_1.pdf', 'factura_2.pdf']
        assert zf.read('factura_1.pdf') == uno
        assert zf.read('factura_2.pdf') == dos


def test_nombres_repetidos_no_se_pisan():
    # Escanear dos tandas seguidas deja dos "factura.pdf"; perder una sin avisar
    # seria perder un documento.
    uno, dos = pdf_bytes(), pdf_bytes(paginas=3)
    with _zip(services.empaquetar_en_zip([('factura.pdf', uno), ('factura.pdf', dos)])) as zf:
        assert zf.namelist() == ['factura.pdf', 'factura_2.pdf']
        assert zf.read('factura.pdf') == uno
        assert zf.read('factura_2.pdf') == dos


def test_nombre_con_tildes_y_ene_se_lee_igual():
    with _zip(services.empaquetar_en_zip([('facturación_niño.pdf', pdf_bytes())])) as zf:
        assert zf.namelist() == ['facturación_niño.pdf']


def test_el_nombre_pierde_la_ruta_y_los_controles():
    with _zip(services.empaquetar_en_zip([('C:\\Users\\x\\fac\ttura.pdf', pdf_bytes())])) as zf:
        assert zf.namelist() == ['factura.pdf']


def test_el_zip_no_recomprime():
    # Partir por el tope del correo exige saber cuanto pesa la parte antes de armarla.
    datos = pdf_bytes()
    with _zip(services.empaquetar_en_zip([('a.pdf', datos)])) as zf:
        info = zf.getinfo('a.pdf')
        assert info.compress_type == zipfile.ZIP_STORED
        assert info.compress_size == len(datos)


def test_sin_archivos_es_error_del_usuario():
    with pytest.raises(ValueError, match='archivo'):
        services.empaquetar_en_zip([])


# ── /api/empaquetar ───────────────────────────────────────────────

def test_empaquetar_devuelve_un_zip_con_los_pdf(client):
    uno, dos = pdf_bytes(), pdf_bytes(paginas=2)
    r = client.post('/api/empaquetar', content_type='multipart/form-data', data={
        'archivos': [_archivo(uno, 'uno.pdf'), _archivo(dos, 'dos.pdf')],
    })
    assert r.status_code == 200
    assert r.mimetype == 'application/zip'
    with _zip(r.data) as zf:
        assert zf.namelist() == ['uno.pdf', 'dos.pdf']
        assert zf.read('dos.pdf') == dos


def test_empaquetar_con_un_solo_archivo_tambien_da_zip(client):
    r = client.post('/api/empaquetar', content_type='multipart/form-data', data={
        'archivos': [_archivo(pdf_bytes(), 'sola.pdf')],
    })
    assert r.status_code == 200
    with _zip(r.data) as zf:
        assert zf.namelist() == ['sola.pdf']


def test_empaquetar_usa_el_nombre_que_le_piden(client):
    r = client.post('/api/empaquetar', content_type='multipart/form-data', data={
        'archivos': [_archivo(pdf_bytes(), 'uno.pdf')],
        'nombre': 'facturas_parte_1',
    })
    assert 'facturas_parte_1.zip' in r.headers['Content-Disposition']


def test_empaquetar_sin_nombre_usa_uno_por_defecto(client):
    r = client.post('/api/empaquetar', content_type='multipart/form-data', data={
        'archivos': [_archivo(pdf_bytes(), 'uno.pdf')],
    })
    assert '.zip' in r.headers['Content-Disposition']


def test_empaquetar_sin_archivos_avisa_a_la_persona(client):
    r = client.post('/api/empaquetar', content_type='multipart/form-data', data={})
    assert r.status_code == 400
    assert 'archivo' in r.json['error'].lower()


def test_empaquetar_rechaza_lo_que_no_es_un_pdf(client):
    r = client.post('/api/empaquetar', content_type='multipart/form-data', data={
        'archivos': [_archivo(pdf_bytes(), 'bueno.pdf'), _archivo(b'no soy un pdf', 'malo.pdf')],
    })
    assert r.status_code == 400
    assert r.json['error']


def test_empaquetar_rechaza_una_tanda_con_demasiados_archivos(client, monkeypatch):
    monkeypatch.setattr('app.routes.MAX_ARCHIVOS_EMPAQUETAR', 2)
    r = client.post('/api/empaquetar', content_type='multipart/form-data', data={
        'archivos': [_archivo(pdf_bytes(), f'{i}.pdf') for i in range(3)],
    })
    assert r.status_code == 400
    assert '2' in r.json['error']


# ── Los otros formatos que la aplicación entrega ──────────────────

def test_empaqueta_excel_y_word_con_su_extension():
    # Convertir 20 facturas a Excel en una tanda produce .xlsx; forzar .pdf en el
    # nombre dejaría archivos que no abren.
    excel, word = xlsx_bytes(), docx_bytes()
    with _zip(services.empaquetar_en_zip([('factura.xlsx', excel), ('carta.docx', word)])) as zf:
        assert zf.namelist() == ['factura.xlsx', 'carta.docx']
        assert zf.read('factura.xlsx') == excel


def test_nombres_repetidos_se_numeran_con_cualquier_extension():
    uno, dos = xlsx_bytes(), xlsx_bytes()
    with _zip(services.empaquetar_en_zip([('factura.xlsx', uno), ('factura.xlsx', dos)])) as zf:
        assert zf.namelist() == ['factura.xlsx', 'factura_2.xlsx']


def test_un_nombre_sin_extension_sale_como_pdf():
    with _zip(services.empaquetar_en_zip([('factura', pdf_bytes())])) as zf:
        assert zf.namelist() == ['factura.pdf']


def test_empaquetar_acepta_los_formatos_que_la_app_produce(client):
    r = client.post('/api/empaquetar', content_type='multipart/form-data', data={
        'archivos': [
            _archivo(pdf_bytes(), 'uno.pdf'),
            _archivo(xlsx_bytes(), 'dos.xlsx'),
            _archivo(docx_bytes(), 'tres.docx'),
        ],
    })
    assert r.status_code == 200
    with _zip(r.data) as zf:
        assert zf.namelist() == ['uno.pdf', 'dos.xlsx', 'tres.docx']


def test_empaquetar_rechaza_un_formato_que_la_app_no_entrega(client):
    r = client.post('/api/empaquetar', content_type='multipart/form-data', data={
        'archivos': [_archivo(b'texto suelto', 'notas.txt')],
    })
    assert r.status_code == 400
    assert 'PDF' in r.json['error']


def test_empaquetar_rechaza_un_excel_que_no_es_un_excel(client):
    r = client.post('/api/empaquetar', content_type='multipart/form-data', data={
        'archivos': [_archivo(b'no soy un excel', 'malo.xlsx')],
    })
    assert r.status_code == 400
    assert r.json['error']
