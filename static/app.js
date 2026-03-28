let DATA = null;

// ── Theme ───────────────────────────────────────────────────────────────────────
function applyTheme(theme) {
  document.body.className = theme;
  const icon = document.getElementById('theme-icon');
  if (icon) icon.textContent = theme === 'dark' ? 'light_mode' : 'dark_mode';
  localStorage.setItem('theme', theme);
}

(function initTheme() {
  const t = localStorage.getItem('theme') || 'dark';
  document.body.className = t;
  document.addEventListener('DOMContentLoaded', function() { applyTheme(t); });
})();

function toggleTheme() {
  applyTheme(document.body.classList.contains('dark') ? 'light' : 'dark');
}

// ── Loading ─────────────────────────────────────────────────────────────────────
function showLoading() {
  const el = document.getElementById('loading-overlay');
  if (el) { el.classList.remove('hidden'); }
}
function hideLoading() {
  const el = document.getElementById('loading-overlay');
  if (el) { el.classList.add('hidden'); }
}

// ── Laden ──────────────────────────────────────────────────────────────────────
async function load() {
  showLoading();
  try {
    const r = await fetch('/data');
    DATA = await r.json();
    document.getElementById('root-label').textContent = DATA.root;
    renderExact(DATA.exact);
    renderSimilar(DATA.similar);
    await loadFolders();
  } finally {
    hideLoading();
  }
}

// ── Escape ─────────────────────────────────────────────────────────────────────
function esc(s) {
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function simColor(p) {
  return p >= 100 ? 'sim-high' : p >= 95 ? 'sim-mid-high' : p >= 90 ? 'sim-mid' : 'sim-low';
}

// ── Datei-Icon nach Endung ──────────────────────────────────────────────────────
const FILE_ICON_MAP = {
  md: 'description', txt: 'article', pdf: 'picture_as_pdf',
  js: 'javascript', ts: 'code', py: 'code', sh: 'terminal',
  html: 'html', css: 'css', json: 'data_object',
  png: 'image', jpg: 'image', jpeg: 'image', gif: 'image',
  svg: 'image', webp: 'image',
  mp3: 'audio_file', wav: 'audio_file',
  mp4: 'video_file', mov: 'video_file',
  zip: 'folder_zip', tar: 'folder_zip', gz: 'folder_zip',
};
function fileIcon(path) {
  const ext = (path.split('.').pop() || '').toLowerCase();
  return FILE_ICON_MAP[ext] || 'insert_drive_file';
}

// ── Datei-Zeile ────────────────────────────────────────────────────────────────
function fileRow(f, id) {
  return `<div class="file-row">
    <div class="checkbox-wrap">
      <input type="checkbox" id="${id}" data-path="${esc(f.path)}" onchange="updateBar()">
    </div>
    <span class="material-symbols-outlined file-icon">${fileIcon(f.path)}</span>
    <label for="${id}" class="file-path">${esc(f.rel)}</label>
    <span class="file-meta">${f.size}</span>
  </div>`;
}

// ── Render Exakt ───────────────────────────────────────────────────────────────
function renderExact(groups) {
  document.getElementById('cnt-exact').textContent = groups.length;
  if (groups.length) document.getElementById('tab-exact').classList.add('has-items');
  const sec = document.getElementById('sec-exact');
  if (!groups.length) {
    sec.innerHTML = '<div class="empty"><span class="material-symbols-outlined">check_circle</span> Keine exakten Duplikate gefunden.</div>';
    return;
  }
  sec.innerHTML = groups.map((g,gi) =>
    `<div class="card" style="--card-delay:${Math.min(gi, 12) * 35}ms">
       <div class="group-label">Gruppe ${gi+1} &mdash; ${g.files.length} identische Dateien</div>
       ${g.files.map((f,fi)=>fileRow(f,`e-${gi}-${fi}`)).join('')}
     </div>`
  ).join('');
}

// ── Render Aehnlich ────────────────────────────────────────────────────────────
function renderSimilar(pairs) {
  document.getElementById('cnt-similar').textContent = pairs.length;
  if (pairs.length) document.getElementById('tab-similar').classList.add('has-items');
  const sec = document.getElementById('sec-similar');
  if (!pairs.length) {
    sec.innerHTML = '<div class="empty"><span class="material-symbols-outlined">check_circle</span> Keine &#228;hnlichen Dateien gefunden.</div>';
    return;
  }
  sec.innerHTML = pairs.map((p,i) => {
    const col = simColor(p.similarity);
    return `<div class="card" style="--card-delay:${Math.min(i, 12) * 35}ms">
      <div class="card-header">
        <span class="badge-sim ${col}">${p.similarity}%</span>
        <span class="sim-label">&#196;hnlichkeit</span>
        <div class="sim-bar">
          <div class="sim-fill ${col}" style="width:${p.similarity}%"></div>
        </div>
        <button class="btn-quick-compare" title="Direkt vergleichen"
          onclick="openDiff('${esc(p.a.path)}','${esc(p.b.path)}')">
          <span class="material-symbols-outlined">compare</span>
        </button>
      </div>
      ${fileRow(p.a,`s-${i}-a`)}
      ${fileRow(p.b,`s-${i}-b`)}
    </div>`;
  }).join('');
}

// ── Tabs ───────────────────────────────────────────────────────────────────────
function switchTab(n) {
  ['exact','similar'].forEach(k => {
    document.getElementById('tab-'+k).classList.toggle('active', k===n);
    document.getElementById('sec-'+k).classList.toggle('active', k===n);
  });
  updateBar();
}

// ── Toolbar ────────────────────────────────────────────────────────────────────
function getChecked() {
  return [...document.querySelectorAll('input[type=checkbox][data-path]:checked')]
         .map(c => c.dataset.path);
}

function updateBar() {
  const paths = getChecked(), n = paths.length;
  document.getElementById('btn-deselect').disabled = n === 0;
  document.getElementById('btn-del').disabled  = n === 0;
  document.getElementById('btn-diff').disabled = n !== 2;
}

function selAll(v) {
  document.querySelectorAll('input[type=checkbox][data-path]').forEach(c=>c.checked=v);
  updateBar();
}

// ── Hilfsfunktionen fuer DOM-Updates ──────────────────────────────────────────
function removeFileRows(paths) {
  const cardMap = new Map();
  for (const path of paths) {
    const row = findRow(path);
    if (!row) continue;
    const card = row.closest('.card');
    if (!card) continue;
    if (!cardMap.has(card)) cardMap.set(card, []);
    cardMap.get(card).push(row);
  }
  for (const [card, rows] of cardMap) {
    const totalRows = card.querySelectorAll('.file-row').length;
    const remaining = totalRows - rows.length;
    if (remaining <= 1) {
      card.remove();
    } else {
      rows.forEach(row => row.remove());
    }
  }
}

function disableFileRow(path) {
  const row = findRow(path);
  if (row) {
    row.style.opacity = '0.4';
    row.style.pointerEvents = 'none';
    const cb = row.querySelector('input[type=checkbox]');
    if (cb) { cb.checked = false; cb.disabled = true; }
  }
}

// ── Diff ───────────────────────────────────────────────────────────────────────

/**
 * LCS-basierter Zeilendiff.
 * Gibt [{type:'eq'|'del'|'ins', la?, lb?}, ...] zurueck.
 * Fuer sehr grosse Dateien: kuerzen auf MAX Zeilen.
 */
function diffLines(lA, lB) {
  const MAX = 3000;
  const a = lA.length > MAX ? lA.slice(0, MAX) : lA;
  const b = lB.length > MAX ? lB.slice(0, MAX) : lB;
  const M = a.length, N = b.length;

  // DP-Tabelle (vorwaerts)
  const dp = Array.from({length: M+1}, () => new Int32Array(N+1));
  for (let i = M-1; i >= 0; i--)
    for (let j = N-1; j >= 0; j--)
      dp[i][j] = a[i]===b[j] ? dp[i+1][j+1]+1 : Math.max(dp[i+1][j], dp[i][j+1]);

  const ops = [];
  let i=0, j=0;
  while (i<M && j<N) {
    if (a[i]===b[j])                       { ops.push({type:'eq', la:a[i], lb:b[j]}); i++;j++; }
    else if (dp[i+1][j] >= dp[i][j+1])    { ops.push({type:'del',la:a[i]});           i++;     }
    else                                   { ops.push({type:'ins',          lb:b[j]}); j++;     }
  }
  while (i<M) { ops.push({type:'del',la:a[i++]}); }
  while (j<N) { ops.push({type:'ins',lb:b[j++]}); }
  return ops;
}

/**
 * Baut eine diff-Pane-Tabelle fuer Seite 'a' oder 'b'.
 * Auf der jeweils anderen Seite werden Platzhalter-Zeilen eingefuegt,
 * damit beide Panes zeilenweise synchron bleiben.
 */
function buildPane(ops, side) {
  let rows='', ln=1;
  for (const op of ops) {
    if (op.type==='eq') {
      rows += `<tr class="eq"><td class="ln">${ln++}</td><td class="lc">${esc(side==='a'?op.la:op.lb)}</td></tr>`;
    } else if (op.type==='del') {
      if (side==='a') rows += `<tr class="del"><td class="ln">${ln++}</td><td class="lc">${esc(op.la)}</td></tr>`;
      else            rows += `<tr class="ph"><td class="ln">&nbsp;</td><td class="lc">&nbsp;</td></tr>`;
    } else { // ins
      if (side==='b') rows += `<tr class="add"><td class="ln">${ln++}</td><td class="lc">${esc(op.lb)}</td></tr>`;
      else            rows += `<tr class="ph"><td class="ln">&nbsp;</td><td class="lc">&nbsp;</td></tr>`;
    }
  }
  return `<table class="dt"><tbody>${rows}</tbody></table>`;
}

let DIFF_CONTEXT = null; // {files: [{path, rel, size}, ...]}
let EDIT_CACHE = { a: null, b: null, originalA: null, originalB: null };

function buildActionRow(path, fi) {
  const folderOpts = FOLDERS.map(fo =>
    '<option value="' + esc(fo) + '">' + esc(fo) + '</option>'
  ).join('');
  return '<div class="diff-action-row" data-side="' + fi + '">' +
    '<input type="checkbox" id="diff-del-' + fi + '" class="diff-del-cb">' +
    '<label for="diff-del-' + fi + '" class="diff-del-label">L\u00f6schen</label>' +
    '<span class="diff-path-display" title="' + esc(path) + '">' + esc(path) + '</span>' +
    '<select class="diff-folder-sel" data-side="' + fi + '" onchange="updateDiffPath(' + fi + ')">' +
      '<option value="">Ordner\u2026</option>' + folderOpts +
    '</select>' +
    '<button class="diff-move-btn" onclick="toggleDiffFolderSel(' + fi + ')" title="Verschieben nach\u2026"><span class="material-symbols-outlined">folder_open</span></button>' +
    '<button class="diff-edit-btn" onclick="toggleEdit(' + fi + ')"><span class="material-symbols-outlined">edit</span> Bearbeiten</button>' +
  '</div>';
}

function toggleDiffFolderSel(fi) {
  const row = document.querySelector('.diff-action-row[data-side="' + fi + '"]');
  const sel = row.querySelector('.diff-folder-sel');
  sel.classList.toggle('show');
  if (sel.classList.contains('show')) sel.focus();
}

function updateDiffPath(fi) {
  const row = document.querySelector('.diff-action-row[data-side="' + fi + '"]');
  const sel = row.querySelector('.diff-folder-sel');
  const disp = row.querySelector('.diff-path-display');
  const origFile = DIFF_CONTEXT.files[fi];
  if (sel.value) {
    const filename = origFile.path.split('/').pop();
    const newPath = DATA.root + '/' + sel.value + '/' + filename;
    disp.textContent = newPath;
    disp.title = newPath;
  } else {
    disp.textContent = origFile.path;
    disp.title = origFile.path;
  }
}

function renderDiff() {
  if (!DIFF_CONTEXT) return;
  const textA = EDIT_CACHE.a ?? EDIT_CACHE.originalA;
  const textB = EDIT_CACHE.b ?? EDIT_CACHE.originalB;
  const lA = textA.split('\n');
  const lB = textB.split('\n');
  const ops = diffLines(lA, lB);

  const pa = DIFF_CONTEXT.files[0].path;
  const pb = DIFF_CONTEXT.files[1].path;
  const grid = document.getElementById('diff-grid');
  grid.innerHTML =
    '<div class="diff-pane" id="dp-a">' +
      buildActionRow(pa, 0) +
      buildPane(ops,'a') +
    '</div>' +
    '<div class="diff-pane" id="dp-b">' +
      buildActionRow(pb, 1) +
      buildPane(ops,'b') +
    '</div>';

  // Synchrones Scrollen beider Panes
  const pA = document.getElementById('dp-a');
  const pB = document.getElementById('dp-b');
  let lock = false;
  pA.addEventListener('scroll', () => { if(!lock){lock=true;pB.scrollTop=pA.scrollTop;lock=false;} });
  pB.addEventListener('scroll', () => { if(!lock){lock=true;pA.scrollTop=pB.scrollTop;lock=false;} });

  updateRecompareBtn();
}

function toggleEdit(fi) {
  const side = fi === 0 ? 'a' : 'b';
  const pane = document.getElementById('dp-' + side);
  const btn = pane.querySelector('.diff-edit-btn');
  const table = pane.querySelector('table.dt');
  const ta = pane.querySelector('.diff-edit-area');

  if (ta) {
    // Textarea -> zurueck (Inhalt ist bereits im Cache)
    EDIT_CACHE[side] = ta.value;
    btn.innerHTML = '<span class="material-symbols-outlined">edit</span> Bearbeiten';
    // Einzelne Pane neu rendern: Diff mit aktuellem Cache
    const textA = EDIT_CACHE.a ?? EDIT_CACHE.originalA;
    const textB = EDIT_CACHE.b ?? EDIT_CACHE.originalB;
    const ops = diffLines(textA.split('\n'), textB.split('\n'));
    const newTable = document.createElement('div');
    newTable.innerHTML = buildPane(ops, side);
    ta.replaceWith(newTable.firstChild);
  } else if (table) {
    // Diff-Tabelle -> Textarea
    const content = EDIT_CACHE[side] ?? (side === 'a' ? EDIT_CACHE.originalA : EDIT_CACHE.originalB);
    const textarea = document.createElement('textarea');
    textarea.className = 'diff-edit-area';
    textarea.value = content;
    textarea.addEventListener('input', () => {
      EDIT_CACHE[side] = textarea.value;
      updateRecompareBtn();
    });
    table.replaceWith(textarea);
    btn.innerHTML = '<span class="material-symbols-outlined">preview</span> Vorschau';
    textarea.focus();
    updateRecompareBtn();
  }
}

function reCompare() {
  // Offene Textareas in Cache lesen
  for (const side of ['a', 'b']) {
    const ta = document.querySelector('#dp-' + side + ' .diff-edit-area');
    if (ta) EDIT_CACHE[side] = ta.value;
  }
  renderDiff();
}

function updateRecompareBtn() {
  const btn = document.getElementById('btn-recompare');
  if (btn) btn.disabled = (EDIT_CACHE.a === null && EDIT_CACHE.b === null);
}

async function openDiff(pa, pb) {
  // Wenn ohne Argumente aufgerufen (Toolbar-Button): aus Checkboxen lesen
  if (!pa || !pb) {
    const paths = getChecked();
    if (paths.length !== 2) return;
    pa = paths[0];
    pb = paths[1];
  }

  // Datei-Infos aus DATA suchen
  const fileA = findFileInfo(pa);
  const fileB = findFileInfo(pb);
  DIFF_CONTEXT = { files: [
    { path: pa, rel: fileA ? fileA.rel : pa.split('/').pop(), size: fileA ? fileA.size : '' },
    { path: pb, rel: fileB ? fileB.rel : pb.split('/').pop(), size: fileB ? fileB.size : '' }
  ]};

  document.getElementById('diff-title').textContent = 'Lade \u2026';
  document.getElementById('diff-status').textContent = '';
  document.getElementById('diff-grid').innerHTML =
    '<div class="diff-loading">Lade Dateien \u2026</div>';
  document.getElementById('diff-modal').classList.add('show');

  try {
    const [ra, rb] = await Promise.all([
      fetch('/file?path='+encodeURIComponent(pa)).then(r=>r.json()),
      fetch('/file?path='+encodeURIComponent(pb)).then(r=>r.json()),
    ]);
    if (ra.error||rb.error) throw new Error(ra.error||rb.error);

    const nameA = pa.split('/').pop();
    const nameB = pb.split('/').pop();
    document.getElementById('diff-title').textContent = nameA + '  \u21d4  ' + nameB;

    EDIT_CACHE = { a: null, b: null, originalA: ra.content, originalB: rb.content };
    renderDiff();

  } catch(e) {
    document.getElementById('diff-grid').innerHTML =
      '<div class="diff-error">Fehler: ' + esc(String(e)) + '</div>';
  }
}

function closeDiff() {
  document.getElementById('diff-modal').classList.remove('show');
  DIFF_CONTEXT = null;
  EDIT_CACHE = { a: null, b: null, originalA: null, originalB: null };
}

function findFileInfo(path) {
  if (!DATA) return null;
  for (const g of DATA.exact)
    for (const f of g.files)
      if (f.path === path) return f;
  for (const p of DATA.similar) {
    if (p.a.path === path) return p.a;
    if (p.b.path === path) return p.b;
  }
  return null;
}

// ── Aenderungen anwenden (Diff-Modal) ─────────────────────────────────────────
async function applyDiffChanges() {
  if (!DIFF_CONTEXT) return;
  const status = document.getElementById('diff-status');
  const toDelete = [];
  const toMove = [];

  DIFF_CONTEXT.files.forEach((f, fi) => {
    const row = document.querySelector('.diff-action-row[data-side="' + fi + '"]');
    const delCb = row.querySelector('.diff-del-cb');
    const moveSel = row.querySelector('.diff-folder-sel');
    if (delCb.checked) {
      toDelete.push(f.path);
    } else if (moveSel.value) {
      toMove.push({ path: f.path, dest: DATA.root + '/' + moveSel.value });
    }
  });

  const hasEdits = EDIT_CACHE.a !== null || EDIT_CACHE.b !== null;
  if (toDelete.length === 0 && toMove.length === 0 && !hasEdits) {
    status.textContent = 'Keine \u00c4nderungen ausgew\u00e4hlt.';
    return;
  }

  status.textContent = 'Wird ausgef\u00fchrt\u2026';
  const messages = [];

  // 0. Bearbeitete Dateien speichern
  for (const [side, fi] of [['a',0],['b',1]]) {
    const edited = EDIT_CACHE[side];
    if (edited === null) continue;
    const path = DIFF_CONTEXT.files[fi].path;
    // Nicht speichern wenn Datei geloescht wird
    const row = document.querySelector('.diff-action-row[data-side="' + fi + '"]');
    if (row.querySelector('.diff-del-cb').checked) continue;
    try {
      const r = await fetch('/save', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ path: path, content: edited })
      });
      const res = await r.json();
      if (res.ok) {
        messages.push('Gespeichert: ' + path.split('/').pop());
      } else {
        messages.push('Speichern fehlgeschlagen: ' + res.error);
      }
    } catch(e) {
      messages.push('Speichern fehlgeschlagen: ' + e);
    }
  }

  // 1. Loeschen
  if (toDelete.length > 0) {
    try {
      const r = await fetch('/delete', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ paths: toDelete })
      });
      const res = await r.json();
      removeFileRows(toDelete);
      messages.push(res.failed > 0
        ? res.deleted + ' gel\u00f6scht, ' + res.failed + ' Fehler'
        : res.deleted + ' gel\u00f6scht');
    } catch(e) {
      messages.push('L\u00f6schen fehlgeschlagen: ' + e);
    }
  }

  // 2. Verschieben
  for (const m of toMove) {
    try {
      const r = await fetch('/move', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ path: m.path, dest: m.dest })
      });
      const res = await r.json();
      if (res.ok) {
        disableFileRow(m.path);
        const destName = res.dest.split('/').pop();
        messages.push('\u2713 Verschoben: ' + destName);
      } else {
        messages.push('\u2717 ' + res.error);
      }
    } catch(e) {
      messages.push('\u2717 ' + e);
    }
  }

  updateBadges();
  updateBar();
  closeDiff();
}

// ── Loeschen ───────────────────────────────────────────────────────────────────
function confDel() {
  const paths = getChecked();
  if (!paths.length) return;
  document.getElementById('conf-cnt').textContent = paths.length;
  document.getElementById('conf-list').innerHTML = paths.map(p=>`<div>${esc(p)}</div>`).join('');
  document.getElementById('conf-overlay').classList.add('show');
}
function closeConf() { document.getElementById('conf-overlay').classList.remove('show'); }

/**
 * Findet die .file-row eines Pfades ohne CSS.escape (sicher fuer Sonderzeichen).
 */
function findRow(path) {
  for (const cb of document.querySelectorAll('input[type=checkbox]'))
    if (cb.dataset.path === path) return cb.closest('.file-row');
  return null;
}

/**
 * Aktualisiert Badge-Zaehler und zeigt "leer"-Meldung wenn kein Block mehr vorhanden.
 */
function updateBadges() {
  for (const key of ['exact', 'similar']) {
    const sec  = document.getElementById('sec-' + key);
    const tab  = document.getElementById('tab-' + key);
    const cnt  = document.getElementById('cnt-' + key);
    const cards = sec.querySelectorAll('.card');
    cnt.textContent = cards.length;
    tab.classList.toggle('has-items', cards.length > 0);
    if (cards.length === 0 && !sec.querySelector('.empty')) {
      sec.innerHTML = '<div class="empty"><span class="material-symbols-outlined">check_circle</span> Keine Eintr\u00e4ge mehr vorhanden.</div>';
    }
  }
}

async function doDelete() {
  closeConf();
  const paths = getChecked();

  const r = await fetch('/delete', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({paths})
  });
  const res = await r.json();

  removeFileRows(paths);
  updateBadges();

  const msg = res.failed > 0
    ? `\u26a0\ufe0f ${res.deleted} gel\u00f6scht, ${res.failed} Fehler`
    : `\u2705 ${res.deleted} gel\u00f6scht`;
  updateBar();
}

// ── Verschieben ────────────────────────────────────────────────────────────────
let FOLDERS = [];

async function loadFolders() {
  try {
    const r = await fetch('/folders');
    FOLDERS = await r.json();
  } catch(e) { FOLDERS = []; }
}

// Escape schliesst Modals
document.addEventListener('keydown', e => {
  if (e.key !== 'Escape') return;
  closeDiff(); closeConf();
});

load();
