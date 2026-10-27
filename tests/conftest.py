import os
import sys

import pymupdf as fitz
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from app.edicion_texto import _buscar_fuente_sistema  # noqa: E402

ADMIN = 'clave-admin-de-pruebas-123'


@pytest.fixture
def app(tmp_path):
    return create_app({
        'TESTING': True,
        'UPLOAD_FOLDER': str(tmp_path / 'uploads'),
        'EDIT_FOLDER': str(tmp_path / 'uploads' / 'ediciones'),
        'DATABASE_PATH': str(tmp_path / 'db' / 'logs.db'),
        'CLEANUP_ENABLED': False,
        'ADMIN_PASSWORD': ADMIN,
        'DEBUG': False,
    })


@pytest.fixture
def client(app):
    return app.test_client()


def pdf_bytes(lineas=(('Fecha: 2026-08-05', 100),), tamano=12, fontname='helv', fontfile=None,
              paginas=1, rotacion=0):
    """PDF de prueba con texto en (72, y)."""
    with fitz.open() as doc:
        for _ in range(paginas):
            page = doc.new_page()
            if rotacion:
                page.set_rotation(rotacion)
            for texto, y in lineas:
                page.insert_text((72, y), texto, fontsize=tamano, fontname=fontname, fontfile=fontfile)
        if fontfile:
            doc.subset_fonts()
        return doc.tobytes(garbage=3, deflate=True)


def ruta_fuente(*familias):
    for familia in familias:
        ruta = _buscar_fuente_sistema(familia, False, False)
        if ruta:
            return ruta
    return None


def textos(datos_pdf, pagina=0):
    with fitz.open('pdf', datos_pdf) as doc:
        return [l.strip() for l in doc[pagina].get_text().replace('\xa0', ' ').replace('‐', '-').splitlines() if l.strip()]


def pixeles_oscuros(datos_pdf, clip, pagina=0):
    with fitz.open('pdf', datos_pdf) as doc:
        pix = doc[pagina].get_pixmap(dpi=72, clip=clip, colorspace=fitz.csGRAY)
        return sum(1 for b in pix.samples if b < 128)
