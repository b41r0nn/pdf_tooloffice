"""La pestaña que acepta una tanda: varios archivos y la casilla del ZIP.

Reglas que fijan estas pruebas: Comprimir, Convertir y Proteger aceptan varios
archivos; Dividir y Editar no (trabajan sobre un documento concreto); y el ZIP es
opcional y viene DESMARCADO, porque lo normal es querer los archivos sueltos.
"""

import re


def _panel(html, nombre):
    inicio = html.index(f'id="panel-{nombre}"')
    fin = html.find('<section id="panel-', inicio + 1)
    return html[inicio:fin if fin != -1 else len(html)]


def _input_archivo(panel_html):
    return re.search(r'<input type="file"[^>]*>', panel_html).group(0)


def _casilla(panel_html, campo):
    return re.search(rf'<input[^>]*id="{campo}"[^>]*>', panel_html).group(0)


PANELES_DE_TANDA = ('compresion', 'conversion', 'cifrado')
CASILLAS = {'compresion': 'comp-zip', 'conversion': 'conv-zip', 'cifrado': 'cif-zip'}


def test_los_paneles_de_tanda_aceptan_varios_archivos(client):
    html = client.get('/').get_data(as_text=True)
    for nombre in PANELES_DE_TANDA:
        assert 'multiple' in _input_archivo(_panel(html, nombre)), nombre


def test_dividir_y_editar_siguen_siendo_de_un_solo_archivo(client):
    # Dividir y Editar actúan sobre un documento concreto: aceptar una tanda ahí
    # no significaría nada.
    html = client.get('/').get_data(as_text=True)
    for nombre in ('division', 'editar'):
        assert 'multiple' not in _input_archivo(_panel(html, nombre)), nombre


def test_cada_panel_de_tanda_tiene_la_casilla_del_zip(client):
    html = client.get('/').get_data(as_text=True)
    for nombre in PANELES_DE_TANDA:
        panel = _panel(html, nombre)
        casilla = _casilla(panel, CASILLAS[nombre])
        assert 'type="checkbox"' in casilla, nombre
        assert f'for="{CASILLAS[nombre]}"' in panel, nombre


def test_la_casilla_del_zip_viene_desmarcada(client):
    # Lo pidió así el dueño: si no la marca, los archivos salen sueltos.
    html = client.get('/').get_data(as_text=True)
    for nombre in PANELES_DE_TANDA:
        assert 'checked' not in _casilla(_panel(html, nombre), CASILLAS[nombre]), nombre


def test_la_casilla_explica_que_el_zip_se_parte_por_el_correo(client):
    html = client.get('/').get_data(as_text=True)
    for nombre in PANELES_DE_TANDA:
        assert '25 MB' in _panel(html, nombre), nombre


def test_los_paneles_de_tanda_dicen_el_tope_de_la_tanda(client):
    html = client.get('/').get_data(as_text=True)
    for nombre in PANELES_DE_TANDA:
        assert '100 MB' in _panel(html, nombre), nombre


def test_tandas_js_se_carga_antes_de_main_js(client):
    # main.js usa repartirEnPartes y los topes al procesar una tanda; invertir el
    # orden deja las tres pestañas sin poder procesar.
    html = client.get('/').get_data(as_text=True)
    assert re.search(r'/static/js/tandas\.js\?v=\d+', html)
    assert html.index('tandas.js') < html.index('main.js')
