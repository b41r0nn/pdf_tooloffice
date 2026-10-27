// PDF ToolOffice — main.js (conectado al back Flask)

const MAX_MB    = 50;
const MAX_BYTES = MAX_MB * 1024 * 1024;

// ── Tab navigation ────────────────────────────────────────────────
document.querySelectorAll('.nav-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById('panel-' + tab.dataset.panel).classList.add('active');
  });
});

// Mostrar/ocultar nivel de compresión en unión
document.getElementById('union-comprimir')?.addEventListener('change', function() {
  const wrap = document.getElementById('union-nivel-wrap');
  if (wrap) wrap.style.display = this.checked ? 'block' : 'none';
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
  Array.from(files).forEach(file => {
    if (file.size > MAX_BYTES) { showToast(`"${file.name}" supera el límite de ${MAX_MB} MB`); return; }
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
  item.innerHTML = `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="cursor:grab;opacity:0.4">
      <line x1="8" y1="6" x2="16" y2="6"/><line x1="8" y1="12" x2="16" y2="12"/><line x1="8" y1="18" x2="16" y2="18"/>
    </svg>
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
      <polyline points="14 2 14 8 20 8"/>
    </svg>
    <span class="file-name">${file.name}</span>
    <span class="file-size">${formatSize(file.size)}</span>
    <button class="file-remove" title="Quitar">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
        <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
      </svg>
    </button>`;
  item.querySelector('.file-remove').addEventListener('click', () => item.remove());

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
  const input = document.getElementById(inputId);
  input.type  = input.type === 'password' ? 'text' : 'password';
  btn.style.color = input.type === 'text' ? 'var(--blue-main)' : '#8E9AB5';
}

function updatePreview(zone, file) {
  const card       = zone.closest('.card');
  const previewBox = card.querySelector('.preview-box');
  if (!previewBox) return;
  const nameEl  = previewBox.querySelector('.preview-name');
  const pagesEl = previewBox.querySelector('.preview-pages');
  if (nameEl)  nameEl.textContent  = file.name;
  if (pagesEl) pagesEl.textContent = 'Detectando páginas…';
  previewBox.style.display = 'flex';

  if (file.name.toLowerCase().endsWith('.pdf')) {
    const fd = new FormData();
    fd.append('archivo', file);
    fetch('/api/paginas', { method: 'POST', body: fd })
      .then(r => r.json())
      .then(d => { if (pagesEl) pagesEl.textContent = d.paginas ? `${d.paginas} páginas` : 'N/D'; })
      .catch(() => { if (pagesEl) pagesEl.textContent = 'N/D'; });
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
    const url  = URL.createObjectURL(blob);

    // Actualiza el resultado en pantalla
    const resultName = panel.querySelector('.result-name');
    const resultSize = panel.querySelector('.result-size');
    const dlBtn      = panel.querySelector('.btn-download');
    if (resultName) resultName.textContent = filename;
    if (resultSize) resultSize.textContent = formatSize(blob.size);
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
    showToast('Proceso completado ✓');

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
    const inicio = panel.querySelector('input[placeholder="1"]')?.value || 1;
    const fin    = panel.querySelector('input[placeholder="5"]')?.value || 1;
    if (parseInt(inicio) > parseInt(fin)) {
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
        if (sub) sub.textContent = 'Múltiples imágenes (JPG, PNG, WEBP, etc)';
      } else if (tipo === 'pdf_a_jpg') {
        input.multiple = false;
        input.accept = '.pdf';
        if (sub) sub.textContent = 'Solo archivos PDF';
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

function showToast(msg) {
  const toast = document.getElementById('toast');
  toast.textContent = msg;
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), 3500);
}
