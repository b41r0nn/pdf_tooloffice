"""El corazón de la vista de páginas: dos conjuntos y los grupos que salen de ellos.

`crearEstadoGrupos` no toca el DOM a propósito, así que se puede ejecutar con node
igual que grupos.js. Lo que se fija aquí es la matriz de cortar / unir / descartar /
reagrupar, y sobre todo que sembrar grupos desordenados no pierda ningún archivo.
"""

import json
import os
import shutil
import subprocess

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VISTA_JS = os.path.join(RAIZ, 'app', 'static', 'js', 'vista-paginas.js')
GRUPOS_JS = os.path.join(RAIZ, 'app', 'static', 'js', 'grupos.js')

# Cada caso: total de páginas, grupos con los que se siembra y acciones a aplicar.
# El resultado es la lista de grupos derivados tras cada acción, en texto.
GUION = '''
const { crearEstadoGrupos } = require(process.argv[2]);
const { formatearGrupos } = require(process.argv[3]);
const casos = JSON.parse(process.argv[4]);

console.log(JSON.stringify(casos.map(({ total, siembra, acciones }) => {
  const e = crearEstadoGrupos(total);
  e.sembrar(siembra);
  const pasos = [formatearGrupos(e.grupos())];
  for (const [que, n] of acciones) {
    if (que === 'cortar') e.cortar(n);
    else if (que === 'unir') e.unir(n);
    else if (que === 'descartar') e.alternarDescarte(n);
    else if (que === 'reagrupar') e.sembrarCortes(bloques(total, n));
    else throw new Error('accion desconocida: ' + que);
    pasos.push(formatearGrupos(e.grupos()));
  }
  return { pasos, descartadas: [...e.descartadas].sort((a, b) => a - b) };
})));

function bloques(total, n) {
  const salida = [];
  for (let i = 1; i <= total; i += n) salida.push([i, Math.min(i + n - 1, total)]);
  return salida;
}
'''

PAREJAS_10 = [[1, 2], [3, 4], [5, 6], [7, 8], [9, 10]]

CASOS = [
    # El recorrido completo de la tarea: cada 2, cortar en el tercero, unir los
    # dos primeros, descartar la última y reagrupar conservando el descarte.
    {
        'total': 10, 'siembra': PAREJAS_10,
        'acciones': [['cortar', 5], ['unir', 2], ['descartar', 10], ['reagrupar', 2]],
        'espera': ['1-2,3-4,5-6,7-8,9-10', '1-2,3-4,5,6,7-8,9-10',
                   '1-4,5,6,7-8,9-10', '1-4,5,6,7-8,9', '1-2,3-4,5-6,7-8,9'],
        'descartadas': [10],
    },
    # Descartar en medio parte el grupo en dos; recuperar lo deshace.
    {
        'total': 10, 'siembra': PAREJAS_10,
        'acciones': [['descartar', 3], ['descartar', 3]],
        'espera': ['1-2,3-4,5-6,7-8,9-10', '1-2,4,5-6,7-8,9-10', '1-2,3-4,5-6,7-8,9-10'],
        'descartadas': [],
    },
    # El caso real: tres páginas escaneadas a doble cara dejan una cara en blanco.
    # Unir las dos parejas y descartar la última deja el documento de 3 páginas.
    {
        'total': 4, 'siembra': [[1, 2], [3, 4]],
        'acciones': [['unir', 2], ['descartar', 4]],
        'espera': ['1-2,3-4', '1-4', '1-3'],
        'descartadas': [4],
    },
    # Unir por encima de una descartada la recupera: un grupo es un tramo seguido.
    {
        'total': 6, 'siembra': [[1, 2], [3, 4], [5, 6]],
        'acciones': [['descartar', 3], ['unir', 2]],
        'espera': ['1-2,3-4,5-6', '1-2,4,5-6', '1-4,5-6'],
        'descartadas': [],
    },
    # Unir el último grupo no hace nada (no hay siguiente).
    {
        'total': 4, 'siembra': [[1, 2], [3, 4]],
        'acciones': [['unir', 4], ['unir', 99]],
        'espera': ['1-2,3-4', '1-2,3-4', '1-2,3-4'],
        'descartadas': [],
    },
    # Las páginas que no aparecen en ningún grupo nacen descartadas.
    {
        'total': 10, 'siembra': [[1, 3], [8, 10]],
        'acciones': [],
        'espera': ['1-3,8-10'],
        'descartadas': [4, 5, 6, 7],
    },
    # Descartarlo todo deja el campo vacío.
    {
        'total': 2, 'siembra': [[1, 2]],
        'acciones': [['descartar', 1], ['descartar', 2]],
        'espera': ['1-2', '2', ''],
        'descartadas': [1, 2],
    },
    # Reagrupar no toca las descartadas aunque cambie el tamaño del bloque.
    {
        'total': 10, 'siembra': PAREJAS_10,
        'acciones': [['descartar', 5], ['reagrupar', 3]],
        'espera': ['1-2,3-4,5-6,7-8,9-10', '1-2,3-4,6,7-8,9-10', '1-3,4,6,7-9,10'],
        'descartadas': [5],
    },
    # Grupos desordenados: la sintaxis los admite (tests/test_grupos_js.py los fija)
    # y dos conjuntos no pueden guardar el orden, así que salen reordenados. Lo que
    # NO puede pasar es perder un archivo por el camino.
    {
        'total': 10, 'siembra': [[6, 7], [1, 2]],
        'acciones': [],
        'espera': ['1-2,6-7'],
        'descartadas': [3, 4, 5, 8, 9, 10],
    },
    {
        'total': 5, 'siembra': [[3, 5], [1, 2]],
        'acciones': [],
        'espera': ['1-2,3-5'],       # dos archivos, no uno
        'descartadas': [],
    },
]


def _node(tmp_path, casos):
    ruta = tmp_path / 'comprobar.js'
    ruta.write_text(GUION, encoding='utf-8')
    salida = subprocess.run(['node', str(ruta), VISTA_JS, GRUPOS_JS, json.dumps(casos)],
                            capture_output=True, text=True, encoding='utf-8',
                            timeout=30, check=True)
    return json.loads(salida.stdout)


@pytest.mark.skipif(not shutil.which('node'), reason='node no está instalado')
def test_el_estado_de_la_vista_deriva_los_grupos_esperados(tmp_path):
    obtenido = _node(tmp_path, CASOS)
    assert len(obtenido) == len(CASOS)
    for caso, real in zip(CASOS, obtenido):
        assert real['pasos'] == caso['espera'], caso['siembra']
        assert real['descartadas'] == caso['descartadas'], caso['siembra']


@pytest.mark.skipif(not shutil.which('node'), reason='node no está instalado')
def test_sembrar_grupos_desordenados_no_funde_dos_archivos_en_uno(tmp_path):
    # Regresión: con el corte puesto solo en «todos menos el último de la lista»,
    # «3-5,1-2» perdía el corte de la página 2 y salía un único archivo 1-5.
    caso = {'total': 5, 'siembra': [[3, 5], [1, 2]], 'acciones': []}
    assert _node(tmp_path, [caso])[0]['pasos'] == ['1-2,3-5']


@pytest.mark.skipif(not shutil.which('node'), reason='node no está instalado')
def test_la_vista_no_expone_nada_mas_que_su_estado(tmp_path):
    # En el navegador no hay `module`, así que la IIFE no exporta nada; en node
    # exporta solo el estado puro y no intenta tocar el DOM.
    ruta = tmp_path / 'comprobar.js'
    ruta.write_text('console.log(JSON.stringify(Object.keys(require(process.argv[2]))));',
                    encoding='utf-8')
    salida = subprocess.run(['node', str(ruta), VISTA_JS], capture_output=True,
                            text=True, encoding='utf-8', timeout=30, check=True)
    assert json.loads(salida.stdout) == ['crearEstadoGrupos']
