"""El panel Proteger ofrece dos modos: poner la contraseña o quitarla.

Lo que fijan estas pruebas es lo que la persona ve: los dos modos existen, el de
quitar pide la contraseña actual en un solo campo, la casilla de restricciones
viene desmarcada y las notas dicen la verdad (la contraseña puede ir vacía y las
restricciones solo se quitan con la casilla, o se van con la contraseña).
"""

import os
import re


def _panel(html, nombre):
    inicio = html.index(f'id="panel-{nombre}"')
    fin = html.find('<section id="panel-', inicio + 1)
    return html[inicio:fin if fin != -1 else len(html)]


def _bloque(panel_html, id_):
    """Contenido del elemento con ese id (hasta su </li>, el paso es un <li>)."""
    inicio = panel_html.index(f'id="{id_}"')
    fin = panel_html.index('</li>', inicio)
    return panel_html[inicio:fin]


def _etiqueta(panel_html, id_):
    return re.search(rf'<label[^>]*for="{id_}"[^>]*>', panel_html) is not None


def test_el_panel_proteger_ofrece_los_dos_modos(client):
    panel = _panel(client.get('/').get_data(as_text=True), 'cifrado')
    poner = re.search(r'<input[^>]*id="cif-modo-poner"[^>]*>', panel).group(0)
    quitar = re.search(r'<input[^>]*id="cif-modo-quitar"[^>]*>', panel).group(0)
    assert 'type="radio"' in poner and 'name="cif-modo"' in poner
    assert 'type="radio"' in quitar and 'name="cif-modo"' in quitar
    assert 'checked' in poner
    assert 'checked' not in quitar
    assert _etiqueta(panel, 'cif-modo-poner')
    assert _etiqueta(panel, 'cif-modo-quitar')
    assert 'Poner contraseña' in panel
    assert 'Quitar contraseña' in panel


def test_los_modos_van_en_un_grupo_de_pastillas_accesible(client):
    panel = _panel(client.get('/').get_data(as_text=True), 'cifrado')
    assert re.search(r'<div class="pill-group"[^>]*role="radiogroup"[^>]*>', panel)
    assert 'aria-label="Qué hacer con la contraseña"' in panel


def test_el_paso_de_quitar_viene_escondido(client):
    panel = _panel(client.get('/').get_data(as_text=True), 'cifrado')
    assert re.search(r'<li[^>]*id="paso-quitar"[^>]*\bhidden\b', panel)
    assert not re.search(r'<li[^>]*id="paso-poner"[^>]*\bhidden\b', panel)


def test_el_paso_de_poner_conserva_las_dos_contrasenas(client):
    panel = _panel(client.get('/').get_data(as_text=True), 'cifrado')
    poner = _bloque(panel, 'paso-poner')
    assert 'id="pass1"' in poner
    assert 'id="pass2"' in poner


def test_el_modo_quitar_tiene_un_solo_campo_de_contrasena(client):
    panel = _panel(client.get('/').get_data(as_text=True), 'cifrado')
    quitar = _bloque(panel, 'paso-quitar')
    assert len(re.findall(r'<input[^>]*type="password"', quitar)) == 1
    assert 'id="cif-pass-actual"' in quitar
    assert 'Contraseña actual' in quitar


def test_la_pantalla_explica_que_la_contrasena_puede_ir_vacia(client):
    panel = _panel(client.get('/').get_data(as_text=True), 'cifrado')
    assert 'Déjalo vacío si el PDF se abre sin pedir contraseña.' in _bloque(panel, 'paso-quitar')


def test_la_casilla_de_restricciones_viene_desmarcada(client):
    panel = _panel(client.get('/').get_data(as_text=True), 'cifrado')
    casilla = re.search(r'<input[^>]*id="cif-restricciones"[^>]*>', panel).group(0)
    assert 'type="checkbox"' in casilla
    assert 'checked' not in casilla
    assert 'for="cif-restricciones"' in panel
    assert 'Quitar también las restricciones de impresión y copia' in panel


def test_la_nota_de_restricciones_dice_cuando_hace_falta_la_casilla(client):
    panel = _panel(client.get('/').get_data(as_text=True), 'cifrado')
    assert (
        'Solo hace falta para un PDF que se abre sin contraseña: '
        'si el PDF pide contraseña, sus restricciones se van con ella.'
    ) in _bloque(panel, 'paso-quitar')


def test_el_boton_dice_proteger_pdf_en_modo_poner(client):
    panel = _panel(client.get('/').get_data(as_text=True), 'cifrado')
    boton = re.search(r'<button[^>]*class="btn-primary btn-process"[^>]*>.*?</button>',
                      panel, re.S).group(0)
    assert 'Proteger PDF' in boton
    assert 'id="cif-btn-texto"' in boton


def test_la_casilla_del_zip_sigue_en_los_dos_modos(client):
    panel = _panel(client.get('/').get_data(as_text=True), 'cifrado')
    # El ZIP no vive dentro de ninguno de los dos pasos: vale para los dos modos.
    assert 'id="cif-zip"' in panel
    assert 'id="cif-zip"' not in _bloque(panel, 'paso-poner')
    assert 'id="cif-zip"' not in _bloque(panel, 'paso-quitar')


def test_los_radios_de_modo_no_los_restaura_el_navegador(client):
    # Si el navegador restaura el radio «Quitar» al recargar o volver atrás, el paso
    # visible no coincidiría con lo que se envía. autocomplete="off" lo evita.
    panel = _panel(client.get('/').get_data(as_text=True), 'cifrado')
    for id_ in ('cif-modo-poner', 'cif-modo-quitar'):
        radio = re.search(rf'<input[^>]*id="{id_}"[^>]*>', panel).group(0)
        assert 'autocomplete="off"' in radio, id_


def test_la_etiqueta_de_progreso_arranca_en_cifrando(client):
    # Modo poner por defecto: la etiqueta de partida es la de cifrar. El modo quitar
    # la cambia en el JavaScript (no en la plantilla).
    panel = _panel(client.get('/').get_data(as_text=True), 'cifrado')
    etiqueta = re.search(r'<div class="progress-label"><span>([^<]*)</span>', panel)
    assert etiqueta.group(1) == 'Cifrando…'


def test_el_javascript_pone_la_etiqueta_de_quitar(client):
    # Guarda de texto: la conmutación en el navegador se verifica aparte.
    ruta = os.path.join(os.path.dirname(__file__), '..', 'app', 'static', 'js', 'main.js')
    with open(ruta, encoding='utf-8') as f:
        js = f.read()
    assert 'Quitando la contraseña…' in js
    assert "'Cifrando…'" in js


def _js():
    ruta = os.path.join(os.path.dirname(__file__), '..', 'app', 'static', 'js', 'main.js')
    with open(ruta, encoding='utf-8') as f:
        return f.read()


def test_el_javascript_cambia_titulo_y_descripcion_segun_el_modo():
    js = _js()
    for texto in ('Quitar la contraseña', 'Proteger con contraseña',
                  'Devuelve un PDF nuevo que se abre sin pedir contraseña. El original no se toca.',
                  'Cifra el PDF: solo quien tenga la contraseña podrá abrirlo.',
                  'Elegir los PDF a desbloquear', 'Elegir los PDF a proteger'):
        assert texto in js, texto


def test_al_cambiar_de_modo_se_esconde_el_resultado_anterior():
    js = _js()
    cuerpo = js[js.index('const sincronizarModo'):js.index("addEventListener('pageshow'")]
    assert '.result-box' in cuerpo
    assert "classList.remove('visible')" in cuerpo
    assert '.btn-download' in cuerpo


def test_la_casilla_de_restricciones_esta_asociada_a_su_explicacion(client):
    panel = _panel(client.get('/').get_data(as_text=True), 'cifrado')
    casilla = re.search(r'<input[^>]*id="cif-restricciones"[^>]*>', panel).group(0)
    assert 'aria-describedby="cif-restricciones-nota"' in casilla
    assert 'id="cif-restricciones-nota"' in panel
