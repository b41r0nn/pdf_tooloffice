import json
import os
import shutil
import subprocess

import pytest

from app.services import analizar_grupos, grupos_por_bloques

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GRUPOS_JS = os.path.join(RAIZ, 'app', 'static', 'js', 'grupos.js')

GUION = '''
const g = require(process.argv[2]);
const r = [
  g.analizarGrupos('1-2,3-5,6', 10).grupos,
  g.analizarGrupos(' 1-2 , 3-5, ', 10).grupos,
  g.analizarGrupos('6-7,1-2', 10).grupos,
  g.analizarGrupos('1-3,5-6', 10).grupos,
  !!g.analizarGrupos('1-4,3-6', 10).error,
  !!g.analizarGrupos('1-2,9-12', 10).error,
  !!g.analizarGrupos('5-3', 10).error,
  !!g.analizarGrupos('1-2,hola', 10).error,
  !!g.analizarGrupos('   ', 10).error,
  g.gruposPorBloques(10, 2).grupos,
  g.gruposPorBloques(10, 3).grupos,
  g.gruposPorBloques(5, 10).grupos,
  !!g.gruposPorBloques(600, 1).error,
  !!g.gruposPorBloques(10, 0).error,
  g.formatearGrupos([[1, 2], [3, 5], [6, 6]]),
];
console.log(JSON.stringify(r));
'''

# Entradas con las que el JS y el Python deben dar el mismo resultado o el mismo mensaje.
CASOS_ANALIZAR = [
    ('1-2,3-5,6', 10),
    ('1,,2', 10),
    ('1 - 2', 10),
    ('x' * 40, 10),
    ('x' * 41, 10),
    ('1234567', 2000000),
    ('1-2,9-12', 10),
    ('0', 10),
    ('5-3', 10),
    ('1-4,3-6', 10),
    ('6-7,1-2,7', 10),
    (','.join(str(i) for i in range(1, 502)), 1000),
    ('1,' * 6000, 10),
    ('   ', 10),
]
CASOS_BLOQUES = [(10, 0), (600, 1), (10, 3), (0, 3)]

GUION_PARIDAD = '''
const g = require(process.argv[2]);
const casos = JSON.parse(process.argv[3]);
console.log(JSON.stringify([
  casos.analizar.map(([t, n]) => g.analizarGrupos(t, n)),
  casos.bloques.map(([t, p]) => g.gruposPorBloques(t, p)),
]));
'''


def _node(tmp_path, guion, *args):
    ruta = tmp_path / 'comprobar.js'
    ruta.write_text(guion, encoding='utf-8')
    salida = subprocess.run(['node', str(ruta), GRUPOS_JS, *args],
                            capture_output=True, text=True, encoding='utf-8',
                            timeout=30, check=True)
    return json.loads(salida.stdout)


@pytest.mark.skipif(not shutil.which('node'), reason='node no está instalado')
def test_grupos_js_coincide_con_el_analizador_de_python(tmp_path):
    assert _node(tmp_path, GUION) == [
        [[1, 2], [3, 5], [6, 6]],
        [[1, 2], [3, 5]],
        [[6, 7], [1, 2]],
        [[1, 3], [5, 6]],
        True, True, True, True, True,
        [[1, 2], [3, 4], [5, 6], [7, 8], [9, 10]],
        [[1, 3], [4, 6], [7, 9], [10, 10]],
        [[1, 5]],
        True, True,
        '1-2,3-5,6',
    ]


def _python(funcion, *args):
    try:
        return {'grupos': [list(g) for g in funcion(*args)]}
    except ValueError as e:
        return {'error': str(e)}


@pytest.mark.skipif(not shutil.which('node'), reason='node no está instalado')
def test_grupos_js_da_los_mismos_resultados_y_mensajes_que_python(tmp_path):
    casos = {'analizar': CASOS_ANALIZAR, 'bloques': CASOS_BLOQUES}
    analizar_js, bloques_js = _node(tmp_path, GUION_PARIDAD, json.dumps(casos))
    assert analizar_js == [_python(analizar_grupos, t, n) for t, n in CASOS_ANALIZAR]
    assert bloques_js == [_python(grupos_por_bloques, t, p) for t, p in CASOS_BLOQUES]
