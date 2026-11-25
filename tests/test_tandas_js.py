"""Reparto de una tanda en partes que caben en el correo (app/static/js/tandas.js).

Esta logica vive solo en el navegador: el servidor empaqueta lo que le llega y no
decide las partes, asi que aqui no hay copia en Python que mantener en pareja (a
diferencia de la sintaxis de grupos, ver tests/test_grupos_js.py).

Se corre con node desde pytest; si no hay node, se omite.
"""

import json
import os
import shutil
import subprocess

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TANDAS_JS = os.path.join(RAIZ, 'app', 'static', 'js', 'tandas.js')

GUION = '''
const t = require(process.argv[2]);
const MB = 1024 * 1024;
const tope = 25 * MB;
const partes = (tamanos, topeBytes = tope) => t.repartirEnPartes(tamanos.map(n => n * MB), topeBytes);
const r = [
  partes([10, 10, 10]).partes,
  partes([10, 10, 10]).pesadas,
  partes([25, 25]).partes,
  partes([24, 1]).partes,
  partes([26]).partes,
  partes([26]).pesadas,
  partes([5, 30, 5]).partes,
  partes([5, 30, 5]).pesadas,
  partes([]).partes,
  partes([3, 3, 3, 3, 3, 3, 3, 3, 3, 3]).partes,
  t.nombrarPartes('facturas', 1),
  t.nombrarPartes('facturas', 3),
  t.nombrarPartes('facturas', 12).slice(0, 2),
  t.cabeEnLaTanda([40 * MB, 40 * MB], 10 * MB, 100 * MB),
  t.cabeEnLaTanda([40 * MB, 40 * MB], 30 * MB, 100 * MB),
  t.cabeEnLaTanda([], 100 * MB, 100 * MB),
  [t.MAX_TANDA_MB, t.MAX_CORREO_MB],
  t.textoAvisoPesadas(['factura_grande.pdf']),
  t.textoAvisoPesadas(['a.pdf', 'b.pdf']),
];
console.log(JSON.stringify(r));
'''


@pytest.fixture(scope='module')
def resultados(tmp_path_factory):
    if not shutil.which('node'):
        pytest.skip('node no está instalado')
    guion = tmp_path_factory.mktemp('tandas') / 'guion.js'
    guion.write_text(GUION, encoding='utf-8')
    salida = subprocess.run(
        ['node', str(guion), TANDAS_JS],
        capture_output=True, text=True, timeout=30,
    )
    assert salida.returncode == 0, salida.stderr
    return json.loads(salida.stdout)


def test_la_tanda_se_reparte_en_partes_que_caben(resultados):
    # 3 de 10 MB con tope de 25: dos en la primera parte, una en la segunda.
    assert resultados[0] == [[0, 1], [2]]
    assert resultados[1] == []


def test_un_archivo_que_llena_la_parte_va_solo(resultados):
    assert resultados[2] == [[0], [1]]


def test_lo_que_cabe_justo_cabe(resultados):
    # 24 + 1 = 25 MB exactos: una sola parte. Un «menor que» en vez de «menor o
    # igual» mandaria dos correos sin necesidad.
    assert resultados[3] == [[0, 1]]


def test_un_archivo_mas_grande_que_el_tope_va_solo_y_se_avisa(resultados):
    assert resultados[4] == [[0]]
    assert resultados[5] == [0]


def test_el_pesado_no_arrastra_a_los_demas(resultados):
    # El de 30 MB no cabe en ningún correo, pero los de 5 MB no tienen por qué
    # viajar con él ni perder su sitio.
    assert resultados[6] == [[0], [1], [2]]
    assert resultados[7] == [1]


def test_sin_archivos_no_hay_partes(resultados):
    assert resultados[8] == []


def test_el_orden_de_los_archivos_se_respeta(resultados):
    # 10 de 3 MB: 8 llenan la primera parte (24 MB), las otras 2 van en la segunda.
    assert resultados[9] == [[0, 1, 2, 3, 4, 5, 6, 7], [8, 9]]


def test_una_sola_parte_no_se_llama_parte_1(resultados):
    assert resultados[10] == ['facturas.zip']


def test_varias_partes_se_numeran(resultados):
    assert resultados[11] == ['facturas_parte_1.zip', 'facturas_parte_2.zip', 'facturas_parte_3.zip']


def test_con_diez_partes_o_mas_el_numero_se_rellena(resultados):
    # Sin rellenar, el gestor de archivos ordena parte_1, parte_10, parte_11, parte_2.
    assert resultados[12] == ['facturas_parte_01.zip', 'facturas_parte_02.zip']


def test_el_tope_de_la_tanda_deja_pasar_lo_que_cabe(resultados):
    assert resultados[13] is True


def test_el_tope_de_la_tanda_rechaza_lo_que_se_pasa(resultados):
    assert resultados[14] is False


def test_el_primer_archivo_puede_llenar_la_tanda_entera(resultados):
    assert resultados[15] is True


def test_los_topes_son_los_acordados(resultados):
    assert resultados[16] == [100, 25]


def test_el_aviso_nombra_el_archivo_y_el_tope(resultados):
    # El aviso es el único camino para enterarse de que ESE correo va a rebotar.
    aviso = resultados[17]
    assert 'factura_grande.pdf' in aviso
    assert '25 MB' in aviso


def test_el_aviso_nombra_todos_los_pesados(resultados):
    assert 'a.pdf' in resultados[18] and 'b.pdf' in resultados[18]
