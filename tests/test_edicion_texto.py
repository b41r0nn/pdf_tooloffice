import pymupdf as fitz
import pytest

from app.edicion_texto import (
    BASE14_SHORT,
    _base14_para,
    analizar_nombre_fuente,
    detectar_campos_pdf,
    reemplazar_texto_pdf,
)

from .conftest import pdf_bytes, pixeles_oscuros, ruta_fuente, textos


def _escribir(tmp_path, datos, nombre='doc.pdf'):
    ruta = tmp_path / nombre
    ruta.write_bytes(datos)
    return str(ruta)


def _campo(ruta, texto, pagina=0):
    return next(c for c in detectar_campos_pdf(ruta, pagina)['campos'] if c['texto'].startswith(texto))


@pytest.mark.parametrize('nombre, esperado', [
    ('ABCDEF+Arial-BoldMT', ('arial', True, False)),
    ('TimesNewRomanPS-BoldItalicMT', ('timesnewroman', True, True)),
    ('TimesNewRomanPSMT', ('timesnewroman', False, False)),
    ('Calibri,Bold', ('calibri', True, False)),
    ('Calibri Light Regular', ('calibrilight', False, False)),
    ('Times-Roman', ('times', False, False)),
    ('CourierNewPS-ItalicMT', ('couriernew', False, True)),
])
def test_analizar_nombre_fuente(nombre, esperado):
    assert analizar_nombre_fuente(nombre) == esperado


def test_alias_base14_validos():
    # Los alias anteriores (heob, hebb, coob, cobb) no existen en PyMuPDF.
    for negrita in (False, True):
        for cursiva in (False, True):
            for flags in (0, 4, 8):
                fitz.Font(BASE14_SHORT[_base14_para('x', negrita, cursiva, flags)])


def test_reemplazo_no_borra_linea_vecina_con_interlineado_apretado(tmp_path):
    ruta = _escribir(tmp_path, pdf_bytes([('Linea uno ABCDEFG', 100), ('Linea dos HIJKLMN', 111)]))
    campo = _campo(ruta, 'Linea uno')
    datos, meta = reemplazar_texto_pdf(ruta, 0, campo['bbox'], 'Cambiado 123', texto_original=campo['texto'])
    assert set(textos(datos)) == {'Cambiado 123', 'Linea dos HIJKLMN'}
    assert not meta['eliminado']


def test_reemplazo_conserva_linea_base_y_tamano(tmp_path):
    ruta = _escribir(tmp_path, pdf_bytes([('Fecha: 2026-08-05', 100)], tamano=14))
    campo = _campo(ruta, 'Fecha')
    datos, _ = reemplazar_texto_pdf(ruta, 0, campo['bbox'], 'Fecha: 2026-12-31')
    with fitz.open('pdf', datos) as doc:
        span = doc[0].get_text('dict')['blocks'][0]['lines'][0]['spans'][0]
    assert span['origin'] == pytest.approx((72, 100), abs=0.05)
    assert span['size'] == pytest.approx(14, abs=0.01)


def test_reemplazo_no_toca_bordes_ni_fondos(tmp_path):
    with fitz.open() as doc:
        page = doc.new_page()
        page.draw_rect(fitz.Rect(60, 80, 300, 120), color=(0, 0, 0), width=1)
        page.draw_rect(fitz.Rect(70, 88, 220, 104), fill=(1, 1, 0.5), color=None)
        page.insert_text((72, 100), 'Celda con fondo', fontsize=12)
        original = doc.tobytes()
    ruta = _escribir(tmp_path, original)
    campo = _campo(ruta, 'Celda')
    datos, _ = reemplazar_texto_pdf(ruta, 0, campo['bbox'], 'Otro valor')
    with fitz.open('pdf', datos) as doc:
        assert len(doc[0].get_drawings()) == 2
        # Sin parche blanco: el fondo amarillo sigue bajo el texto
        pix = doc[0].get_pixmap(dpi=72, clip=fitz.Rect(200, 90, 215, 102))
        assert pix.pixel(5, 5)[2] < 200


def test_misma_familia_de_fuente_del_sistema(tmp_path):
    fuente = ruta_fuente('arial', 'liberationsans', 'dejavusans')
    if not fuente:
        pytest.skip('No hay fuentes del sistema disponibles')
    ruta = _escribir(tmp_path, pdf_bytes([('Total: $ 1.250.000', 100)], fontname='F1', fontfile=fuente))
    campo = _campo(ruta, 'Total')
    datos, meta = reemplazar_texto_pdf(ruta, 0, campo['bbox'], 'Total: $ 9.999.999 Ñandú')
    assert meta['tipo_fuente'] == 'sistema'
    assert meta['fuente_aproximada'] is False
    assert 'Total: $ 9.999.999 Ñandú' in textos(datos)


def test_ediciones_sucesivas_no_inflan_el_archivo(tmp_path):
    fuente = ruta_fuente('arial', 'liberationsans', 'dejavusans')
    if not fuente:
        pytest.skip('No hay fuentes del sistema disponibles')
    datos = pdf_bytes([('Uno 1', 100), ('Dos 2', 130), ('Tres 3', 160)], fontname='F1', fontfile=fuente)
    inicial = len(datos)
    for texto in ('Uno', 'Dos', 'Tres'):
        ruta = _escribir(tmp_path, datos)
        campo = _campo(ruta, texto)
        datos, _ = reemplazar_texto_pdf(ruta, 0, campo['bbox'], f'{texto} editado')
    assert len(datos) - inicial < 250_000  # sin subset serían varios MB


def test_editar_una_pagina_no_rompe_otras_con_la_misma_fuente(tmp_path):
    fuente = ruta_fuente('arial', 'liberationsans', 'dejavusans')
    if not fuente:
        pytest.skip('No hay fuentes del sistema disponibles')
    with fitz.open() as doc:
        for texto in ('Pagina uno AAA', 'Pagina dos XYZ 789'):
            page = doc.new_page()
            page.insert_text((72, 100), texto, fontsize=14, fontname='F1', fontfile=fuente)
        doc.subset_fonts()
        original = doc.tobytes(garbage=3, deflate=True)
    clip = fitz.Rect(60, 80, 300, 110)
    antes = pixeles_oscuros(original, clip, pagina=1)
    ruta = _escribir(tmp_path, original)
    campo = _campo(ruta, 'Pagina uno')
    datos, _ = reemplazar_texto_pdf(ruta, 0, campo['bbox'], 'Pagina uno BBB')
    assert pixeles_oscuros(datos, clip, pagina=1) == antes


def test_alineacion_derecha_conserva_el_final(tmp_path):
    ruta = _escribir(tmp_path, pdf_bytes([('1.250.000,00', 100)]))
    campo = _campo(ruta, '1.250')
    datos, _ = reemplazar_texto_pdf(ruta, 0, campo['bbox'], '99,00', alineacion='derecha')
    with fitz.open('pdf', datos) as doc:
        span = doc[0].get_text('dict')['blocks'][0]['lines'][0]['spans'][0]
    assert span['bbox'][2] == pytest.approx(campo['bbox'][2], abs=0.6)


def test_texto_largo_se_reduce_sin_pisar_al_vecino(tmp_path):
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((72, 100), 'Corto', fontsize=12)
        page.insert_text((140, 100), 'Vecino', fontsize=12)
        original = doc.tobytes()
    ruta = _escribir(tmp_path, original)
    campo = _campo(ruta, 'Corto')
    datos, meta = reemplazar_texto_pdf(ruta, 0, campo['bbox'], 'Un poco largo')
    assert meta['tamano_reducido'] is True
    assert meta['tamano'] >= 12 * 0.7 - 0.01
    assert 'Vecino' in ' '.join(textos(datos))


def test_texto_vacio_borra(tmp_path):
    ruta = _escribir(tmp_path, pdf_bytes([('Borrame', 100), ('Queda', 140)]))
    campo = _campo(ruta, 'Borrame')
    datos, meta = reemplazar_texto_pdf(ruta, 0, campo['bbox'], '')
    assert meta['eliminado'] is True
    assert textos(datos) == ['Queda']


def test_rechaza_si_el_texto_cambio(tmp_path):
    ruta = _escribir(tmp_path, pdf_bytes())
    campo = _campo(ruta, 'Fecha')
    with pytest.raises(ValueError, match='cambió'):
        reemplazar_texto_pdf(ruta, 0, campo['bbox'], 'x', texto_original='Otro texto')


def test_rechaza_multilinea_y_pagina_fuera_de_rango(tmp_path):
    ruta = _escribir(tmp_path, pdf_bytes())
    campo = _campo(ruta, 'Fecha')
    with pytest.raises(ValueError):
        reemplazar_texto_pdf(ruta, 0, campo['bbox'], 'a\nb')
    with pytest.raises(ValueError):
        reemplazar_texto_pdf(ruta, 5, campo['bbox'], 'x')


@pytest.mark.parametrize('rotacion', [90, 180, 270])
def test_pagina_rotada_overlay_y_reemplazo(tmp_path, rotacion):
    datos = pdf_bytes([('HOLA MUNDO', 100)], tamano=20, rotacion=rotacion)
    ruta = _escribir(tmp_path, datos)
    info = detectar_campos_pdf(ruta, 0)
    campo = info['campos'][0]
    # 'vista' debe caer sobre el texto en la imagen renderizada (página rotada)
    with fitz.open(ruta) as doc:
        pix = doc[0].get_pixmap(dpi=72, colorspace=fitz.csGRAY)
    x0, y0, x1, y1 = (int(v) for v in campo['vista'])
    oscuros = sum(1 for y in range(y0, y1) for x in range(x0, x1) if pix.pixel(x, y)[0] < 128)
    assert oscuros > 50
    nuevo, _ = reemplazar_texto_pdf(ruta, 0, campo['bbox'], 'ADIOS')
    assert textos(nuevo) == ['ADIOS']


def test_pagina_escaneada_se_detecta(tmp_path):
    with fitz.open() as doc:
        page = doc.new_page()
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 60, 80), False)
        pix.clear_with(200)
        page.insert_image(page.rect, pixmap=pix)
        datos = doc.tobytes()
    info = detectar_campos_pdf(_escribir(tmp_path, datos), 0)
    assert info['escaneada'] is True
    assert info['campos'] == []


def test_texto_de_anotaciones_no_es_editable(tmp_path):
    with fitz.open('pdf', pdf_bytes([('Contenido real', 100)])) as doc:
        annot = doc[0].add_freetext_annot(fitz.Rect(72, 200, 300, 230), 'Nota del visor', fontsize=12)
        annot.update()
        doc[0].add_highlight_annot(fitz.Rect(70, 88, 170, 104))
        datos = doc.tobytes()
    textos_campos = [c['texto'] for c in detectar_campos_pdf(_escribir(tmp_path, datos), 0)['campos']]
    assert textos_campos == ['Contenido real']  # el resaltado no oculta el texto real


@pytest.mark.parametrize('giro', [90, 270])
def test_texto_girado_dentro_de_la_pagina(tmp_path, giro):
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((200, 400), 'Sello lateral', fontsize=14, rotate=giro)
        page.insert_text((72, 100), 'Encabezado', fontsize=14)
        datos = doc.tobytes()
    ruta = _escribir(tmp_path, datos)
    campo = _campo(ruta, 'Sello')
    assert campo['editable']
    nuevo, _ = reemplazar_texto_pdf(ruta, 0, campo['bbox'], 'Sello nuevo')
    assert set(textos(nuevo)) == {'Sello nuevo', 'Encabezado'}
    with fitz.open('pdf', nuevo) as doc:
        line = next(l for b in doc[0].get_text('dict')['blocks'] for l in b['lines']
                    if l['spans'][0]['text'].startswith('Sello'))
    assert line['spans'][0]['origin'] == pytest.approx((200, 400), abs=0.1)


def test_equivalente_metrico_no_se_marca_como_aproximado(monkeypatch):
    from app import edicion_texto
    fuente = ruta_fuente('arial', 'liberationsans', 'dejavusans')
    if not fuente:
        pytest.skip('No hay fuentes del sistema disponibles')
    # Calibri no instalada, Carlito sí -> equivalente métrico, sin aviso
    monkeypatch.setattr(edicion_texto, '_indice', {'carlito': [(False, False, fuente)]})
    assert edicion_texto.resolver_fuente('ABCDEF+Calibri', 0, 'abc')['aproximada'] is False
    # Solo una genérica disponible -> aproximada, con aviso
    monkeypatch.setattr(edicion_texto, '_indice', {'arial': [(False, False, fuente)]})
    assert edicion_texto.resolver_fuente('ABCDEF+Calibri', 0, 'abc')['aproximada'] is True
