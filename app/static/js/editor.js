// PDF ToolOffice — editor.js
// Editor de PDF en dos modos sobre una misma sesión del servidor (con versiones):
//  · "Anotar, firmar y páginas": visor PDF.js (Mozilla, Apache-2.0) con sus
//    herramientas de edición: texto libre, dibujo, firmas, imágenes, resaltado,
//    comentarios, formularios y organización de páginas.
//  · "Editar texto existente": reemplazo de texto en el servidor con PyMuPDF,
//    conservando fuente, tamaño, color y línea base.

(function () {
  const API = '/api/edicion';
  const CLAVE_SESION = 'pdftool.edicion';

  const $ = id => document.getElementById(id);
  const zona        = $('ed-zona');
  const inputArchivo = $('ed-input');
  const inputClave  = $('ed-contrasena');
  const tarjetaCarga = $('ed-carga');
  const espacio     = $('ed-espacio');
  const lblNombre   = $('ed-nombre');
  const lblEstado   = $('ed-estado');
  const btnDeshacer = $('ed-deshacer');
  const btnGuardar  = $('ed-guardar');
  const btnDescargar = $('ed-descargar');
  const btnCerrar   = $('ed-cerrar');
  const chkAplanar  = $('ed-aplanar');
  const vistaAnotar = $('ed-vista-anotar');
  const vistaTexto  = $('ed-vista-texto');
  const iframe      = $('ed-visor');
  const inputPagina = $('ed-pagina');
  const lblTotal    = $('ed-total');
  const btnPrev     = $('ed-prev');
  const btnNext     = $('ed-next');
  const selAlineacion = $('ed-alineacion');
  const lblCampos   = $('ed-campos-count');
  const aviso       = $('ed-aviso');
  const escenario   = $('ed-escenario');
  const img         = $('ed-img');
  const overlays    = $('ed-overlays');
  const cargando    = $('ed-cargando');

  if (!zona || !iframe) return;

  const estado = {
    sesion: null,          // {id, nombre, version, paginas, puede_deshacer}
    modo: 'anotar',
    pagina: 0,
    versionVisor: null,    // versión cargada en el visor PDF.js
    versionTexto: null,    // versión/página dibujada en el modo texto
    ocupado: false,
    confirmarDescartar: false,
    confirmarCerrar: false,
  };

  // ── Utilidades ──────────────────────────────────────────────────
  async function api(ruta, opciones = {}) {
    const res = await fetch(API + ruta, opciones);
    if (res.status === 204) return null;
    const tipo = res.headers.get('Content-Type') || '';
    const datos = tipo.includes('application/json') ? await res.json() : null;
    if (!res.ok) {
      const err = new Error((datos && datos.error) || `Error ${res.status}`);
      err.status = res.status;
      throw err;
    }
    return datos;
  }

  function setOcupado(v, texto) {
    estado.ocupado = v;
    [btnDeshacer, btnGuardar, btnDescargar, btnCerrar].forEach(b => { if (b) b.disabled = v; });
    if (cargando) {
      cargando.hidden = !v || estado.modo !== 'texto';
      const span = cargando.querySelector('span');
      if (span) span.textContent = texto || 'Procesando…';
    }
    if (v) lblEstado.textContent = texto || 'Procesando…';
    else actualizarEstado();
  }

  function actualizarEstado() {
    if (!estado.sesion) return;
    const s = estado.sesion;
    lblNombre.textContent = s.nombre;
    lblEstado.textContent = `Versión ${s.version} · ${s.paginas} pág.`;
    btnDeshacer.disabled = estado.ocupado;
  }

  function aplicarSesion(datos) {
    estado.sesion = {
      id: datos.id, nombre: datos.nombre, version: datos.version,
      paginas: datos.paginas, puede_deshacer: datos.puede_deshacer,
    };
    if (estado.pagina >= datos.paginas) estado.pagina = Math.max(0, datos.paginas - 1);
    try { sessionStorage.setItem(CLAVE_SESION, datos.id); } catch (e) { /* almacenamiento no disponible */ }
    actualizarEstado();
  }

  // ── Carga de archivo / sesión ───────────────────────────────────
  async function crearSesion(file) {
    if (estado.ocupado) return;
    if (!file.name.toLowerCase().endsWith('.pdf')) { showToast('Selecciona un archivo PDF'); return; }
    if (file.size > MAX_BYTES) { showToast(`"${file.name}" supera el límite de ${MAX_MB} MB`); return; }
    if (estado.sesion) await cerrarSesion(true);

    setOcupado(true, 'Subiendo PDF…');
    try {
      const fd = new FormData();
      fd.append('archivo', file);
      if (inputClave.value) fd.append('contrasena', inputClave.value);
      const datos = await api('', { method: 'POST', body: fd });
      inputClave.value = '';
      estado.pagina = 0;
      abrirEspacio(datos);
      if (datos.desbloqueado) showToast('PDF desbloqueado: el archivo descargado no tendrá contraseña');
      else showToast('PDF cargado');
    } catch (err) {
      showToast(`Error: ${err.message}`);
    } finally {
      setOcupado(false);
      inputArchivo.value = '';
    }
  }

  function abrirEspacio(datos) {
    aplicarSesion(datos);
    estado.versionVisor = null;
    estado.versionTexto = null;
    tarjetaCarga.hidden = true;
    espacio.hidden = false;
    // Con la pestaña oculta el visor no puede medir la página: se carga al mostrarla.
    if (panelVisible()) cambiarModo(estado.modo, true);
  }

  function panelVisible() {
    return !!document.getElementById('panel-editar')?.classList.contains('active');
  }

  async function reanudarSesion() {
    let id = null;
    try { id = sessionStorage.getItem(CLAVE_SESION); } catch (e) { /* sin almacenamiento */ }
    if (!id) return;
    try {
      abrirEspacio(await api(`/${id}`));
    } catch (err) {
      try { sessionStorage.removeItem(CLAVE_SESION); } catch (e) { /* sin almacenamiento */ }
    }
  }

  async function cerrarSesion(silencioso) {
    const s = estado.sesion;
    estado.sesion = null;
    try { sessionStorage.removeItem(CLAVE_SESION); } catch (e) { /* sin almacenamiento */ }
    espacio.hidden = true;
    tarjetaCarga.hidden = false;
    overlays.replaceChildren();
    img.removeAttribute('src');
    estado.versionVisor = null;
    estado.versionTexto = null;
    const app = visorApp();
    if (app && app.pdfDocument) { try { await app.close(); } catch (e) { /* visor ya cerrado */ } }
    if (s) { try { await api(`/${s.id}`, { method: 'DELETE' }); } catch (e) { /* expirada */ } }
    if (!silencioso) showToast('Documento cerrado');
  }

  // ── Visor PDF.js ────────────────────────────────────────────────
  let visorListo = null;
  let capturaPendiente = null;

  // El visor avisa antes de inicializarse: aquí se fijan sus opciones.
  document.addEventListener('webviewerloaded', e => {
    const opciones = e.detail && e.detail.source && e.detail.source.PDFViewerApplicationOptions;
    if (!opciones) return;
    opciones.set('defaultUrl', '');
    opciones.set('disablePreferences', true);  // que localStorage no pise estas opciones
    opciones.set('annotationEditorMode', 0);    // herramientas de edición activas
    opciones.set('enableSignatureEditor', true);
    opciones.set('enableComment', true);
    opciones.set('enableHighlightFloatingButton', true);
    opciones.set('enableSplitMerge', true);     // borrar, mover y copiar páginas
    opciones.set('enableAltText', false);
    opciones.set('externalLinkTarget', 2);      // enlaces del PDF en pestaña nueva
    opciones.set('viewerCssTheme', 1);          // visor claro, como los demás recuadros de la app
  });

  function visorApp() {
    try { return iframe.contentWindow && iframe.contentWindow.PDFViewerApplication; } catch (e) { return null; }
  }

  function asegurarVisor() {
    if (visorListo) return visorListo;
    visorListo = new Promise((resolve, reject) => {
      iframe.addEventListener('load', async () => {
        try {
          const app = visorApp();
          await app.initializedPromise;
          ajustarControlesVisor();
          // Las descargas que pide la barra propia se capturan para subirlas a la sesión.
          // Las que inicia el visor por su cuenta (Ctrl+S, "Exportar selección…") se
          // entregan tal cual: pueden ser solo una parte del documento.
          app.downloadManager.download = (data, _url, nombre) => {
            if (capturaPendiente) {
              const p = capturaPendiente;
              capturaPendiente = null;
              p.resolve(data);
            } else {
              descargarBytes(data, nombre || (estado.sesion && estado.sesion.nombre) || 'documento.pdf');
            }
          };
          resolve(app);
        } catch (err) {
          reject(err);
        }
      }, { once: true });
      iframe.src = iframe.dataset.src;
    });
    return visorListo;
  }

  // Oculta controles que romperían la sesión y acomoda la barra en celulares (ver visor.css).
  // Va como <link> porque la CSP de viewer.html bloquea los <style> en línea.
  function ajustarControlesVisor() {
    const doc = iframe.contentDocument;
    const hoja = doc.createElement('link');
    hoja.rel = 'stylesheet';
    hoja.href = iframe.dataset.css;
    doc.head.appendChild(hoja);
  }

  async function cargarVisor() {
    const app = await asegurarVisor();
    const s = estado.sesion;
    if (!s) return;
    const paginaPrevia = app.pdfDocument ? app.page : estado.pagina + 1;
    // El aviso "N páginas eliminadas · Deshacer" del visor pertenece al documento anterior.
    const avisoPaginas = iframe.contentDocument.getElementById('viewsManagerStatusUndoCloseButton');
    if (avisoPaginas && avisoPaginas.offsetParent !== null) avisoPaginas.click();
    app.eventBus.on('pagesinit', () => {
      app.page = Math.min(Math.max(1, paginaPrevia), app.pagesCount);
    }, { once: true });
    // Hasta 840 px PDF.js pone el panel lateral encima de la página: que no se abra solo
    // aunque el PDF lo pida (índice de marcadores); el usuario lo abre con su botón.
    iframe.contentWindow.PDFViewerApplicationOptions.set('sidebarViewOnLoad', iframe.clientWidth <= 840 ? 0 : -1);
    await app.open({ url: `${API}/${s.id}/pdf?v=${s.version}` });
    estado.versionVisor = s.version;
  }

  function hayCambiosVisor() {
    const app = visorApp();
    if (!app || !app.pdfDocument || estado.versionVisor === null) return false;
    const storage = app.pdfDocument.annotationStorage;
    const estructura = app.pdfThumbnailViewer && app.pdfThumbnailViewer.hasStructuralChanges
      && app.pdfThumbnailViewer.hasStructuralChanges();
    return (storage && storage.size > 0) || !!estructura;
  }

  // Obtiene el PDF con los cambios usando la propia lógica de guardado del visor.
  function capturarPdfVisor(app) {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        capturaPendiente = null;
        reject(new Error('El visor no respondió al guardar'));
      }, 120000);
      capturaPendiente = {
        resolve: data => { clearTimeout(timer); resolve(data); },
      };
      app.downloadOrSave().catch(err => {
        clearTimeout(timer);
        capturaPendiente = null;
        reject(err);
      });
    });
  }

  // Sube los cambios del visor como nueva versión. Retorna true si guardó, null si no había cambios.
  async function guardarCambiosVisor(datosCapturados) {
    const s = estado.sesion;
    if (!s) return false;
    if (!datosCapturados && !hayCambiosVisor()) return null;
    setOcupado(true, 'Guardando cambios…');
    try {
      const datos = datosCapturados || await capturarPdfVisor(visorApp());
      if (!datos || !datos.byteLength) throw new Error('El visor no entregó el documento');
      const fd = new FormData();
      fd.append('archivo', new Blob([datos], { type: 'application/pdf' }), 'visor.pdf');
      aplicarSesion(await api(`/${s.id}/version`, { method: 'POST', body: fd }));
      estado.versionTexto = null;
      await cargarVisor();
      showToast('Cambios guardados ✓');
      return true;
    } catch (err) {
      showToast(`Error al guardar: ${err.message}`);
      return false;
    } finally {
      setOcupado(false);
    }
  }

  // ── Modos ───────────────────────────────────────────────────────
  async function cambiarModo(modo, forzar) {
    if (!estado.sesion) return;
    if (modo === estado.modo && !forzar) return;
    if (estado.modo === 'anotar' && modo !== 'anotar') {
      if (hayCambiosVisor()) {
        const ok = await guardarCambiosVisor();
        if (ok === false) return;
      }
      const app = visorApp();
      if (app && app.pdfDocument) estado.pagina = app.page - 1;  // seguir en la misma página
    }
    estado.modo = modo;
    document.querySelectorAll('.ed-modo').forEach(b => {
      const activo = b.dataset.modo === modo;
      b.classList.toggle('active', activo);
      b.setAttribute('aria-selected', activo ? 'true' : 'false');
    });
    vistaAnotar.hidden = modo !== 'anotar';
    vistaTexto.hidden = modo !== 'texto';
    btnGuardar.hidden = modo !== 'anotar';

    if (modo === 'anotar') {
      ajustarVisor(true);
      if (estado.versionVisor !== estado.sesion.version) {
        try { await cargarVisor(); } catch (err) { showToast(`Error al abrir el visor: ${err.message}`); }
      }
    } else {
      await cargarPaginaTexto(estado.pagina);
    }
  }

  // El visor ocupa el alto de la ventana bajo la barra fija; desplazar lo deja a la vista.
  function ajustarVisor(desplazar) {
    if (espacio.hidden || vistaAnotar.hidden) return;
    const barra = espacio.querySelector('.ed-barra');
    const cabecera = document.querySelector('.header');
    const fija = getComputedStyle(barra).position === 'sticky';
    const altoCabecera = cabecera && getComputedStyle(cabecera).position === 'sticky' ? cabecera.offsetHeight : 0;
    const arriba = altoCabecera + 8 + (fija ? barra.offsetHeight + 10 : 0);
    iframe.style.height = `${Math.max(420, window.innerHeight - arriba - 12)}px`;
    if (desplazar) {
      window.scrollTo({ top: iframe.getBoundingClientRect().top + window.scrollY - arriba, behavior: 'smooth' });
    }
  }

  // ── Modo texto ──────────────────────────────────────────────────
  function familiaCss(fuente) {
    const f = (fuente || '').toLowerCase();
    if (/courier|mono|consol/.test(f)) return '"Courier New", monospace';
    if (/times|serif|georgia|cambria|garamond|book/.test(f) && !/sans/.test(f)) return '"Times New Roman", serif';
    return 'Arial, Helvetica, sans-serif';
  }

  function dpiParaPantalla(anchoPt) {
    const ancho = Math.max(320, escenario.parentElement.clientWidth - 24);
    const dpi = (ancho / anchoPt) * 72 * (window.devicePixelRatio || 1);
    return Math.round(Math.min(200, Math.max(72, dpi)));
  }

  async function cargarPaginaTexto(pagina) {
    const s = estado.sesion;
    if (!s) return;
    pagina = Math.min(Math.max(0, pagina), s.paginas - 1);
    estado.pagina = pagina;
    inputPagina.value = pagina + 1;
    inputPagina.max = s.paginas;
    lblTotal.textContent = s.paginas;
    btnPrev.disabled = pagina === 0;
    btnNext.disabled = pagina >= s.paginas - 1;

    setOcupado(true, 'Cargando página…');
    try {
      const datos = await api(`/${s.id}/paginas/${pagina}/campos`);
      const dpi = dpiParaPantalla(datos.ancho);
      escenario.style.aspectRatio = `${datos.ancho} / ${datos.alto}`;
      escenario.style.maxWidth = `${Math.round(datos.ancho * 2)}px`;
      await new Promise((resolve, reject) => {
        img.onload = resolve;
        img.onerror = () => reject(new Error('No se pudo cargar la imagen de la página'));
        img.src = `${API}/${s.id}/paginas/${pagina}/imagen?dpi=${dpi}&v=${s.version}`;
      });
      dibujarCampos(datos);
      estado.versionTexto = `${s.version}:${pagina}`;

      const editables = datos.campos.filter(c => c.editable).length;
      lblCampos.textContent = `${editables} texto${editables === 1 ? '' : 's'} editable${editables === 1 ? '' : 's'}`;
      if (datos.escaneada) {
        aviso.textContent = 'Esta página parece escaneada (es una imagen, no tiene texto real). '
          + 'Para escribir encima o tapar contenido usa el modo "Anotar, firmar y páginas".';
        aviso.hidden = false;
      } else if (!datos.campos.length) {
        aviso.textContent = 'No se encontró texto editable en esta página.';
        aviso.hidden = false;
      } else {
        aviso.hidden = true;
      }
    } catch (err) {
      showToast(`Error: ${err.message}`);
    } finally {
      setOcupado(false);
    }
  }

  function dibujarCampos(datos) {
    const frag = document.createDocumentFragment();
    datos.campos.forEach(campo => {
      const [x0, y0, x1, y1] = campo.vista;
      const el = document.createElement('div');
      el.className = 'editor-field' + (campo.editable ? '' : ' no-editable');
      el.style.left = `${(x0 / datos.ancho) * 100}%`;
      el.style.top = `${(y0 / datos.alto) * 100}%`;
      el.style.width = `${((x1 - x0) / datos.ancho) * 100}%`;
      el.style.height = `${((y1 - y0) / datos.alto) * 100}%`;
      el.title = campo.editable ? `${campo.texto}\n${campo.fuente} · ${campo.tamano} pt — clic para editar`
                                : 'Texto inclinado: edítalo desde el modo Anotar';
      if (campo.editable) el.addEventListener('click', () => editarCampo(el, campo, datos));
      frag.appendChild(el);
    });
    overlays.replaceChildren(frag);
  }

  function editarCampo(el, campo, datos) {
    if (estado.ocupado || el.classList.contains('editing')) return;
    el.classList.add('editing');
    const escala = escenario.clientWidth / datos.ancho;
    const input = document.createElement('input');
    input.type = 'text';
    input.value = campo.texto;
    input.spellcheck = false;
    input.maxLength = 200;
    input.setAttribute('aria-label', 'Nuevo texto');
    input.style.fontSize = `${Math.max(9, campo.tamano * escala)}px`;
    input.style.fontFamily = familiaCss(campo.fuente);
    input.style.fontWeight = campo.negrita ? '700' : '400';
    input.style.fontStyle = campo.cursiva ? 'italic' : 'normal';
    input.style.color = campo.color;
    el.appendChild(input);
    const ajustarAncho = () => { input.style.width = '0'; input.style.width = `${Math.max(el.clientWidth - 4, input.scrollWidth + 6)}px`; };
    input.addEventListener('input', ajustarAncho);
    ajustarAncho();
    input.focus();
    input.select();

    let terminado = false;
    const cancelar = () => {
      if (terminado) return;
      terminado = true;
      input.remove();
      el.classList.remove('editing');
    };
    const guardar = async () => {
      if (terminado) return;
      const nuevo = input.value;
      if (nuevo === campo.texto) { cancelar(); return; }
      terminado = true;
      input.disabled = true;
      await reemplazarTexto(campo, nuevo);
    };
    input.addEventListener('keydown', e => {
      if (e.key === 'Enter') { e.preventDefault(); guardar(); }
      if (e.key === 'Escape') { e.preventDefault(); cancelar(); }
    });
    input.addEventListener('blur', guardar);
  }

  async function reemplazarTexto(campo, nuevo) {
    const s = estado.sesion;
    setOcupado(true, nuevo.trim() ? 'Reemplazando texto…' : 'Borrando texto…');
    let resp = null;
    try {
      resp = await api(`/${s.id}/reemplazar`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          pagina: estado.pagina,
          bbox: campo.bbox,
          texto_original: campo.texto,
          texto_nuevo: nuevo.trim() ? nuevo : '',
          alineacion: selAlineacion.value,
        }),
      });
      aplicarSesion(resp);
    } catch (err) {
      showToast(`Error: ${err.message}`);
    } finally {
      setOcupado(false);
    }
    await cargarPaginaTexto(estado.pagina);
    if (resp) avisarResultado(resp.metadata);
  }

  function avisarResultado(m) {
    if (!m) return;
    if (m.eliminado) { showToast('Texto borrado ✓'); return; }
    const avisos = [];
    if (m.fuente_aproximada) avisos.push(`fuente similar (${m.fuente_usada}): "${m.fuente_original}" no está instalada`);
    if (m.tamano_reducido) avisos.push(`tamaño reducido a ${m.tamano} pt para que quepa`);
    if (m.desborda) avisos.push('el texto es más largo que el espacio disponible');
    showToast(avisos.length ? `Texto actualizado · ${avisos.join(' · ')}` : 'Texto actualizado ✓');
  }

  // ── Acciones comunes ────────────────────────────────────────────
  function descargarBytes(datos, nombre) {
    const blob = datos instanceof Blob ? datos : new Blob([datos], { type: 'application/pdf' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = nombre;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  }

  async function deshacer() {
    const s = estado.sesion;
    if (!s || estado.ocupado) return;
    if (estado.modo === 'anotar' && hayCambiosVisor()) {
      if (!estado.confirmarDescartar) {
        estado.confirmarDescartar = true;
        setTimeout(() => { estado.confirmarDescartar = false; }, 5000);
        showToast('Hay cambios sin guardar en el visor. Usa Ctrl+Z para deshacerlos uno a uno, o pulsa Deshacer otra vez para descartarlos todos.');
        return;
      }
      estado.confirmarDescartar = false;
      await cargarVisor();
      showToast('Cambios sin guardar descartados');
      return;
    }
    if (!s.puede_deshacer) { showToast('No hay cambios para deshacer'); return; }
    setOcupado(true, 'Deshaciendo…');
    try {
      aplicarSesion(await api(`/${s.id}/deshacer`, { method: 'POST' }));
      showToast('Cambio deshecho');
    } catch (err) {
      showToast(`Error: ${err.message}`);
    } finally {
      setOcupado(false);
    }
    if (estado.modo === 'anotar') await cargarVisor();
    else await cargarPaginaTexto(estado.pagina);
  }

  async function descargar() {
    const s = estado.sesion;
    if (!s || estado.ocupado) return;
    if (estado.modo === 'anotar' && hayCambiosVisor()) {
      const ok = await guardarCambiosVisor();
      if (ok === false) return;
    }
    setOcupado(true, 'Preparando descarga…');
    try {
      const res = await fetch(`${API}/${s.id}/descargar?aplanar=${chkAplanar.checked ? 1 : 0}`);
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.error || `Error ${res.status}`);
      }
      const disposition = res.headers.get('Content-Disposition') || '';
      const m = disposition.match(/filename\*=UTF-8''([^;]+)/i) || disposition.match(/filename="?([^";]+)"?/i);
      descargarBytes(await res.blob(), m ? decodeURIComponent(m[1]) : 'documento_editado.pdf');
      showToast('Descarga lista ✓');
    } catch (err) {
      showToast(`Error al descargar: ${err.message}`);
    } finally {
      setOcupado(false);
    }
  }

  function pedirCierre() {
    if (estado.modo === 'anotar' && hayCambiosVisor() && !estado.confirmarCerrar) {
      estado.confirmarCerrar = true;
      setTimeout(() => { estado.confirmarCerrar = false; }, 5000);
      showToast('Hay cambios sin guardar. Pulsa Cerrar otra vez para descartarlos.');
      return;
    }
    estado.confirmarCerrar = false;
    cerrarSesion(false);
  }

  // ── Eventos ─────────────────────────────────────────────────────
  zona.addEventListener('dragover', e => { e.preventDefault(); zona.classList.add('dragover'); });
  zona.addEventListener('dragleave', () => zona.classList.remove('dragover'));
  zona.addEventListener('drop', e => {
    e.preventDefault();
    zona.classList.remove('dragover');
    if (e.dataTransfer.files.length) crearSesion(e.dataTransfer.files[0]);
  });
  inputArchivo.addEventListener('change', () => {
    if (inputArchivo.files.length) crearSesion(inputArchivo.files[0]);
  });

  document.querySelectorAll('.ed-modo').forEach(b => b.addEventListener('click', () => cambiarModo(b.dataset.modo)));
  btnGuardar.addEventListener('click', async () => {
    const ok = await guardarCambiosVisor();
    if (ok === null) showToast('No hay cambios nuevos en el visor');
  });
  btnDeshacer.addEventListener('click', deshacer);
  btnDescargar.addEventListener('click', descargar);
  btnCerrar.addEventListener('click', pedirCierre);

  btnPrev.addEventListener('click', () => cargarPaginaTexto(estado.pagina - 1));
  btnNext.addEventListener('click', () => cargarPaginaTexto(estado.pagina + 1));
  inputPagina.addEventListener('change', () => {
    const n = parseInt(inputPagina.value, 10);
    if (Number.isFinite(n)) cargarPaginaTexto(n - 1);
  });

  let redimension = null;
  window.addEventListener('resize', () => {
    clearTimeout(redimension);
    redimension = setTimeout(() => {
      ajustarVisor(false);
      if (estado.sesion && estado.modo === 'texto' && !vistaTexto.hidden) cargarPaginaTexto(estado.pagina);
    }, 400);
  });

  // Al mostrar la pestaña se precarga el visor y se pinta la sesión pendiente (p. ej. reanudada).
  document.querySelector('.nav-tab[data-panel="editar"]')?.addEventListener('click', () => {
    asegurarVisor().catch(() => {});
    const s = estado.sesion;
    if (!s || estado.ocupado) return;
    const pendiente = estado.modo === 'anotar' ? estado.versionVisor !== s.version : !estado.versionTexto;
    if (pendiente) cambiarModo(estado.modo, true);
    else ajustarVisor(true);
  });
  reanudarSesion();
})();
