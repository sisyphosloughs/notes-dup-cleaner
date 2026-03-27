import hashlib
import math
import multiprocessing as mp
import random
from difflib import SequenceMatcher
from pathlib import Path

TEXT_EXTENSIONS  = {".md", ".txt", ".markdown", ".rst", ".org"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp"}
SKIP_DIRS        = {".git", ".obsidian", "node_modules", "__pycache__", ".trash"}
MAX_COMPARE_CHARS = 10_000


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

    def _size_bucket_pairs(cands, ext_set):
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
