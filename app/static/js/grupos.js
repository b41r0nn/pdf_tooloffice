/*
 * Sintaxis de grupos de páginas ("1-2,3-5,6") en el navegador.
 *
 * Esta lógica está repetida a propósito: la versión de verdad vive en el servidor
 * (app/services.py: analizar_grupos y grupos_por_bloques) y es la que manda. Esta
 * copia solo sirve para adelantar la cuenta de archivos mientras se escribe y para
 * dibujar la vista de páginas, sin subir nada. Por eso las reglas, los límites y los
 * mensajes son los mismos, comprobados en el mismo orden: quien lee el aviso lee la
 * misma frase venga del navegador o del servidor. Si cambias una, cambia la otra
 * (tests/test_grupos_js.py las compara).
 *
 * A diferencia del Python, estas funciones no lanzan excepciones: devuelven
 * {grupos: [[ini, fin], …]} o {error: 'mensaje'}, porque se recalculan a cada tecla.
 *
 * Diferencias conocidas que solo afectan al texto de un aviso, no a si algo es válido:
 * el trozo mostrado se corta por unidades UTF-16 (Python, por puntos de código) y
 * trim() de JavaScript quita algún espacio exótico más que str.strip() de Python.
 */

const MAX_ARCHIVOS_DIVISION = 500;
const MAX_TEXTO_GRUPOS = 10000;

const TRAMO_GRUPO = /^([0-9]{1,6})(?:-([0-9]{1,6}))?$/;

function analizarGrupos(texto, total) {
  // Python cuenta puntos de código; length cuenta unidades UTF-16. Solo se cuenta
  // de verdad cuando length ya pasa el límite.
  if (texto.length > MAX_TEXTO_GRUPOS && Array.from(texto).length > MAX_TEXTO_GRUPOS) {
    return { error: 'El texto de los grupos es demasiado largo.' };
  }

  const trozos = texto.split(',').map((t) => t.trim()).filter((t) => t);
  if (trozos.length === 0) {
    return { error: 'Escribe al menos un grupo de páginas, por ejemplo 1-2,3-5,6.' };
  }

  const grupos = [];
  for (const trozo of trozos) {
    const m = TRAMO_GRUPO.exec(trozo);
    if (!m) {
      const visto = trozo.length <= 40 ? trozo : trozo.slice(0, 40) + '…';
      return { error: `«${visto}» no es un grupo válido; escribe un número o un tramo como 3-5.` };
    }
    const inicio = parseInt(m[1], 10);
    const fin = m[2] ? parseInt(m[2], 10) : inicio;
    grupos.push([inicio, fin]);
  }

  for (const [inicio, fin] of grupos) {
    for (const pagina of [inicio, fin]) {
      if (pagina < 1 || pagina > total) {
        return { error: `La página ${pagina} no existe; el documento tiene de la 1 a la ${total}.` };
      }
    }
  }

  for (const [inicio, fin] of grupos) {
    if (inicio > fin) {
      return { error: `El grupo ${inicio}-${fin} está al revés: la página inicial es mayor que la final.` };
    }
  }

  if (grupos.length > MAX_ARCHIVOS_DIVISION) {
    return { error: `Hay ${grupos.length} grupos, más de los ${MAX_ARCHIVOS_DIVISION} permitidos.` };
  }

  const usadas = new Set();
  for (const [inicio, fin] of grupos) {
    for (let pagina = inicio; pagina <= fin; pagina++) {
      if (usadas.has(pagina)) {
        return { error: `La página ${pagina} está en más de un grupo.` };
      }
      usadas.add(pagina);
    }
  }

  return { grupos };
}

function gruposPorBloques(total, paginasPorArchivo) {
  if (!(Number.isInteger(paginasPorArchivo) && paginasPorArchivo >= 1)) {
    return { error: 'Las páginas por archivo deben ser al menos 1.' };
  }

  const cantidad = Math.ceil(total / paginasPorArchivo);
  if (cantidad > MAX_ARCHIVOS_DIVISION) {
    return {
      error: `Saldrían ${cantidad} archivos, más de los ${MAX_ARCHIVOS_DIVISION} permitidos. `
        + 'Usa «Cada página por separado».',
    };
  }

  const grupos = [];
  for (let inicio = 1; inicio <= total; inicio += paginasPorArchivo) {
    grupos.push([inicio, Math.min(inicio + paginasPorArchivo - 1, total)]);
  }
  return { grupos };
}

function formatearGrupos(grupos) {
  return grupos.map(([inicio, fin]) => (inicio === fin ? String(inicio) : `${inicio}-${fin}`)).join(',');
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { analizarGrupos, gruposPorBloques, formatearGrupos };
}
