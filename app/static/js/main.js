// PDF ToolOffice — main.js (conectado al back Flask)

const MAX_MB    = 50;
const MAX_BYTES = MAX_MB * 1024 * 1024;

// ── Tab navigation ────────────────────────────────────────────────
const tabs = Array.from(document.querySelectorAll('.nav-tab'));

function activarTab(tab) {
  tabs.forEach(t => {
    const activa = t === tab;
    t.classList.toggle('active', activa);
    t.setAttribute('aria-selected', activa ? 'true' : 'false');
    t.tabIndex = activa ? 0 : -1;
  });
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.getElementById('panel-' + tab.dataset.panel).classList.add('active');
  // El color de la herramienta tiñe la cabecera, los pasos y los botones.
  document.body.dataset.herramienta = tab.dataset.panel;
  // El editor necesita todo el ancho de la ventana.
  document.body.classList.toggle('modo-ancho', tab.dataset.panel === 'editar');
  // La dirección refleja la herramienta: se puede guardar como favorito (…/#compresion)
  history.replaceState(null, '', '#' + tab.dataset.panel);
}

// Abrir la herramienta del enlace; tras cargar editor.js, que también escucha el clic en "Editar".
window.addEventListener('DOMContentLoaded', () => {
  const inicial = tabs.find(t => '#' + t.dataset.panel === location.hash);
  if (inicial) inicial.click();
});

tabs.forEach((tab, i) => {
  tab.addEventListener('click', () => activarTab(tab));
  // Flechas, Inicio y Fin mueven entre pestañas (patrón ARIA de pestañas)
  tab.addEventListener('keydown', e => {
    const destino = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: tabs.length - 1 }[e.key];
    if (destino === undefined) return;
    e.preventDefault();
    const siguiente = tabs[(destino + tabs.length) % tabs.length];
    siguiente.focus();
    siguiente.click();
  });
});

// Mostrar/ocultar nivel de compresión en unión
document.getElementById('union-comprimir')?.addEventListener('change', function() {
  const wrap = document.getElementById('union-nivel-wrap');
  if (wrap) wrap.hidden = !this.checked;
});

// Cada modo de división muestra sus propios campos y oculta los de los otros
document.querySelectorAll('input[name="modo-div"]').forEach(radio => {
  radio.addEventListener('change', () => {
    const camposPorModo = {
      rango: 'div-rango-campos',
      cada: 'div-cada-campos',
      personalizado: 'div-grupos-campos',
    };
    Object.entries(camposPorModo).forEach(([modo, id]) => {
      const campos = document.getElementById(id);
      if (campos) campos.hidden = radio.value !== modo;
    });
  });
});

// ── División: recuento en vivo de los archivos que saldrán ─────────
// Total de páginas del PDF elegido en Dividir (null mientras no se sepa).
window._totalPaginasDivision = null;
// Por qué no se sabe: lo que respondió /api/paginas (un PDF cifrado, uno dañado…).
// Sin esto la pantalla callaba y, al pedir las páginas, decía "sube primero el PDF"
// de un archivo que ya estaba subido.
window._motivoSinTotalDivision = null;
let _archivoDivisionActual = null;

function textoRecuentoDivision(resultado, paginasUltimo) {
  if (resultado.error) return resultado.error;
  const cantidad = resultado.grupos.length;
  let texto = cantidad === 1 ? 'Saldrá 1 archivo.' : `Saldrán ${cantidad} archivos.`;
  if (paginasUltimo) {
    texto += ` El último archivo tendrá ${paginasUltimo === 1 ? '1 página' : paginasUltimo + ' páginas'}.`;
  }
  return texto;
}

function actualizarRecuentoDivision() {
  const total = window._totalPaginasDivision;
  // Sin total, en lugar de quedarse en blanco se dice por qué no se pudo leer el PDF.
  const motivo = window._motivoSinTotalDivision || '';
  const cuentaCada = document.getElementById('div-cuenta');
  const cuentaGrupos = document.getElementById('div-grupos-cuenta');

  if (cuentaCada) {
    const porArchivo = Number(document.getElementById('div-paginas-por-archivo').value);
    if (!total) {
      cuentaCada.textContent = motivo;
    } else {
      const resultado = gruposPorBloques(total, porArchivo);
      const grupos = resultado.grupos || [];
      const ultimo = grupos.length ? total - (grupos.length - 1) * porArchivo : 0;
      // Con un solo archivo, "el último archivo tendrá N páginas" no añade nada.
      const corto = grupos.length > 1 && ultimo < porArchivo ? ultimo : 0;
      cuentaCada.textContent = textoRecuentoDivision(resultado, corto);
    }
  }

  if (cuentaGrupos) {
    const texto = document.getElementById('div-grupos').value;
    if (!total) cuentaGrupos.textContent = motivo;
    else cuentaGrupos.textContent = texto.trim() ? textoRecuentoDivision(analizarGrupos(texto, total), 0) : '';
  }
}

function olvidarTotalDivision() {
  _archivoDivisionActual = null;
  window._totalPaginasDivision = null;
  window._motivoSinTotalDivision = null;
  actualizarRecuentoDivision();
}

document.getElementById('div-paginas-por-archivo')?.addEventListener('input', actualizarRecuentoDivision);
document.getElementById('div-grupos')?.addEventListener('input', actualizarRecuentoDivision);

document.getElementById('div-rellenar')?.addEventListener('click', () => {
  const total = window._totalPaginasDivision;
  if (!total) {
    showToast(window._motivoSinTotalDivision || 'Sube primero el PDF para saber cuántas páginas tiene');
    return;
  }
  const resultado = gruposPorBloques(total, Number(document.getElementById('div-rellenar-n').value));
  if (resultado.error) { showToast(resultado.error); return; }
  document.getElementById('div-grupos').value = formatearGrupos(resultado.grupos);
  actualizarRecuentoDivision();
});

// ── Upload zones ──────────────────────────────────────────────────
document.querySelectorAll('.upload-zone').forEach(zone => {
  zone.addEventListener('dragover',  e => { e.preventDefault(); zone.classList.add('dragover'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('dragover');
    handleFiles(zone, e.dataTransfer.files);
  });
  const input = zone.querySelector('input[type="file"]');
  if (input) input.addEventListener('change', () => handleFiles(zone, input.files));
});

function handleFiles(zone, files) {
  const listEl = zone.closest('.card').querySelector('.file-list');
  if (!listEl) return;
  // En las herramientas de un solo archivo, el nuevo reemplaza al anterior
  const input = zone.querySelector('input[type="file"]');
  if (input && !input.multiple && files.length) {
    listEl.innerHTML = '';
    // Si el que se va era el PDF de Dividir, el recuento no puede seguir
    // describiéndolo: el reemplazo puede ser rechazado (p. ej. por tamaño).
    if (listEl.closest('#panel-division')) olvidarTotalDivision();
  }
  Array.from(files).forEach(file => {
    if (file.size > MAX_BYTES) {
      // Sin la salida, quien escanea una tanda grande se queda sin siguiente paso.
      showToast(`"${file.name}" supera el límite de ${MAX_MB} MB. Reduce su tamaño en la pestaña Comprimir.`);
      return;
    }
    addFileItem(listEl, file);
    updatePreview(zone, file);
  });
}

function addFileItem(listEl, file) {
  const existing = Array.from(listEl.querySelectorAll('.file-name')).find(el => el.textContent === file.name);
  if (existing) return;
  const item = document.createElement('div');
  item.className = 'file-item';
  item._fileObj  = file;
  item.draggable = true;
  // Plantilla fija; el nombre del archivo se asigna con textContent (nunca como HTML).
  item.innerHTML = `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="cursor:grab;opacity:0.4">
      <line x1="8" y1="6" x2="16" y2="6"/><line x1="8" y1="12" x2="16" y2="12"/><line x1="8" y1="18" x2="16" y2="18"/>
    </svg>
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
      <polyline points="14 2 14 8 20 8"/>
    </svg>
    <span class="file-name"></span>
    <span class="file-size"></span>
    <button class="file-remove" type="button" title="Quitar" aria-label="Quitar archivo">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
        <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
      </svg>
    </button>`;
  item.querySelector('.file-name').textContent = file.name;
  item.querySelector('.file-size').textContent = formatSize(file.size);
  item.querySelector('.file-remove').addEventListener('click', () => {
    item.remove();
    if (listEl.closest('#panel-division')) olvidarTotalDivision();
  });

  // Drag to reorder
  item.addEventListener('dragstart', e => {
    e.dataTransfer.effectAllowed = 'move';
    item.classList.add('dragging');
  });
  item.addEventListener('dragend', () => item.classList.remove('dragging'));
  item.addEventListener('dragover', e => {
    e.preventDefault();
    const dragging = listEl.querySelector('.dragging');
    if (dragging && dragging !== item) {
      const rect = item.getBoundingClientRect();
      const mid  = rect.top + rect.height / 2;
      if (e.clientY < mid) listEl.insertBefore(dragging, item);
      else listEl.insertBefore(dragging, item.nextSibling);
    }
  });

  listEl.appendChild(item);
}

function togglePass(inputId, btn) {
  const input   = document.getElementById(inputId);
  const visible = input.type === 'password';
  input.type = visible ? 'text' : 'password';
  btn.setAttribute('aria-pressed', visible ? 'true' : 'false');
  btn.setAttribute('aria-label', visible ? 'Ocultar contraseña' : 'Mostrar contraseña');
}

function updatePreview(zone, file) {
  const card       = zone.closest('.card');
  const previewBox = card.querySelector('.preview-box');
  if (!previewBox) return;
  const nameEl  = previewBox.querySelector('.preview-name');
  const pagesEl = previewBox.querySelector('.preview-pages');
  if (nameEl)  nameEl.textContent  = file.name;
  if (pagesEl) pagesEl.textContent = 'Detectando páginas…';
  previewBox.hidden = false;

  const esDivision = !!zone.closest('#panel-division');
  if (esDivision) {
    olvidarTotalDivision();
    _archivoDivisionActual = file;
  }

  if (file.name.toLowerCase().endsWith('.pdf')) {
    const fd = new FormData();
    fd.append('archivo', file);
    fetch('/api/paginas', { method: 'POST', body: fd })
      .then(r => r.json())
      .then(d => {
        if (pagesEl) pagesEl.textContent = d.paginas ? `${d.paginas} páginas` : 'N/D';
        if (esDivision && _archivoDivisionActual === file) {
          window._totalPaginasDivision = d.paginas || null;
          window._motivoSinTotalDivision = d.paginas ? null : (d.error || null);
          actualizarRecuentoDivision();
        }
      })
      .catch(() => {
        if (pagesEl) pagesEl.textContent = 'N/D';
        if (esDivision && _archivoDivisionActual === file) {
          window._motivoSinTotalDivision = 'No se pudo leer el PDF para saber cuántas páginas tiene';
          actualizarRecuentoDivision();
        }
      });
  } else {
    if (pagesEl) pagesEl.textContent = formatSize(file.size);
  }
}

// ── Proceso genérico con fetch ─────────────────────────────────────
async function procesarConFetch(panel, endpoint, buildFormData) {
  const progressWrap = panel.querySelector('.progress-wrap');
  const progressFill = panel.querySelector('.progress-fill');
  const progressPct  = panel.querySelector('.progress-pct');
  const resultBox    = panel.querySelector('.result-box');
  const btn          = panel.querySelector('.btn-process');

  btn.disabled = true;
  if (resultBox) resultBox.classList.remove('visible');
  if (progressWrap) progressWrap.classList.add('visible');
  simulateProgress(progressFill, progressPct);

  try {
    const fd  = buildFormData();
    const res = await fetch(endpoint, { method: 'POST', body: fd });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: 'Error desconocido' }));
      throw new Error(err.error || `HTTP ${res.status}`);
    }

    // Obtiene nombre del archivo desde la cabecera Content-Disposition
    const disposition = res.headers.get('Content-Disposition') || '';
    const match = disposition.match(/filename\*?=(?:UTF-8'')?["']?([^"';\n]+)/i);
    const filename = match ? decodeURIComponent(match[1]) : 'resultado';

    const blob = await res.blob();
    if (panel._resultUrl) URL.revokeObjectURL(panel._resultUrl);  // libera el resultado anterior
    const url  = URL.createObjectURL(blob);
    panel._resultUrl = url;

    // Actualiza el resultado en pantalla
    const resultName = panel.querySelector('.result-name');
    const resultSize = panel.querySelector('.result-size');
    const dlBtn      = panel.querySelector('.btn-download');
    if (resultName) resultName.textContent = filename;
    if (resultSize) resultSize.textContent = `${formatSize(blob.size)}, se descargó automáticamente`;
    if (dlBtn) {
      dlBtn.href     = url;
      dlBtn.download = filename;
    }

    // Descarga automática
    const a = document.createElement('a');
    a.href     = url;
    a.download = filename;
    a.click();

    stopProgress(progressFill, progressPct);
    if (progressWrap) progressWrap.classList.remove('visible');
    if (resultBox)    resultBox.classList.add('visible');
    showToast(`Listo: ${filename}`);

  } catch (err) {
    stopProgress(progressFill, progressPct);
    if (progressWrap) progressWrap.classList.remove('visible');
    showToast(`Error: ${err.message}`);
  } finally {
    btn.disabled = false;
  }
}

// ── Animación de progreso (simulada durante la espera) ─────────────
let _progressInterval = null;

function simulateProgress(fill, pct) {
  let v = 0;
  clearInterval(_progressInterval);
  _progressInterval = setInterval(() => {
    v += Math.random() * 6 + 2;
    if (v > 90) v = 90; // Se detiene en 90% hasta que llega la respuesta real
    if (fill) fill.style.width = v + '%';
    if (pct)  pct.textContent  = Math.floor(v) + '%';
  }, 200);
}

function stopProgress(fill, pct) {
  clearInterval(_progressInterval);
  if (fill) fill.style.width = '100%';
  if (pct)  pct.textContent  = '100%';
}

// ── UNIÓN ─────────────────────────────────────────────────────────
document.querySelector('#panel-union .btn-process')?.addEventListener('click', () => {
  const panel  = document.getElementById('panel-union');
  const items  = panel.querySelectorAll('.file-item');
  if (items.length < 2) { showToast('Sube al menos 2 archivos PDF'); return; }

  const comprimir = document.getElementById('union-comprimir')?.checked || false;
  const nivel     = panel.querySelector('input[name="union-nivel"]:checked')?.value || 'media';

  procesarConFetch(panel, '/api/union', () => {
    const fd = new FormData();
    items.forEach(item => fd.append('archivos', item._fileObj));
    const nombre = panel.querySelector('input[type="text"]')?.value || 'documento_unido.pdf';
    const contrasena = panel.querySelector('#union-password')?.value || '';
    fd.append('nombre_salida', nombre);
    if (contrasena) fd.append('contrasena_union', contrasena);
    fd.append('comprimir',    comprimir ? 'true' : 'false');
    fd.append('nivel',        nivel);
    return fd;
  });
});

// ── DIVISIÓN ──────────────────────────────────────────────────────
document.querySelector('#panel-division .btn-process')?.addEventListener('click', () => {
  const panel = document.getElementById('panel-division');
  const items = panel.querySelectorAll('.file-item');
  const modo  = panel.querySelector('input[name="modo-div"]:checked')?.value || 'rango';

  if (items.length === 0) { showToast('Sube un archivo PDF'); return; }

  if (modo === 'rango') {
    const inicio = document.getElementById('div-inicio')?.value;
    const fin    = document.getElementById('div-fin')?.value;
    if (!inicio || !fin) {
      showToast('Indica la página de inicio y la de fin');
      return;
    }
    if (parseInt(inicio, 10) > parseInt(fin, 10)) {
      showToast('La página de inicio no puede ser mayor que la final');
      return;
    }
    procesarConFetch(panel, '/api/division', () => {
      const fd = new FormData();
      fd.append('archivo', items[0]._fileObj);
      fd.append('modo',    'rango');
      fd.append('inicio', inicio);
      fd.append('fin', fin);
      return fd;
    });
  } else if (modo === 'cada') {
    const porArchivo = Number(document.getElementById('div-paginas-por-archivo')?.value);
    const total = window._totalPaginasDivision;
    if (total) {
      const { error } = gruposPorBloques(total, porArchivo);
      if (error) { showToast(error); return; }
    }
    procesarConFetch(panel, '/api/division', () => {
      const fd = new FormData();
      fd.append('archivo', items[0]._fileObj);
      fd.append('modo',    'cada');
      fd.append('paginas_por_archivo', String(porArchivo));
      return fd;
    });
  } else if (modo === 'personalizado') {
    const grupos = document.getElementById('div-grupos')?.value || '';
    const total = window._totalPaginasDivision;
    if (total) {
      const { error } = analizarGrupos(grupos, total);
      if (error) { showToast(error); return; }
    }
    procesarConFetch(panel, '/api/division', () => {
      const fd = new FormData();
      fd.append('archivo', items[0]._fileObj);
      fd.append('modo',    'personalizado');
      fd.append('grupos',  grupos);
      return fd;
    });
  } else {
    procesarConFetch(panel, '/api/division', () => {
      const fd = new FormData();
      fd.append('archivo', items[0]._fileObj);
      fd.append('modo',    modo);
      return fd;
    });
  }
});

// ── CONVERSIÓN ────────────────────────────────────────────────────
document.querySelectorAll('input[name="conv-dir"]').forEach(radio => {
  radio.addEventListener('change', (e) => {
    const tipo = e.target.value;
    const input = document.getElementById('conversion-file-input');
    const sub = document.getElementById('conversion-upload-sub');
    const zone = document.getElementById('conversion-upload-zone');
    
    // Limpiar archivos al cambiar de tipo
    const fileList = zone?.parentElement?.querySelector('.file-list');
    if (fileList) fileList.innerHTML = '';
    
    if (input) {
      if (tipo === 'imagen_a_pdf') {
        input.multiple = true;
        input.accept = '.jpg,.jpeg,.png,.bmp,.tiff,.tif,.webp';
        if (sub) sub.textContent = 'Una o varias imágenes JPG, PNG, BMP, TIFF o WEBP';
      } else if (tipo === 'pdf_a_jpg') {
        input.multiple = false;
        input.accept = '.pdf';
        if (sub) sub.textContent = 'Un PDF';
      } else {
        input.multiple = false;
        input.accept = '.pdf,.xlsx,.docx';
        if (sub) sub.textContent = 'PDF, Excel (.xlsx) o Word (.docx)';
      }
    }
  });
});

document.querySelector('#panel-conversion .btn-process')?.addEventListener('click', () => {
  const panel     = document.getElementById('panel-conversion');
  const items     = panel.querySelectorAll('.file-item');
  const direccion = panel.querySelector('input[name="conv-dir"]:checked')?.value;
  if (items.length === 0) { showToast('Sube un archivo'); return; }
  if (!direccion)         { showToast('Selecciona la dirección de conversión'); return; }
  procesarConFetch(panel, '/api/conversion', () => {
    const fd = new FormData();
    if (direccion === 'imagen_a_pdf') {
      items.forEach(item => fd.append('archivos', item._fileObj));
    } else {
      fd.append('archivo', items[0]._fileObj);
    }
    fd.append('direccion', direccion);
    return fd;
  });
});

// ── COMPRESIÓN ────────────────────────────────────────────────────
document.querySelector('#panel-compresion .btn-process')?.addEventListener('click', () => {
  const panel = document.getElementById('panel-compresion');
  const items = panel.querySelectorAll('.file-item');
  const nivel = panel.querySelector('input[name="comp-nivel"]:checked')?.value || 'media';
  if (items.length === 0) { showToast('Sube un archivo PDF'); return; }
  procesarConFetch(panel, '/api/compresion', () => {
    const fd = new FormData();
    fd.append('archivo', items[0]._fileObj);
    fd.append('nivel',   nivel);
    return fd;
  });
});

// ── CIFRADO ───────────────────────────────────────────────────────
document.querySelector('#panel-cifrado .btn-process')?.addEventListener('click', () => {
  const panel      = document.getElementById('panel-cifrado');
  const items      = panel.querySelectorAll('.file-item');
  const contrasena = document.getElementById('pass1')?.value || '';
  const confirmar  = document.getElementById('pass2')?.value || '';
  if (items.length === 0)       { showToast('Sube un archivo PDF'); return; }
  if (!contrasena)              { showToast('Ingresa una contraseña'); return; }
  if (contrasena !== confirmar) { showToast('Las contraseñas no coinciden'); return; }
  procesarConFetch(panel, '/api/cifrado', () => {
    const fd = new FormData();
    fd.append('archivo',    items[0]._fileObj);
    fd.append('contrasena', contrasena);
    fd.append('confirmar',  confirmar);
    return fd;
  });
});

// ── Utilidades ────────────────────────────────────────────────────
function formatSize(bytes) {
  if (bytes < 1024)           return bytes + ' B';
  if (bytes < 1024 * 1024)    return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

let _toastTimer = null;

function showToast(msg) {
  const toast = document.getElementById('toast');
  toast.textContent = msg;
  toast.classList.toggle('error', /^Error/.test(msg));
  toast.classList.add('show');
  // Un aviso nuevo reinicia el tiempo; los errores se leen con más calma
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => toast.classList.remove('show'), /^Error/.test(msg) ? 6000 : 3500);
}
