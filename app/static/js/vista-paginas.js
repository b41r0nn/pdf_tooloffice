/*
 * Vista de páginas de la pestaña Dividir: miniaturas para ajustar los grupos a mano.
 *
 * Todo va dentro de una IIFE y no se expone nada: grupos.js y main.js son scripts
 * clásicos que comparten el ámbito global, y un `const` repetido arriba es un
 * SyntaxError que tumbaría la página entera, no solo esta vista.
 *
 * El estado son dos conjuntos — las páginas descartadas y los puntos de corte (la
 * página tras la cual se corta) — y los grupos se DERIVAN de ahí; nunca al revés.
 * Así cortar, unir y descartar son tres operaciones sobre dos conjuntos y el dibujo
 * siempre dice lo mismo que el campo de texto, que se reescribe en cada acción.
 *
 * Las miniaturas se dibujan en el navegador con la PDF.js que la aplicación ya trae.
 * Las rutas de pdf.mjs y pdf.worker.mjs llegan en los data-… del armazón porque solo
 * la plantilla sabe el ?v= de caché.
 */

(function () {
  'use strict';

  const ANCHO_MINIATURA = 120;             // px de ancho de cada miniatura
  const MARGEN_OBSERVADOR = '300px';       // se adelanta a dibujar lo que está por entrar
  const AVISO_CIFRADO = 'El archivo PDF está cifrado: ingresa la contraseña correcta para procesarlo';

  const vista = document.getElementById('div-vista');
  const contenedor = document.getElementById('vista-grupos');
  const resumen = document.getElementById('vista-resumen');
  const campoN = document.getElementById('vista-n');
  const btnAbrir = document.getElementById('div-ver-paginas');
  const btnReagrupar = document.getElementById('vista-reagrupar');
  const btnCerrar = document.getElementById('vista-cerrar');
  const campoGrupos = document.getElementById('div-grupos');
  const campoRellenarN = document.getElementById('div-rellenar-n');
  const btnRellenar = document.getElementById('div-rellenar');
  if (!vista || !contenedor || !btnAbrir || !campoGrupos) return;

  // ── Estado ───────────────────────────────────────────────────────
  let abierta = false;
  let total = 0;
  const descartadas = new Set();
  const cortes = new Set();

  // PDF.js y las miniaturas ya dibujadas, atadas al archivo del que salieron.
  let pdfjs = null;            // {getDocument, GlobalWorkerOptions}
  let archivo = null;          // el File cuyas miniaturas están en memoria
  let documento = null;        // PDFDocumentProxy
  const lienzos = new Map();   // nº de página → <canvas> (se reusa el nodo para no redibujar)

  const observador = ('IntersectionObserver' in window)
    ? new IntersectionObserver((entradas) => {
      for (const entrada of entradas) {
        if (!entrada.isIntersecting) continue;
        observador.unobserve(entrada.target);
        dibujarPagina(Number(entrada.target.dataset.pagina));
      }
    }, { rootMargin: MARGEN_OBSERVADOR })
    : null;

  function aviso(mensaje) {
    if (typeof showToast === 'function') showToast(mensaje);
  }

  // ── Los grupos se derivan del estado ─────────────────────────────
  function gruposDerivados() {
    const grupos = [];
    let inicio = null;
    const cerrar = (fin) => {
      if (inicio !== null && fin >= inicio) grupos.push([inicio, fin]);
      inicio = null;
    };
    for (let pagina = 1; pagina <= total; pagina++) {
      if (descartadas.has(pagina)) { cerrar(pagina - 1); continue; }
      if (inicio === null) inicio = pagina;
      if (cortes.has(pagina)) cerrar(pagina);
    }
    cerrar(total);
    return grupos;
  }

  // Siembra el estado con unos grupos: cortes en el final de cada uno salvo el
  // último, y fuera (descartadas) las páginas que no aparecen en ninguno.
  function sembrar(grupos) {
    cortes.clear();
    descartadas.clear();
    const dentro = new Set();
    grupos.forEach(([inicio, fin], indice) => {
      for (let pagina = inicio; pagina <= fin; pagina++) dentro.add(pagina);
      if (indice < grupos.length - 1) cortes.add(fin);
    });
    for (let pagina = 1; pagina <= total; pagina++) {
      if (!dentro.has(pagina)) descartadas.add(pagina);
    }
  }

  // Solo rehace los cortes: las descartadas se respetan (es el «Reagrupar»).
  function sembrarCortes(grupos) {
    cortes.clear();
    grupos.forEach(([, fin], indice) => {
      if (indice < grupos.length - 1) cortes.add(fin);
    });
  }

  // ── Dibujo ───────────────────────────────────────────────────────
  function lienzoDe(pagina) {
    let lienzo = lienzos.get(pagina);
    if (lienzo) return lienzo;
    lienzo = document.createElement('canvas');
    lienzo.className = 'vista-lienzo';
    lienzo.dataset.pagina = String(pagina);
    lienzos.set(pagina, lienzo);
    return lienzo;
  }

  async function dibujarPagina(pagina) {
    const lienzo = lienzos.get(pagina);
    if (!documento || !lienzo || lienzo.dataset.listo) return;
    try {
      const hoja = await documento.getPage(pagina);
      const nitidez = Math.min(window.devicePixelRatio || 1, 2);
      const base = hoja.getViewport({ scale: 1 });
      const escala = ANCHO_MINIATURA / base.width;
      const marco = hoja.getViewport({ scale: escala * nitidez });
      // El tamaño en píxeles es el del dibujo; el tamaño en pantalla lo pone el CSS
      // (width: 100% del marco), así la miniatura se encoge sola en pantallas estrechas.
      lienzo.width = Math.max(1, Math.round(marco.width));
      lienzo.height = Math.max(1, Math.round(marco.height));
      await hoja.render({ canvasContext: lienzo.getContext('2d'), viewport: marco }).promise;
      lienzo.dataset.listo = '1';
    } catch (err) {
      // Una miniatura que no sale no impide ajustar los grupos: queda el hueco.
      lienzo.dataset.listo = '1';
    }
  }

  function botonTexto(clase, texto, etiqueta, datos) {
    const boton = document.createElement('button');
    boton.type = 'button';
    boton.className = clase;
    boton.textContent = texto;
    boton.setAttribute('aria-label', etiqueta);
    Object.entries(datos).forEach(([clave, valor]) => { boton.dataset[clave] = String(valor); });
    return boton;
  }

  function figuraDe(pagina) {
    const fuera = descartadas.has(pagina);
    const figura = document.createElement('figure');
    figura.className = 'vista-pagina' + (fuera ? ' apagada' : '');

    const marco = document.createElement('div');
    marco.className = 'vista-lienzo-marco';
    marco.appendChild(lienzoDe(pagina));
    figura.appendChild(marco);

    // El <figcaption> tiene que ser el primer o el último hijo del <figure>:
    // lleva dentro el número y el botón, que son el pie de esta miniatura.
    const pie = document.createElement('figcaption');
    pie.className = 'vista-pie';
    const numero = document.createElement('span');
    numero.className = 'vista-numero';
    numero.textContent = String(pagina);
    pie.appendChild(numero);
    pie.appendChild(botonTexto(
      'vista-descartar',
      fuera ? 'Recuperar' : 'Descartar',
      fuera ? `Recuperar la página ${pagina}` : `Descartar la página ${pagina}`,
      { descartar: pagina },
    ));
    figura.appendChild(pie);
    return figura;
  }

  function seccionGrupo(numero, inicio, fin, esUltimo) {
    const seccion = document.createElement('section');
    seccion.className = 'vista-grupo';
    const cabecera = document.createElement('header');
    cabecera.className = 'vista-grupo-cabecera';
    const titulo = document.createElement('h3');
    titulo.className = 'vista-grupo-titulo';
    const paginas = fin - inicio + 1;
    titulo.textContent = `Documento ${numero} · ${paginas === 1 ? '1 página' : paginas + ' páginas'}`;
    cabecera.appendChild(titulo);
    if (!esUltimo) {
      cabecera.appendChild(botonTexto(
        'vista-unir btn-secondary',
        'Unir con el siguiente',
        `Unir el documento ${numero} con el siguiente`,
        { unir: fin },
      ));
    }
    seccion.appendChild(cabecera);
    const fila = document.createElement('div');
    fila.className = 'vista-fila';
    seccion.appendChild(fila);
    return { seccion, fila };
  }

  function seccionFuera() {
    const seccion = document.createElement('section');
    seccion.className = 'vista-grupo vista-fuera';
    const cabecera = document.createElement('header');
    cabecera.className = 'vista-grupo-cabecera';
    const titulo = document.createElement('h3');
    titulo.className = 'vista-grupo-titulo';
    titulo.textContent = 'Fuera de los archivos';
    cabecera.appendChild(titulo);
    seccion.appendChild(cabecera);
    const fila = document.createElement('div');
    fila.className = 'vista-fila';
    seccion.appendChild(fila);
    return { seccion, fila };
  }

  // Recorre las páginas en orden y abre un recuadro por grupo derivado; las
  // descartadas van en un recuadro aparte, en su sitio, para que se vea que
  // están fuera y se puedan recuperar de un clic.
  function dibujar(grupos) {
    const grupoDe = new Map();
    grupos.forEach(([inicio, fin], indice) => {
      for (let pagina = inicio; pagina <= fin; pagina++) grupoDe.set(pagina, indice);
    });

    contenedor.textContent = '';
    let claveActual = null;
    let fila = null;
    for (let pagina = 1; pagina <= total; pagina++) {
      const indice = grupoDe.has(pagina) ? grupoDe.get(pagina) : null;
      const clave = indice === null ? 'fuera' : 'g' + indice;
      if (clave !== claveActual) {
        const nodo = indice === null
          ? seccionFuera()
          : seccionGrupo(indice + 1, grupos[indice][0], grupos[indice][1], indice === grupos.length - 1);
        contenedor.appendChild(nodo.seccion);
        fila = nodo.fila;
        claveActual = clave;
      }
      fila.appendChild(figuraDe(pagina));
      if (indice !== null && pagina < grupos[indice][1]) {
        fila.appendChild(botonTexto(
          'vista-cortar',
          '✂',
          `Cortar después de la página ${pagina}`,
          { corte: pagina },
        ));
      }
    }

    if (observador) {
      lienzos.forEach((lienzo) => { if (!lienzo.dataset.listo) observador.observe(lienzo); });
    } else {
      for (let pagina = 1; pagina <= total; pagina++) dibujarPagina(pagina);
    }
  }

  // Única salida del estado: redibuja, reescribe el campo y actualiza el resumen.
  function refrescar(foco) {
    const grupos = gruposDerivados();
    dibujar(grupos);
    campoGrupos.value = formatearGrupos(grupos);
    if (typeof actualizarRecuentoDivision === 'function') actualizarRecuentoDivision();
    if (resumen) {
      const incluidas = total - descartadas.size;
      resumen.textContent = grupos.length === 0
        ? 'Ningún archivo: todas las páginas están descartadas.'
        : `${grupos.length} ${grupos.length === 1 ? 'documento' : 'documentos'} · `
          + `${incluidas === 1 ? '1 página' : incluidas + ' páginas'}`;
    }
    if (foco) {
      const destino = contenedor.querySelector(foco);
      if (destino) destino.focus();
    }
  }

  // ── Acciones ─────────────────────────────────────────────────────
  function cortar(pagina) {
    cortes.add(pagina);
    // Lo contrario de cortar aquí es unir aquí: el foco va al botón que lo deshace.
    refrescar(`[data-unir="${pagina}"]`);
  }

  // Unir dos documentos seguidos: se quitan los cortes del tramo y se recuperan
  // las páginas descartadas que hubiera en medio, porque el resultado tiene que
  // ser un tramo seguido. Se ve al instante en el redibujado.
  function unir(fin) {
    const grupos = gruposDerivados();
    const indice = grupos.findIndex(([, f]) => f === fin);
    if (indice < 0 || indice >= grupos.length - 1) return;
    const hasta = grupos[indice + 1][1];
    for (let pagina = fin; pagina < hasta; pagina++) {
      cortes.delete(pagina);
      if (pagina > fin) descartadas.delete(pagina);
    }
    refrescar(`[data-corte="${fin}"]`);
  }

  function alternarDescarte(pagina) {
    if (descartadas.has(pagina)) descartadas.delete(pagina);
    else descartadas.add(pagina);
    refrescar(`[data-descartar="${pagina}"]`);
  }

  function reagrupar() {
    const resultado = gruposPorBloques(total, Number(campoN.value));
    if (resultado.error) { aviso(resultado.error); return; }
    sembrarCortes(resultado.grupos);
    refrescar(null);
  }

  // ── Abrir y cerrar ───────────────────────────────────────────────
  function cerrar(devolverFoco) {
    if (!abierta) return;
    abierta = false;
    vista.hidden = true;
    if (observador) observador.disconnect();
    contenedor.textContent = '';
    campoGrupos.readOnly = false;
    if (btnRellenar) btnRellenar.disabled = false;
    btnAbrir.setAttribute('aria-expanded', 'false');
    btnAbrir.textContent = 'Ver páginas';
    if (devolverFoco) btnAbrir.focus();
  }

  async function cargarDocumento(elArchivo) {
    if (documento && archivo === elArchivo) return;
    if (documento) {
      // En PDF.js 6 lo que se destruye es la tarea de carga, no el documento: el
      // proxy no tiene destroy(). Se espera a que termine para no solapar workers.
      await documento.loadingTask.destroy();
      documento = null;
    }
    if (observador) observador.disconnect();
    lienzos.clear();
    archivo = elArchivo;
    if (!pdfjs) {
      const modulo = await import(vista.dataset.pdfjs);
      modulo.GlobalWorkerOptions.workerSrc = vista.dataset.worker;
      pdfjs = modulo;
    }
    documento = await pdfjs.getDocument({ data: await elArchivo.arrayBuffer() }).promise;
  }

  async function abrir() {
    total = Number(window._totalPaginasDivision) || 0;
    if (!total) { aviso('Sube primero el PDF para saber cuántas páginas tiene'); return; }

    const item = document.querySelector('#panel-division .file-item');
    if (!item || !item._fileObj) { aviso('Sube primero el PDF para ver sus páginas'); return; }

    if (campoRellenarN && campoN) campoN.value = campoRellenarN.value;

    // Se lee el campo una sola vez al abrir; si está vacío, se siembra cada N.
    const texto = campoGrupos.value;
    const resultado = texto.trim()
      ? analizarGrupos(texto, total)
      : gruposPorBloques(total, Number(campoN.value));
    if (resultado.error) { aviso(resultado.error); return; }

    sembrar(resultado.grupos);
    abierta = true;
    vista.hidden = false;
    campoGrupos.readOnly = true;
    // «Rellenar cada N páginas» también escribe el campo: con la vista abierta
    // lo dejaría diciendo algo distinto de lo que se ve. Su equivalente dentro
    // de la vista es «Reagrupar», que sí pasa por el estado.
    if (btnRellenar) btnRellenar.disabled = true;
    btnAbrir.setAttribute('aria-expanded', 'true');
    btnAbrir.textContent = 'Ocultar páginas';
    if (resumen) resumen.textContent = 'Cargando las páginas…';

    try {
      await cargarDocumento(item._fileObj);
    } catch (err) {
      archivo = null;
      documento = null;
      cerrar(true);
      aviso(err && err.name === 'PasswordException'
        ? AVISO_CIFRADO
        : 'No se pudieron dibujar las páginas de este PDF');
      return;
    }
    if (!abierta) return;   // se cerró mientras cargaba
    refrescar(null);
  }

  // ── Eventos ──────────────────────────────────────────────────────
  btnAbrir.addEventListener('click', () => { if (abierta) cerrar(false); else abrir(); });
  btnCerrar?.addEventListener('click', () => cerrar(true));
  btnReagrupar?.addEventListener('click', reagrupar);

  // Un solo número de reagrupar: el de la vista es el mismo campo trasladado,
  // así que los dos se copian en los dos sentidos.
  campoN?.addEventListener('input', () => {
    if (campoRellenarN) campoRellenarN.value = campoN.value;
  });
  campoRellenarN?.addEventListener('input', () => {
    if (campoN) campoN.value = campoRellenarN.value;
  });

  contenedor.addEventListener('click', (evento) => {
    const boton = evento.target.closest('button');
    if (!boton || !contenedor.contains(boton)) return;
    if (boton.dataset.corte) cortar(Number(boton.dataset.corte));
    else if (boton.dataset.unir) unir(Number(boton.dataset.unir));
    else if (boton.dataset.descartar) alternarDescarte(Number(boton.dataset.descartar));
  });

  // Si cambia o se quita el PDF, la vista dejaría de corresponder al archivo: se cierra.
  const lista = document.querySelector('#panel-division .file-list');
  if (lista && 'MutationObserver' in window) {
    new MutationObserver(() => {
      if (!abierta) return;
      const item = document.querySelector('#panel-division .file-item');
      if (!item || item._fileObj !== archivo) cerrar(false);
    }).observe(lista, { childList: true });
  }
})();
