#!/usr/bin/env python3
"""
notes_dedup.py  Duplikat-Finder fuer Obsidian / VS Code Notizen
================================================================
Verwendung:
    python notes_dedup.py /pfad/zu/deinen/notizen
    python notes_dedup.py /pfad/zu/deinen/notizen --threshold 80
    python notes_dedup.py /pfad/zu/deinen/notizen --threshold 80 --port 8765

Optionen:
    --threshold   Aehnlichkeits-Schwellenwert in % (Standard: 85)
    --port        Lokaler Port fuer den Browser (Standard: 8742)
    --no-images   Bilder von der Aehnlichkeits-Analyse ausschliessen

Optimierungen:
    * Parallelisierung via multiprocessing.Pool (alle CPU-Kerne)
    * Groessen-Vorfilter eliminiert unmoeglich-aehnliche Paare sofort

Neu:
    * Datei-Vorschau per Auge-Icon
    * Side-by-Side Diff (genau 2 Dateien auswaehlen -> "Vergleichen")
"""

import argparse
import hashlib
import http.server
import itertools
import json
import math
import multiprocessing as mp
import random
import shutil
import sys
import threading
import urllib.parse
import webbrowser
from difflib import SequenceMatcher
from pathlib import Path

# ── Konfiguration ──────────────────────────────────────────────────────────────
TEXT_EXTENSIONS  = {".md", ".txt", ".markdown", ".rst", ".org"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp"}
SKIP_DIRS        = {".git", ".obsidian", "node_modules", "__pycache__", ".trash"}
MAX_COMPARE_CHARS = 10_000  # Textvergleich auf erste 10k Zeichen begrenzen

# ── Hilfs-Funktionen ───────────────────────────────────────────────────────────

def file_hash(path: Path, chunk: int = 65536) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while data := f.read(chunk):
            h.update(data)
    return h.hexdigest()


def _size_ratio(a: Path, b: Path) -> float:
    try:
        sa, sb = a.stat().st_size, b.stat().st_size
        if sa == 0 and sb == 0:
            return 1.0
        if sa == 0 or sb == 0:
            return 0.0
        return min(sa, sb) / max(sa, sb)
    except Exception:
        return 1.0


def compare_pair(args: tuple):
    """
    Laeuft in Worker-Prozessen - muss auf Modulebene stehen (pickle-bar).
    args = (path_a_str, path_b_str, threshold, size_ratio_min)
    """
    pa_str, pb_str, threshold, size_ratio_min = args
    a, b = Path(pa_str), Path(pb_str)
    if _size_ratio(a, b) < size_ratio_min:
        return None
    try:
        ta = a.read_text(encoding="utf-8", errors="ignore")[:MAX_COMPARE_CHARS]
        tb = b.read_text(encoding="utf-8", errors="ignore")[:MAX_COMPARE_CHARS]
        sm = SequenceMatcher(None, ta, tb)
        if sm.quick_ratio() * 100 < threshold:
            return None
        sim = sm.ratio() * 100
    except Exception:
        return None
    return (pa_str, pb_str, round(sim, 1)) if sim >= threshold else None


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def collect_files(root: Path) -> list:
    files = []
    for p in root.rglob("*"):
        if p.is_file() and not any(d in p.parts for d in SKIP_DIRS):
            files.append(p)
    return files

# ── Analyse ────────────────────────────────────────────────────────────────────

def find_duplicates(root: Path, threshold: float, include_images: bool):
    files = collect_files(root)
    print(f"  {len(files)} Dateien gefunden ...", flush=True)

    workers = max(1, mp.cpu_count() - 1)

    hash_map: dict = {}
    with mp.Pool(processes=workers) as pool:
        for h, p in zip(pool.map(file_hash, files), files):
            hash_map.setdefault(h, []).append(p)
    exact_groups = [v for v in hash_map.values() if len(v) > 1]
    exact_paths  = {p for g in exact_groups for p in g}

    text_files  = [p for p in files
                   if p.suffix.lower() in TEXT_EXTENSIONS and p not in exact_paths]
    image_files = [p for p in files
                   if include_images and p.suffix.lower() in IMAGE_EXTENSIONS
                   and p not in exact_paths]
    candidates  = text_files + image_files
    n           = len(candidates)
    total_pairs = n * (n - 1) // 2
    print(f"  {n} Kandidaten -> {total_pairs:,} Paare", flush=True)

    size_ratio_min = max(0.0, min(0.95, 2 * threshold / 100 - 1))

    text_ext  = TEXT_EXTENSIONS
    image_ext = IMAGE_EXTENSIONS

    # Groessen-Buckets: Nur Dateien mit kompatiblem Groessenverhaeltnis paaren
    def _size_bucket_pairs(cands, ext_set):
        """Paare nur aus Dateien bilden, deren Groesse kompatibel ist."""
        sized = []
        for p in cands:
            if p.suffix.lower() in ext_set:
                try:
                    sized.append((p.stat().st_size, p))
                except OSError:
                    continue
        sized.sort(key=lambda x: x[0])
        pairs = []
        for i, (sa, a) in enumerate(sized):
            for j in range(i + 1, len(sized)):
                sb, b = sized[j]
                if sa == 0 and sb == 0:
                    pairs.append((str(a), str(b), threshold, size_ratio_min))
                    continue
                if sa == 0 or sb == 0:
                    break
                if sa / sb < size_ratio_min:
                    break
                pairs.append((str(a), str(b), threshold, size_ratio_min))
        return pairs

    pair_args = _size_bucket_pairs(candidates, text_ext) + \
                _size_bucket_pairs(candidates, image_ext)
    skipped = total_pairs - len(pair_args)
    if skipped > 0:
        print(f"  {skipped:,} Paare durch Groessen-Vorfilter uebersprungen", flush=True)
    # Mischen damit langsame Paare (grosse Dateien) gleichmaessig verteilt werden
    random.shuffle(pair_args)
    chunk_size = max(1, min(50, math.ceil(max(1, len(pair_args)) / (workers * 8))))
    print(f"  Starte {workers} Worker-Prozesse ...", flush=True)

    similar_pairs = []
    done         = 0
    report_every = max(1, len(pair_args) // 20) if pair_args else 1

    with mp.Pool(processes=workers) as pool:
        for result in pool.imap_unordered(compare_pair, pair_args,
                                          chunksize=chunk_size):
            done += 1
            if result is not None:
                pa, pb, sim = result
                similar_pairs.append((Path(pa), Path(pb), sim))
            if done % report_every == 0:
                pct = done * 100 // max(1, len(pair_args))
                print(f"  ... {pct:3d}%  ({done:,}/{len(pair_args):,}, "
                      f"{len(similar_pairs)} Treffer)", end="\r", flush=True)

    print(f"\n  Fertig: {len(exact_groups)} exakte Gruppen, "
          f"{len(similar_pairs)} aehnliche Paare.        ", flush=True)
    return exact_groups, similar_pairs

# ── Payload ────────────────────────────────────────────────────────────────────

def build_payload(root: Path, exact_groups, similar_pairs) -> dict:
    def file_info(p: Path) -> dict:
        try:
            st = p.stat()
            return {"path": str(p), "rel": str(p.relative_to(root)),
                    "size": human_size(st.st_size), "mtime": st.st_mtime}
        except Exception:
            return {"path": str(p), "rel": str(p), "size": "?", "mtime": 0}

    return {
        "root":    str(root),
        "exact":   [{"files": [file_info(p) for p in g]} for g in exact_groups],
        "similar": [{"a": file_info(a), "b": file_info(b), "similarity": s}
                    for a, b, s in similar_pairs],
    }

# ── HTML ───────────────────────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<title>Notes Dedup</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0f1117;--surface:#1a1d27;--surface2:#21253a;--border:#2a2d3a;
  --accent:#6c8fff;--danger:#ff6b6b;--ok:#6bffb0;
  --text:#d4d8f0;--muted:#6b7098;
  --add-bg:#0d2a1a;--add-fg:#6bffb0;
  --del-bg:#2a0d0d;--del-fg:#ff8080;
  --font:'JetBrains Mono','Fira Code',monospace;
}
body{background:var(--bg);color:var(--text);font-family:var(--font);
     font-size:13px;line-height:1.6;overflow-x:hidden}

/* Header */
header{padding:15px 28px;border-bottom:1px solid var(--border);display:flex;
       align-items:center;gap:14px;position:sticky;top:0;
       background:var(--bg);z-index:50}
header h1{font-size:16px;color:var(--accent);letter-spacing:.04em}
#root-label{margin-left:auto;color:var(--muted);font-size:11px;
            overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:55%}

/* Tabs */
.tabs{display:flex;gap:2px;padding:13px 28px 0;border-bottom:1px solid var(--border)}
.tab{padding:7px 18px;border-radius:6px 6px 0 0;cursor:pointer;
     border:1px solid transparent;border-bottom:none;color:var(--muted);
     user-select:none}
.tab.active{border-color:var(--border);background:var(--surface);color:var(--text)}
.badge{display:inline-block;padding:1px 7px;border-radius:99px;
       font-size:11px;margin-left:5px;background:var(--border)}
.tab.has-items .badge{background:var(--danger);color:#000}

/* Sections */
section{display:none;padding:20px 28px}
section.active{display:block}

/* Cards */
.card{background:var(--surface);border:1px solid var(--border);
      border-radius:8px;margin-bottom:10px;overflow:hidden}
.card-header{padding:10px 14px;display:flex;align-items:center;gap:10px;
             border-bottom:1px solid var(--border);background:rgba(255,255,255,.02)}
.group-label{font-size:11px;color:var(--muted);padding:7px 14px;
             background:rgba(255,255,255,.01)}
.badge-sim{padding:2px 9px;border-radius:99px;font-size:11px;font-weight:700}
.sim-bar{height:3px;background:var(--border);border-radius:2px;width:110px;flex-shrink:0}
.sim-fill{height:100%;border-radius:2px}

/* File rows */
.file-row{padding:8px 14px;display:flex;align-items:center;gap:10px;
          border-bottom:1px solid var(--border)}
.file-row:last-child{border-bottom:none}
.file-row input[type=checkbox]{accent-color:var(--danger);width:14px;height:14px;
                                flex-shrink:0;cursor:pointer}
.file-path{flex:1;word-break:break-all}
.file-meta{color:var(--muted);font-size:11px;white-space:nowrap}
.btn-eye{background:none;border:1px solid var(--border);color:var(--muted);
         padding:3px 8px;border-radius:5px;cursor:pointer;font-size:12px;
         flex-shrink:0;font-family:var(--font)}
.btn-eye:hover{border-color:var(--accent);color:var(--accent)}

/* Toolbar */
.toolbar{position:sticky;bottom:0;background:var(--bg);
         border-top:1px solid var(--border);padding:11px 28px;
         display:flex;align-items:center;gap:10px;flex-wrap:wrap}
button{padding:7px 17px;border-radius:6px;border:none;cursor:pointer;
       font-family:var(--font);font-size:13px;font-weight:600}
.btn-accent{background:var(--accent);color:#000}
.btn-danger{background:var(--danger);color:#000}
.btn-secondary{background:var(--border);color:var(--text)}
button:disabled{opacity:.33;cursor:not-allowed}
#status{color:var(--muted);font-size:12px;margin-left:auto}
.all-sel{display:flex;gap:8px;font-size:12px;color:var(--muted)}
.all-sel a{color:var(--accent);cursor:pointer;text-decoration:none}
.empty{padding:36px;text-align:center;color:var(--muted)}

/* Move row */
.move-row{padding:6px 14px 8px 38px;display:flex;align-items:center;gap:8px;
          border-bottom:1px solid var(--border);background:rgba(108,143,255,.04)}
.move-row select{background:var(--surface2);color:var(--text);border:1px solid var(--border);
                  border-radius:5px;padding:4px 8px;font-family:var(--font);font-size:12px;
                  flex:1;max-width:420px}
.btn-move{background:var(--accent);color:#000;padding:4px 12px;border-radius:5px;
          border:none;cursor:pointer;font-family:var(--font);font-size:12px;font-weight:600}
.btn-move:disabled{opacity:.33;cursor:not-allowed}
.move-ok{color:var(--ok);font-size:11px}
.move-err{color:var(--danger);font-size:11px}

/* Overlays */
.overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.78);
         z-index:200;align-items:flex-start;justify-content:center;
         padding:28px 12px;overflow-y:auto}
.overlay.show{display:flex}
.modal{background:var(--surface);border:1px solid var(--border);
       border-radius:10px;width:100%;display:flex;flex-direction:column;
       max-height:calc(100vh - 56px);overflow:hidden}
.modal-hdr{padding:13px 18px;border-bottom:1px solid var(--border);
           display:flex;align-items:center;gap:12px;flex-shrink:0}
.modal-hdr h2{font-size:13px;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.btn-x{background:none;border:none;color:var(--muted);font-size:18px;
       cursor:pointer;padding:0 4px;line-height:1;font-family:var(--font)}
.btn-x:hover{color:var(--text)}
.modal-body{overflow:auto;flex:1}

/* Preview */
#prev-modal .modal{max-width:780px}
.preview-pre{padding:16px 20px;white-space:pre-wrap;word-break:break-all;
             font-size:12px;line-height:1.75;color:var(--text)}

/* Diff */
#diff-modal .modal{max-width:1280px}
.diff-grid{display:grid;grid-template-columns:1fr 1fr;height:100%;min-height:0}
.diff-pane{overflow:auto;border-right:1px solid var(--border)}
.diff-pane:last-child{border-right:none}
.diff-pane-hdr{padding:7px 12px;font-size:11px;color:var(--muted);
               border-bottom:1px solid var(--border);position:sticky;top:0;
               background:var(--surface2);z-index:2;
               white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
table.dt{width:100%;border-collapse:collapse;font-size:12px;line-height:1.55}
table.dt td{padding:1px 0;vertical-align:top}
td.ln{width:36px;min-width:36px;text-align:right;padding:0 7px;
      color:var(--muted);user-select:none;border-right:1px solid var(--border)}
td.lc{padding:0 9px;white-space:pre-wrap;word-break:break-all}
tr.eq  td{background:transparent}
tr.del td{background:var(--del-bg)} tr.del td.lc{color:var(--del-fg)}
tr.add td{background:var(--add-bg)} tr.add td.lc{color:var(--add-fg)}
tr.ph  td{background:rgba(255,255,255,.013)}
.diff-legend{display:flex;gap:14px;padding:7px 16px;
             border-top:1px solid var(--border);font-size:11px;
             color:var(--muted);flex-shrink:0}
.ld{display:inline-block;width:10px;height:10px;border-radius:2px;
    margin-right:4px;vertical-align:middle}

/* Confirm */
#conf-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.78);
              z-index:300;align-items:center;justify-content:center}
#conf-overlay.show{display:flex}
#conf-box{background:var(--surface);border:1px solid var(--border);
          border-radius:10px;padding:24px 28px;max-width:500px;width:90%}
#conf-box h2{margin-bottom:9px;color:var(--danger)}
#conf-list{max-height:180px;overflow-y:auto;margin:9px 0;
           border:1px solid var(--border);border-radius:6px;padding:9px}
#conf-list div{padding:2px 0;word-break:break-all;color:var(--muted);font-size:11px}
.conf-btns{display:flex;gap:9px;margin-top:13px;justify-content:flex-end}
</style>
</head>
<body>

<header>
  <h1>&#x1F4D3; Notes Dedup</h1>
  <div id="root-label"></div>
</header>

<div class="tabs">
  <div class="tab active" id="tab-exact" onclick="switchTab('exact')">
    Exakte Kopien <span class="badge" id="cnt-exact">0</span>
  </div>
  <div class="tab" id="tab-similar" onclick="switchTab('similar')">
    &#228;hnliche Dateien <span class="badge" id="cnt-similar">0</span>
  </div>
</div>

<section id="sec-exact"  class="active"></section>
<section id="sec-similar"></section>

<div class="toolbar">
  <div class="all-sel">
    <a onclick="selAll(true)">Alle</a> /
    <a onclick="selAll(false)">Keine</a>
  </div>
  <button class="btn-accent"    id="btn-diff"  onclick="openDiff()"     disabled>&#8660; Vergleichen</button>
  <button class="btn-danger"    id="btn-del"   onclick="confDel()"      disabled>&#128465; L&#246;schen</button>
  <button class="btn-secondary"               onclick="location.reload()">&#8635; Neu scannen</button>
  <div id="status">W&#228;hle Dateien aus.</div>
</div>

<!-- Vorschau -->
<div class="overlay" id="prev-modal">
  <div class="modal">
    <div class="modal-hdr">
      <h2 id="prev-title">Vorschau</h2>
      <button class="btn-x" onclick="closePrev()">&#10005;</button>
    </div>
    <div class="modal-body">
      <pre class="preview-pre" id="prev-content">Lade ...</pre>
    </div>
  </div>
</div>

<!-- Diff -->
<div class="overlay" id="diff-modal">
  <div class="modal">
    <div class="modal-hdr">
      <h2 id="diff-title">Vergleich</h2>
      <button class="btn-x" onclick="closeDiff()">&#10005;</button>
    </div>
    <div class="modal-body" style="overflow:hidden;display:flex;flex-direction:column">
      <div class="diff-grid" id="diff-grid" style="flex:1;min-height:0"></div>
    </div>
    <div class="diff-legend">
      <span><span class="ld" style="background:var(--del-bg);border:1px solid var(--del-fg)"></span>Nur in A (links)</span>
      <span><span class="ld" style="background:var(--add-bg);border:1px solid var(--add-fg)"></span>Nur in B (rechts)</span>
      <span><span class="ld" style="background:var(--surface2);border:1px solid var(--border)"></span>Identisch</span>
    </div>
  </div>
</div>

<!-- Bestaetigung -->
<div id="conf-overlay">
  <div id="conf-box">
    <h2>&#9888;&#65039; Wirklich l&#246;schen?</h2>
    <p>Diese <strong id="conf-cnt"></strong> Datei(en) werden <em>unwiderruflich</em> gel&#246;scht:</p>
    <div id="conf-list"></div>
    <div class="conf-btns">
      <button class="btn-secondary" onclick="closeConf()">Abbrechen</button>
      <button class="btn-danger"    onclick="doDelete()">Jetzt l&#246;schen</button>
    </div>
  </div>
</div>

<script>
let DATA = null;

// ── Laden ──────────────────────────────────────────────────────────────────────
async function load() {
  const r = await fetch('/data');
  DATA = await r.json();
  document.getElementById('root-label').textContent = DATA.root;
  renderExact(DATA.exact);
  renderSimilar(DATA.similar);
  await loadFolders();
}

// ── Escape ─────────────────────────────────────────────────────────────────────
function esc(s) {
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function simColor(p) {
  return p>=100?'#ff6b6b':p>=95?'#ffa06b':p>=90?'#ffd06b':'#6c8fff';
}

// ── Datei-Zeile ────────────────────────────────────────────────────────────────
function fileRow(f, id) {
  const ph = JSON.stringify(f.path), rh = JSON.stringify(f.rel);
  const mid = 'mv-' + id;
  return `<div class="file-row">
    <input type="checkbox" id="${id}" data-path="${esc(f.path)}" onchange="updateBar()">
    <label for="${id}" class="file-path">${esc(f.rel)}</label>
    <span class="file-meta">${f.size}</span>
    <button class="btn-eye" onclick="openPrev(${ph},${rh})" title="Vorschau">&#128065;</button>
  </div>
  <div class="move-row" id="${mid}">
    <select class="move-sel" data-path="${esc(f.path)}" onchange="toggleMoveBtn('${mid}')">
      <option value="">Verschieben nach\u2026</option>
    </select>
    <button class="btn-move" disabled onclick="doMove('${mid}')" title="Datei verschieben">Verschieben</button>
    <span class="move-status"></span>
  </div>`;
}

// ── Render Exakt ───────────────────────────────────────────────────────────────
function renderExact(groups) {
  document.getElementById('cnt-exact').textContent = groups.length;
  if (groups.length) document.getElementById('tab-exact').classList.add('has-items');
  const sec = document.getElementById('sec-exact');
  if (!groups.length) {
    sec.innerHTML = '<div class="empty">&#9989; Keine exakten Duplikate gefunden.</div>';
    return;
  }
  sec.innerHTML = groups.map((g,gi) =>
    `<div class="card">
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
    sec.innerHTML = '<div class="empty">&#9989; Keine &#228;hnlichen Dateien gefunden.</div>';
    return;
  }
  sec.innerHTML = pairs.map((p,i) => {
    const col = simColor(p.similarity);
    return `<div class="card">
      <div class="card-header">
        <span class="badge-sim" style="background:${col};color:#000">${p.similarity}%</span>
        <span style="flex:1;color:var(--muted);font-size:11px">&#196;hnlichkeit</span>
        <div class="sim-bar">
          <div class="sim-fill" style="width:${p.similarity}%;background:${col}"></div>
        </div>
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
  return [...document.querySelectorAll('input[type=checkbox]:checked')]
         .map(c => c.dataset.path);
}

function updateBar() {
  const paths = getChecked(), n = paths.length;
  document.getElementById('btn-del').disabled  = n === 0;
  document.getElementById('btn-diff').disabled = n !== 2;
  document.getElementById('status').textContent =
    n === 0 ? 'W\u00e4hle Dateien aus.' :
    n === 2 ? `2 ausgew\u00e4hlt \u2014 \u201eVergleichen\u201c verf\u00fcgbar` :
              `${n} Datei(en) ausgew\u00e4hlt`;
}

function selAll(v) {
  document.querySelectorAll('input[type=checkbox]').forEach(c=>c.checked=v);
  updateBar();
}

// ── Vorschau ───────────────────────────────────────────────────────────────────
async function openPrev(path, rel) {
  document.getElementById('prev-title').textContent = rel;
  document.getElementById('prev-content').textContent = 'Lade \u2026';
  document.getElementById('prev-modal').classList.add('show');
  try {
    const r = await fetch('/file?path=' + encodeURIComponent(path));
    const d = await r.json();
    document.getElementById('prev-content').textContent =
      d.content != null ? d.content : 'Fehler: ' + d.error;
  } catch(e) {
    document.getElementById('prev-content').textContent = 'Fehler: ' + e;
  }
}
function closePrev() { document.getElementById('prev-modal').classList.remove('show'); }

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

async function openDiff() {
  const paths = getChecked();
  if (paths.length !== 2) return;
  const [pa, pb] = paths;

  document.getElementById('diff-title').textContent = 'Lade \u2026';
  document.getElementById('diff-grid').innerHTML =
    '<div style="padding:24px;color:var(--muted);grid-column:1/-1">Lade Dateien \u2026</div>';
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

    const lA = ra.content.split('\n');
    const lB = rb.content.split('\n');
    const ops = diffLines(lA, lB);

    const grid = document.getElementById('diff-grid');
    grid.innerHTML = `
      <div class="diff-pane" id="dp-a">
        <div class="diff-pane-hdr" title="${esc(pa)}"><b>A</b> &mdash; ${esc(pa)}</div>
        ${buildPane(ops,'a')}
      </div>
      <div class="diff-pane" id="dp-b">
        <div class="diff-pane-hdr" title="${esc(pb)}"><b>B</b> &mdash; ${esc(pb)}</div>
        ${buildPane(ops,'b')}
      </div>`;

    // Synchrones Scrollen beider Panes
    const pA = document.getElementById('dp-a');
    const pB = document.getElementById('dp-b');
    let lock = false;
    pA.addEventListener('scroll', () => { if(!lock){lock=true;pB.scrollTop=pA.scrollTop;lock=false;} });
    pB.addEventListener('scroll', () => { if(!lock){lock=true;pA.scrollTop=pB.scrollTop;lock=false;} });

  } catch(e) {
    document.getElementById('diff-grid').innerHTML =
      `<div style="padding:24px;color:var(--danger);grid-column:1/-1">Fehler: ${esc(String(e))}</div>`;
  }
}
function closeDiff() { document.getElementById('diff-modal').classList.remove('show'); }

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
      sec.innerHTML = '<div class="empty">&#9989; Keine Eintr\u00e4ge mehr vorhanden.</div>';
    }
  }
}

async function doDelete() {
  closeConf();
  const paths = getChecked();
  document.getElementById('status').textContent = 'L\u00f6sche \u2026';

  const r = await fetch('/delete', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({paths})
  });
  const res = await r.json();

  // ── DOM-Bereinigung: Karten und Zeilen anpassen ──────────────────────────────
  // Schritt 1: Zeilen nach Eltern-Karte gruppieren
  const cardMap = new Map(); // card-Element -> [file-row Elemente]
  for (const path of paths) {
    const row  = findRow(path);
    if (!row) continue;
    const card = row.closest('.card');
    if (!card) continue;
    if (!cardMap.has(card)) cardMap.set(card, []);
    cardMap.get(card).push(row);
  }

  // Schritt 2: Pro Karte entscheiden ob Block oder nur Zeile entfernt wird
  for (const [card, rows] of cardMap) {
    const totalRows = card.querySelectorAll('.file-row').length;
    const remaining = totalRows - rows.length;
    if (remaining <= 1) {
      // Nur 0 oder 1 Datei uebrig -> ganzen Block entfernen
      card.remove();
    } else {
      // 2+ Dateien uebrig -> nur die geloeschten Zeilen entfernen
      rows.forEach(row => row.remove());
    }
  }

  // Schritt 3: Badges und Leer-Zustand aktualisieren
  updateBadges();

  const msg = res.failed > 0
    ? `\u26a0\ufe0f ${res.deleted} gel\u00f6scht, ${res.failed} Fehler`
    : `\u2705 ${res.deleted} gel\u00f6scht`;
  document.getElementById('status').textContent = msg;
  updateBar();
}

// ── Verschieben ────────────────────────────────────────────────────────────────
let FOLDERS = [];

async function loadFolders() {
  try {
    const r = await fetch('/folders');
    FOLDERS = await r.json();
  } catch(e) { FOLDERS = []; }
  // Alle move-selects befuellen
  for (const sel of document.querySelectorAll('.move-sel')) {
    const cur = sel.value;
    sel.innerHTML = '<option value="">Verschieben nach\u2026</option>'
      + FOLDERS.map(f => `<option value="${esc(f)}">${esc(f)}</option>`).join('');
    sel.value = cur;
  }
}

function toggleMoveBtn(mid) {
  const row = document.getElementById(mid);
  const sel = row.querySelector('.move-sel');
  const btn = row.querySelector('.btn-move');
  btn.disabled = !sel.value;
}

async function doMove(mid) {
  const row    = document.getElementById(mid);
  const sel    = row.querySelector('.move-sel');
  const btn    = row.querySelector('.btn-move');
  const status = row.querySelector('.move-status');
  const srcPath = sel.dataset.path;
  const destRel = sel.value;
  if (!destRel) return;

  btn.disabled = true;
  status.className = 'move-status';
  status.textContent = 'Verschiebe\u2026';

  try {
    const dest = DATA.root + '/' + destRel;
    const r = await fetch('/move', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({path: srcPath, dest: dest})
    });
    const res = await r.json();
    if (res.ok) {
      status.className = 'move-status move-ok';
      const destName = res.dest.split('/').pop();
      status.textContent = '\u2713 ' + destRel + '/' + destName;
      // file-row deaktivieren
      const fileRow = row.previousElementSibling;
      if (fileRow) {
        fileRow.style.opacity = '0.4';
        fileRow.style.pointerEvents = 'none';
        const cb = fileRow.querySelector('input[type=checkbox]');
        if (cb) { cb.checked = false; cb.disabled = true; }
      }
      sel.disabled = true;
    } else {
      status.className = 'move-status move-err';
      status.textContent = '\u2717 ' + res.error;
      btn.disabled = false;
    }
  } catch(e) {
    status.className = 'move-status move-err';
    status.textContent = '\u2717 ' + e;
    btn.disabled = false;
  }
  updateBar();
}

// Escape schliesst Modals
document.addEventListener('keydown', e => {
  if (e.key !== 'Escape') return;
  closeDiff(); closePrev(); closeConf();
});

load();
</script>
</body>
</html>
"""

# ── Webserver ──────────────────────────────────────────────────────────────────

class Handler(http.server.BaseHTTPRequestHandler):
    payload: dict = {}
    root: Path = Path(".")

    def log_message(self, fmt, *args):
        pass  # stille Logs

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/":
            self._send(200, "text/html; charset=utf-8", HTML.encode())

        elif parsed.path == "/data":
            self._send(200, "application/json",
                       json.dumps(self.payload).encode())

        elif parsed.path == "/file":
            qs   = urllib.parse.parse_qs(parsed.query)
            path = qs.get("path", [""])[0]
            try:
                content = Path(path).read_text(encoding="utf-8", errors="replace")
                body = json.dumps({"content": content, "path": path}).encode()
                self._send(200, "application/json", body)
            except Exception as e:
                body = json.dumps({"error": str(e)}).encode()
                self._send(500, "application/json", body)

        else:
            self._send(404, "text/plain", b"Not found")

    def do_POST(self):
        if self.path == "/delete":
            length  = int(self.headers.get("Content-Length", 0))
            body    = json.loads(self.rfile.read(length))
            deleted, failed = 0, 0
            for p in body.get("paths", []):
                try:
                    Path(p).unlink()
                    deleted += 1
                except Exception as e:
                    print(f"  Fehler: {p}: {e}")
                    failed += 1
            self._send(200, "application/json",
                       json.dumps({"deleted": deleted, "failed": failed}).encode())

        elif self.path == "/move":
            length = int(self.headers.get("Content-Length", 0))
            body   = json.loads(self.rfile.read(length))
            src    = Path(body.get("path", ""))
            dest_dir = Path(body.get("dest", ""))
            try:
                if not src.is_file():
                    raise FileNotFoundError(f"Quelldatei nicht gefunden: {src}")
                if not dest_dir.is_dir():
                    raise NotADirectoryError(f"Zielordner nicht gefunden: {dest_dir}")
                # Zieldatei mit Konfliktvermeidung
                stem    = src.stem
                suffix  = src.suffix
                target  = dest_dir / src.name
                counter = 1
                while target.exists():
                    target = dest_dir / f"{stem}-{counter}{suffix}"
                    counter += 1
                shutil.move(str(src), str(target))
                self._send(200, "application/json",
                           json.dumps({"ok": True,
                                       "dest": str(target)}).encode())
            except Exception as e:
                self._send(500, "application/json",
                           json.dumps({"ok": False, "error": str(e)}).encode())

        elif self.path == "/folders":
            folders = sorted(
                str(d.relative_to(self.root))
                for d in self.root.rglob("*")
                if d.is_dir() and not any(s in d.parts for s in SKIP_DIRS)
            )
            self._send(200, "application/json",
                       json.dumps(folders).encode())

        else:
            self._send(404, "text/plain", b"Not found")

    def _send(self, code: int, ctype: str, body: bytes):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Duplikat-Finder fuer Obsidian/VS Code Notizen")
    parser.add_argument("root",
        help="Pfad zum Notizen-Ordner")
    parser.add_argument("--threshold", type=float, default=85.0,
        help="Aehnlichkeits-Schwellenwert in %% (Standard: 85)")
    parser.add_argument("--port", type=int, default=8742,
        help="Lokaler Port (Standard: 8742)")
    parser.add_argument("--no-images", action="store_true",
        help="Bilder aus Aehnlichkeits-Analyse ausschliessen")
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        print(f"Fehler: '{root}' ist kein Verzeichnis.", file=sys.stderr)
        sys.exit(1)

    print(f"\nNotes Dedup")
    print(f"  Ordner   : {root}")
    print(f"  Schwelle : {args.threshold} %")
    print(f"  Port     : {args.port}\n")
    print("Analysiere ...")

    exact_groups, similar_pairs = find_duplicates(
        root, args.threshold, not args.no_images)
    payload = build_payload(root, exact_groups, similar_pairs)

    Handler.payload = payload
    Handler.root    = root

    server = http.server.HTTPServer(("127.0.0.1", args.port), Handler)
    url    = f"http://127.0.0.1:{args.port}"
    print(f"\nBrowser oeffnet sich unter: {url}")
    print("Strg+C zum Beenden.\n")

    threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nBeendet.")


if __name__ == "__main__":
    mp.freeze_support()
    main()