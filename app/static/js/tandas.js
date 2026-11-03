/*
 * Tandas: procesar varios archivos de una vez y, si se pide, entregarlos en un ZIP
 * que quepa en el correo.
 *
 * Esta lógica vive SOLO aquí, a diferencia de la sintaxis de grupos (grupos.js), que
 * está repetida en el servidor. El motivo: el servidor empaqueta los archivos que le
 * llegan y no decide las partes. Las partes se deciden en el navegador porque es el
 * único sitio donde ya se conoce el peso de lo YA comprimido, que es lo que se manda
 * por correo. El servidor no recomprime el ZIP (services.empaquetar_en_zip), así que
 * el peso de una parte es la suma de sus archivos y no hay que adivinar.
 *
 * Igual que grupos.js: script clásico, nombres en el ámbito global compartido (por eso
 * son largos y propios de este tema) y module.exports para que node los pruebe.
 */

const BYTES_EN_MB = 1024 * 1024;

// Lo que se puede elegir de una vez. Lo pidió la oficina: una tanda de facturas
// escaneadas son 20-40 archivos.
const MAX_TANDA_MB = 100;
// Tope por correo de Gmail. Es el que manda de verdad: de nada sirve comprimir si
// después el correo rebota, que es lo que venía pasando.
const MAX_CORREO_MB = 25;

const MAX_TANDA_BYTES  = MAX_TANDA_MB * BYTES_EN_MB;
const MAX_CORREO_BYTES = MAX_CORREO_MB * BYTES_EN_MB;

/**
 * ¿Cabe un archivo más en la tanda?
 * @param {number[]} tamanos  Pesos de los que ya están elegidos.
 * @param {number} nuevo      Peso del que se quiere añadir.
 * @param {number} topeBytes
 */
function cabeEnLaTanda(tamanos, nuevo, topeBytes = MAX_TANDA_BYTES) {
  const suma = tamanos.reduce((total, tamano) => total + tamano, 0);
  return suma + nuevo <= topeBytes;
}

/**
 * Reparte los archivos en partes que no pasen del tope, respetando el orden.
 *
 * Devuelve {partes, pesadas}: `partes` son listas de índices y `pesadas` los índices
 * que no caben en el tope ni yendo solos (se entregan igual, en su propia parte, y
 * quien los envía merece saber cuáles son por su nombre).
 */
function repartirEnPartes(tamanos, topeBytes = MAX_CORREO_BYTES) {
  const partes = [];
  const pesadas = [];
  let actual = [];
  let suma = 0;

  const cerrar = () => {
    if (actual.length) partes.push(actual);
    actual = [];
    suma = 0;
  };

  tamanos.forEach((tamano, indice) => {
    if (tamano > topeBytes) {
      // Ni solo cabe: acompañarlo solo haría rebotar también a los demás.
      cerrar();
      partes.push([indice]);
      pesadas.push(indice);
      return;
    }
    if (actual.length && suma + tamano > topeBytes) cerrar();
    actual.push(indice);
    suma += tamano;
  });
  cerrar();

  return { partes, pesadas };
}

/**
 * Nombres de los ZIP. Con una sola parte no se numera: "facturas.zip" y punto.
 * Con diez o más se rellena con ceros, porque si no el gestor de archivos las
 * ordena parte_1, parte_10, parte_11, parte_2.
 */
function nombrarPartes(base, total) {
  if (total <= 1) return [`${base}.zip`];
  const ancho = String(total).length;
  return Array.from({ length: total },
    (_, i) => `${base}_parte_${String(i + 1).padStart(ancho, '0')}.zip`);
}

/**
 * Aviso de los archivos que no caben en un correo ni yendo solos. Los nombra todos:
 * es lo único que explica por qué ESE correo va a rebotar y cuál hay que arreglar.
 */
function textoAvisoPesadas(nombres, topeMB = MAX_CORREO_MB) {
  const cuales = nombres.join(', ');
  const verbo = nombres.length === 1 ? 'pasa' : 'pasan';
  return `Aviso: ${cuales} ${verbo} de ${topeMB} MB incluso ya procesado, así que ese correo puede rebotar. Prueba un nivel de compresión más alto.`;
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    BYTES_EN_MB,
    MAX_TANDA_MB,
    MAX_CORREO_MB,
    MAX_TANDA_BYTES,
    MAX_CORREO_BYTES,
    cabeEnLaTanda,
    repartirEnPartes,
    nombrarPartes,
    textoAvisoPesadas,
  };
}
