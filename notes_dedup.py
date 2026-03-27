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
"""

import argparse
import sys
from pathlib import Path

from backend.scanner import find_duplicates, build_payload
from backend.server import serve


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

    serve(payload, root, args.port)


if __name__ == "__main__":
    main()
