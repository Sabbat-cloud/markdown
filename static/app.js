'use strict';
const $ = id => document.getElementById(id);
const source = $('source');
const csrf = document.querySelector('meta[name="csrf-token"]').content;
// API relativa para poder publicar también bajo una subruta con proxy_pass correcto.
const base = new URL('./', location.href);
let current = '', revision = null, baseline = '', busy = false, allFiles = [];
let timer, generation = 0, renderQueue = Promise.resolve(), renderedSource = null;
const dirty = () => source.value !== baseline;
const status = (message, error = false) => { $('status').textContent = message; $('status').classList.toggle('error', error); };
async function api(path, method = 'GET', data) {
  const response = await fetch(new URL('api/' + path, base), {
    method, credentials:'same-origin', headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},
    body:data === undefined ? undefined : JSON.stringify(data)
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(result.error || `Error HTTP ${response.status}. Comprueba la autenticación.`);
  return result;
}
async function action(fn) {
  if (busy) return;
  busy = true;
  const controls = [...document.querySelectorAll('button,input,textarea,select')];
  controls.forEach(el => el.disabled = true);
  try { await fn(); } catch (error) { status(error.message, true); }
  finally { controls.forEach(el => el.disabled = false); busy = false; update(); }
}
function update() {
  $('current').textContent = current || 'Documento nuevo';
  $('saved').textContent = dirty() ? '● Cambios sin guardar' : (current ? 'Guardado' : 'Sin guardar');
  document.title = `${dirty() ? '* ' : ''}${current || 'Nuevo'} · Sabbat Markdown`;
  const words = source.value.trim().match(/\S+/g) || [];
  $('stats').textContent = `${words.length} palabras · ${source.value.length} caracteres · ${source.value.split('\n').length} líneas`;
}
function draftSave() {
  try { sessionStorage.setItem('sabbat-md-draft', JSON.stringify({current, revision, baseline, content:source.value})); }
  catch { status('No se pudo guardar el borrador en esta pestaña. Descarga una copia.', true); }
}
function changed() { update(); draftSave(); schedule(); }
function mayLeave() { return !dirty() || confirm('Hay cambios sin guardar. ¿Quieres descartarlos para continuar?'); }
function schedule() { clearTimeout(timer); const ticket = ++generation; timer = setTimeout(() => enqueueRender(ticket), 450); }
function enqueueRender(ticket = ++generation) {
  const value = source.value;
  renderQueue = renderQueue.catch(() => {}).then(async () => {
    if (ticket !== generation) return;
    $('render-state').textContent = '· actualizando';
    try {
      const result = await api('render', 'POST', {content:value});
      if (ticket !== generation) return;
      const preview = $('preview');
      // HTML saneado en el servidor; nunca insertar nombres ni Markdown directamente.
      preview.innerHTML = result.html;
      preview.querySelectorAll('input').forEach(el => el.disabled = true);
      preview.querySelectorAll('a').forEach(el => { el.rel = 'noopener noreferrer'; });
      let missing = [];
      for (const el of preview.querySelectorAll('.math-tex')) {
        if (!window.katex) { missing.push('KaTeX'); continue; }
        window.katex.render(el.textContent, el, {displayMode:el.tagName === 'DIV', throwOnError:false, trust:false, strict:'warn', maxExpand:1000});
      }
      for (const code of preview.querySelectorAll('pre > code')) {
        if (code.classList.contains('language-mermaid')) {
          if (!window.mermaid) { missing.push('Mermaid'); continue; }
          const holder = document.createElement('div');
          try {
            const id = `diagram-${ticket}-${Math.random().toString(36).slice(2)}`;
            const rendered = await window.mermaid.render(id, code.textContent);
            if (ticket !== generation) return;
            holder.innerHTML = rendered.svg;
            code.parentElement.replaceWith(holder);
          } catch {
            const note = document.createElement('p'); note.className = 'mermaid-error';
            note.textContent = 'Diagrama no válido: revisa la sintaxis Mermaid. Se conserva el código.';
            code.parentElement.before(note);
          }
        } else if (window.hljs) {
          window.hljs.highlightElement(code);
        }
      }
      if (ticket === generation) renderedSource = value;
      if (ticket === generation) $('render-state').textContent = missing.length ? `· sin ${[...new Set(missing)].join(', ')} (CDN no disponible)` : '';
    } catch (error) { if (ticket === generation) { $('render-state').textContent = '· vista previa desactualizada'; status(error.message, true); } }
  });
  return renderQueue;
}
function fileURL(name) { return 'files/' + encodeURIComponent(name); }
function drawFiles() {
  const query = $('filter').value.toLocaleLowerCase();
  $('files').replaceChildren();
  for (const f of allFiles.filter(f => f.filename.toLocaleLowerCase().includes(query))) {
    const button = document.createElement('button'); button.textContent = f.filename;
    button.classList.toggle('active', f.filename === current);
    const info = document.createElement('small'); info.textContent = `${(f.size/1024).toFixed(1)} KiB · ${new Date(f.modified*1000).toLocaleDateString()}`;
    button.append(info); button.onclick = () => action(() => openFile(f.filename)); $('files').append(button);
  }
}
async function refresh() { allFiles = await api('files'); drawFiles(); }
async function openFile(name) {
  if (!mayLeave()) return;
  const data = await api(fileURL(name));
  current = data.filename; revision = data.revision; source.value = data.content; baseline = data.content;
  changed(); drawFiles(); status(`Abierto · ${data.encoding}`);
}
function askName(initial = current || 'documento.md') {
  let name = prompt('Nombre del archivo (.md o .markdown):', initial);
  if (name === null) return null;
  name = name.trim();
  if (!name) return null;
  if (!/\.(md|markdown)$/i.test(name)) name += '.md';
  return name;
}
async function save(asNew = false) {
  const name = asNew || !current ? askName(asNew && current ? current.replace(/\.(md|markdown)$/i, '-copia.md') : undefined) : current;
  if (!name) return;
  const data = await api(fileURL(name), 'POST', {content:source.value, revision:asNew ? null : revision});
  current = data.filename; revision = data.revision; baseline = source.value;
  changed(); status('Documento guardado.'); await refresh();
}
function insert(before, after = '', sample = 'texto') {
  const start = source.selectionStart, end = source.selectionEnd;
  const selected = source.value.slice(start,end) || sample;
  source.setRangeText(before + selected + after,start,end,'select');
  source.focus(); changed();
}
$('save').onclick = () => action(() => save());
$('saveas').onclick = () => action(() => save(true));
$('refresh').onclick = () => action(refresh);
$('filter').oninput = drawFiles;
$('new').onclick = () => { if (busy || !mayLeave()) return; current=''; revision=null; source.value=''; baseline=''; changed(); drawFiles(); source.focus(); status('Documento nuevo.'); };
$('rename').onclick = () => action(async () => {
  if (!current) throw new Error('Guarda el documento antes de renombrarlo.');
  if (dirty()) throw new Error('Guarda los cambios antes de renombrar.');
  const name = askName(); if (!name || name === current) return;
  const data = await api(fileURL(current),'PATCH',{filename:name,revision});
  current=data.filename; revision=data.revision; draftSave(); await refresh(); status('Archivo renombrado.');
});
$('delete').onclick = () => action(async () => {
  if (!current) throw new Error('No hay ningún archivo guardado seleccionado.');
  if (dirty()) throw new Error('Guarda o descarga los cambios antes de borrar el archivo.');
  if (!confirm(`¿Enviar «${current}» a la papelera? Podrás recuperarlo desde Papelera / versiones.`)) return;
  await api(fileURL(current),'DELETE',{revision}); current=''; revision=null; baseline=''; source.value='';
  changed(); await refresh(); status('Archivo enviado a la papelera.');
});
source.addEventListener('input', changed);
window.addEventListener('beforeunload', event => { if (dirty() || busy) { event.preventDefault(); event.returnValue=''; } });
document.addEventListener('keydown', event => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') { event.preventDefault(); action(() => save()); }
  if (event.target === source && event.key === 'Tab') { event.preventDefault(); source.setRangeText('    ',source.selectionStart,source.selectionEnd,'end'); changed(); }
});
document.querySelectorAll('[data-wrap]').forEach(button => button.onclick = () => insert(button.dataset.wrap,button.dataset.wrap));
document.querySelectorAll('[data-prefix]').forEach(button => button.onclick = () => {
  const a = source.value.lastIndexOf('\n',source.selectionStart - 1) + 1;
  const b = source.selectionEnd;
  const text = source.value.slice(a,b);
  source.setRangeText(text.split('\n').map(line => button.dataset.prefix + line).join('\n'),a,b,'select');
  source.focus(); changed();
});
$('code').onclick = () => insert('\n```python\n','\n```\n','print("Hola")');
$('link').onclick = () => insert('[','](https://ejemplo.com)','enlace');
$('table').onclick = () => insert('\n','\n','| Columna 1 | Columna 2 |\n| --- | --- |\n| Dato | Dato |');
$('math').onclick = () => insert('\n$$\n','\n$$\n','E = mc^2');
$('diagram').onclick = () => insert('\n```mermaid\n','\n```\n','flowchart TD\n  A[Inicio] --> B{Decisión}\n  B -->|Sí| C[Continuar]\n  B -->|No| D[Terminar]');
$('view').onchange = () => $('panes').className = $('view').value;
$('theme').onclick = () => { document.body.classList.toggle('dark'); try {localStorage.setItem('md-theme',document.body.classList.contains('dark')?'dark':'light');}catch{} };
try { document.body.classList.toggle('dark',localStorage.getItem('md-theme') === 'dark'); } catch {}
$('find-toggle').onclick = () => { $('findbar').hidden = !$('findbar').hidden; if (!$('findbar').hidden) $('needle').focus(); };
$('find').onclick = () => {
  const needle = $('needle').value; if (!needle) return;
  let pos = source.value.indexOf(needle,source.selectionEnd);
  if (pos < 0) pos = source.value.indexOf(needle);
  if (pos < 0) { status('Texto no encontrado.'); return; }
  source.focus(); source.setSelectionRange(pos,pos+needle.length); status('Coincidencia seleccionada en el editor.');
};
$('replace').onclick = () => { const needle=$('needle').value; if (needle && source.value.slice(source.selectionStart,source.selectionEnd) === needle) { source.setRangeText($('replacement').value,source.selectionStart,source.selectionEnd,'end'); changed(); } else status('Selecciona primero una coincidencia con Siguiente.'); };
$('replace-all').onclick = () => {
  const needle=$('needle').value; if (!needle) return;
  const parts=source.value.split(needle), n=parts.length-1;
  if (n && confirm(`¿Reemplazar ${n} coincidencias?`)) { source.setRangeText(parts.join($('replacement').value),0,source.value.length,'end'); changed(); status(`${n} reemplazos.`); }
};
$('import').onchange = () => action(async () => {
  const file=$('import').files[0]; $('import').value=''; if (!file || !mayLeave()) return;
  if (file.size > 2097152) throw new Error('El límite por documento es 2 MiB.');
  if (!/\.(md|markdown)$/i.test(file.name)) throw new Error('Selecciona un archivo .md o .markdown.');
  const bytes=new Uint8Array(await file.arrayBuffer());
  let encoding='utf-8';
  if (bytes[0]===255 && bytes[1]===254) encoding='utf-16le';
  if (bytes[0]===254 && bytes[1]===255) encoding='utf-16be';
  const text=new TextDecoder(encoding,{fatal:true}).decode(bytes);
  current=''; revision=null; baseline=''; source.value=text; changed(); drawFiles(); status(`Importado «${file.name}». Pulsa Guardar para elegir nombre.`);
});
$('download').onclick = () => {
  const blob=new Blob([source.value],{type:'text/markdown;charset=utf-8'}), url=URL.createObjectURL(blob);
  const a=document.createElement('a'); a.href=url; a.download=current || 'borrador.md'; a.click(); setTimeout(() => URL.revokeObjectURL(url),1000);
};
$('print').onclick = () => action(async () => { clearTimeout(timer); await enqueueRender(); if (renderedSource !== source.value) throw new Error('No se puede imprimir una vista previa desactualizada.'); window.print(); });
$('draft').onclick = () => {
  if (busy) return;
  let data; try {data=JSON.parse(sessionStorage.getItem('sabbat-md-draft'));} catch {}
  if (!data || typeof data.content !== 'string') { status('No hay borrador disponible en esta pestaña.'); return; }
  if (!mayLeave()) return;
  current=data.current || ''; revision=data.revision || null; baseline=data.baseline || ''; source.value=data.content;
  update(); schedule(); drawFiles(); status('Borrador recuperado. Al guardar se comprobará si cambió el servidor.');
};
$('archive').onclick = () => action(async () => {
  const entries=await api('archive'); $('archive-list').replaceChildren();
  if (!entries.length) $('archive-list').textContent='No hay copias todavía.';
  entries.forEach(item => {
    const row=document.createElement('div'); row.className='archive-item';
    const label=document.createElement('span'); label.textContent=`${item.kind==='deleted'?'Papelera':'Versión'} · ${item.filename} · ${new Date(item.date).toLocaleString()} · ${(item.size/1024).toFixed(1)} KiB`;
    const button=document.createElement('button'); button.textContent='Restaurar copia';
    button.onclick=() => action(async () => {
      const name=askName(item.filename); if (!name) return;
      await api(`archive/${item.id}/restore`,'POST',{filename:name}); await refresh(); status(`Restaurado: ${name}`); $('archive-dialog').close();
    });
    row.append(label,button); $('archive-list').append(row);
  });
  $('archive-dialog').showModal();
});
$('close-archive').onclick = () => $('archive-dialog').close();
$('preview').addEventListener('click',event => {
  const a=event.target.closest('a'); if (!a) return;
  const href=a.getAttribute('href') || '';
  if (href.startsWith('#')) return;
  try {
    const url=new URL(href,base);
    if (url.origin===base.origin && /\.(md|markdown)$/i.test(url.pathname)) {
      event.preventDefault(); const name=decodeURIComponent(url.pathname.split('/').pop()); action(() => openFile(name));
    } else { a.target='_blank'; a.rel='noopener noreferrer'; }
  } catch { event.preventDefault(); }
});
if (window.mermaid) window.mermaid.initialize({startOnLoad:false,securityLevel:'strict',maxTextSize:50000,suppressErrorRendering:true});
update(); action(refresh); schedule();
