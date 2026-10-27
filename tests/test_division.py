import pytest

from app.services import analizar_grupos, grupos_por_bloques


def test_analizar_grupos_acepta_tramos_y_paginas_sueltas():
    assert analizar_grupos('1-2,3-5,6', 10) == [(1, 2), (3, 5), (6, 6)]


def test_analizar_grupos_tolera_espacios_y_coma_final():
    assert analizar_grupos(' 1-2 , 3-5, ', 10) == [(1, 2), (3, 5)]


def test_analizar_grupos_respeta_el_orden_escrito():
    assert analizar_grupos('6-7,1-2', 10) == [(6, 7), (1, 2)]


def test_analizar_grupos_permite_dejar_paginas_fuera():
    assert analizar_grupos('1-3,5-6', 10) == [(1, 3), (5, 6)]


def test_analizar_grupos_rechaza_solapamiento_y_nombra_la_pagina():
    # '1-4' y '3-6' se pisan en la 3 y en la 4; el mensaje nombra la primera, la 3
    with pytest.raises(ValueError, match=r'\b3\b'):
        analizar_grupos('1-4,3-6', 10)


def test_analizar_grupos_rechaza_pagina_fuera_del_documento():
    with pytest.raises(ValueError, match='10'):
        analizar_grupos('1-2,9-12', 10)


def test_analizar_grupos_rechaza_inicio_mayor_que_fin():
    with pytest.raises(ValueError):
        analizar_grupos('5-3', 10)


@pytest.mark.parametrize('texto', ['', '   ', ',', '1-2,hola', '1--2', '0-2', '-3'])
def test_analizar_grupos_rechaza_texto_invalido(texto):
    with pytest.raises(ValueError):
        analizar_grupos(texto, 10)


def test_analizar_grupos_rechaza_mas_de_500_grupos():
    with pytest.raises(ValueError, match='500'):
        analizar_grupos(','.join(str(i) for i in range(1, 502)), 600)


def test_analizar_grupos_corta_el_texto_desmesurado_antes_de_analizarlo():
    with pytest.raises(ValueError, match='largo'):
        analizar_grupos('1-2,' * 5000, 10)


def test_grupos_por_bloques_divide_exacto():
    assert grupos_por_bloques(10, 2) == [(1, 2), (3, 4), (5, 6), (7, 8), (9, 10)]


def test_grupos_por_bloques_deja_el_ultimo_mas_corto():
    assert grupos_por_bloques(10, 3) == [(1, 3), (4, 6), (7, 9), (10, 10)]


def test_grupos_por_bloques_con_n_mayor_que_el_total_da_un_solo_grupo():
    assert grupos_por_bloques(5, 10) == [(1, 5)]


def test_grupos_por_bloques_rechaza_mas_de_500_archivos():
    with pytest.raises(ValueError, match='Cada página por separado'):
        grupos_por_bloques(600, 1)


@pytest.mark.parametrize('n', [0, -3])
def test_grupos_por_bloques_rechaza_n_menor_que_uno(n):
    with pytest.raises(ValueError):
        grupos_por_bloques(10, n)
