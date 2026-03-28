# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

**Notes Dedup** is a duplicate finder and similarity analysis tool for personal notes (Obsidian, VS Code, etc.). It detects exact duplicates (SHA256) and near-duplicates (similarity above a configurable threshold), then serves an interactive web UI for comparing and managing them.

## Running the Tool

```bash
python notes_dedup.py /path/to/your/notes
python notes_dedup.py /path/to/notes --threshold 80 --port 8765 --no-images
```

Options: `--threshold` (0–100, default 85), `--port` (default 8742), `--no-images` (exclude image files).

No build step, no package manager, no test suite. All dependencies are Python standard library + Google Fonts CDN.

## Architecture

Three-layer pipeline:

1. **CLI entry point** (`notes_dedup.py`): Parses args, runs scanner, starts server, opens browser.
2. **Scanner** (`backend/scanner.py`): Finds files recursively, computes SHA256 hashes for exact duplicates (multiprocessing, `cpu_count()-1` workers), then runs `difflib.SequenceMatcher` for similarity pairs with a size-ratio pre-filter. Text content is capped at 10,000 chars (`MAX_COMPARE_CHARS`).
3. **HTTP server** (`backend/server.py`): Built-in Python HTTP server. Serves static files and a JSON API (`/data`, `/file`, `/folders`, `/delete`, `/move`, `/save`). Validates all paths against the scanned root directory.
4. **Frontend** (`static/app.js`, `static/index.html`, `static/style.css`, `static/theme/`): Vanilla JS. Fetches `/data` on load, renders exact-duplicate groups and similar pairs. The diff view uses a client-side LCS algorithm (capped at 3,000 lines per file). Inline editing writes back via `POST /save`. Material Design 3 with modular theme CSS files.

## Key Design Decisions

- **No external dependencies**: everything runs on Python stdlib + vanilla JS.
- **Two-phase similarity**: quick ratio pre-filter → full `SequenceMatcher.ratio()` to avoid O(n²) comparisons on large vaults.
- **Skipped directories**: `.git`, `.obsidian`, `node_modules`, `__pycache__`, `.trash`.
- **UI language**: German (all labels/buttons are in German).
- **Themes**: `static/theme/` contains Material Design 3 color token CSS files (dark, light, dark-hc, light-hc, dark-mc, light-mc). The git status shows some of these were removed from `src/css/` — the canonical location is now `static/theme/`.

## 1. Theme & Farben
- Nutze die MD3-Farb-Tokens aus `src/theme/light.css` und `src/theme/dark.css` (--md-sys-color-*).
- **Strikte Regel:** Verwende ausschließlich var(--md-sys-color-*) für Farben. 
- **Elevation:** Realisiere Tiefe primär über Surface-Container-Farben (z. B. --md-sys-color-surface-container-low/high) statt klassischer Schatten.
- Keine Hex-Werte, keine hardcodierten RGB-Werte.

## 2. Icons (Material Symbols)
- Verwende ausschließlich **Material Symbols** im Outlined-Stil.
- Einbindung via Google Fonts: <link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined" rel="stylesheet">
- Syntax: <span class="material-symbols-outlined">icon_name</span>
- Namen: Nur offizielle Namen von fonts.google.com/icons (Snake-Case). Keine Namen erfinden!

## 3. Spacing & Grid (8px-Regel)
- **Layout-Abstände:** Nutze ein striktes 8px-Raster für Margins und Paddings (8, 16, 24, 32, 40, 48, 64px).
- **Micro-Spacing:** 4px-Schritte sind nur für kleinste Abstände (z. B. Icon zu Text) erlaubt.
- Vermeide 12px oder andere Zwischenwerte, sofern sie nicht explizit Teil einer M3-Komponente sind.

## 4. Shapes (Rundungen)
Nutze die M3-Shape-Skala für `border-radius`:
- **None:** 0px
- **Extra Small:** 4px
- **Small:** 8px
- **Medium:** 12px (Standard für Cards)
- **Large:** 16px
- **Extra Large:** 28px (Standard für Dialoge/FABs)
- **Full:** 999px (Buttons, Chips, Search Bars)

## 5. Typografie
- Nutze die M3-Skala: Display, Headline, Title, Body, Label.
- Implementiere für jede Kategorie die Stufen Large, Medium und Small.
- Verwende für die CSS-Klassen die Benennung: `.[kategorie]-[stufe]` (z. B. .title-medium).
- Font: Noto Sans (bereits im Theme definiert).

## 6. Absolut Verboten
- Keine `box-shadow` Definitionen (nutze stattdessen M3-Elevation-Klassen oder Surface-Farben).
- Keine `border-radius` Werte, die nicht der M3-Skala (Punkt 4) entsprechen.
- Keine fremden Icon-Libraries (Font Awesome, Heroicons etc.).
- Keine eigenen CSS-Tricks für Standard-M3-Komponenten (Button, FAB, Card, Chip, Navigation Bar) – baue sie exakt nach der M3-Spec nach.

## 7. Spezifische Komponenten-Struktur (M3 Spec)
Wende für die vorhandenen Elemente folgende M3-Strukturen an:

- **Top App Bar:** Der Titel "Notes Dedup" muss eine 'Center-aligned top app bar' sein (Höhe 64px, Title-Large).
- **Tabs:** Nutze 'Primary Tabs'. Der aktive Tab erhält einen Indikator-Strich (3px) in `--md-sys-color-primary`, der an den Ecken abgerundet ist.
- **List Items:** Jede Datei-Zeile ist ein 'List Item'. 
  - Höhe: min. 56px. 
  - Padding: 16px horizontal.
  - Hintergrund: `--md-sys-color-surface-container-low`.
  - Trennung: Nutze keine harten Linien, sondern leichte Abstände (8px) zwischen den Gruppen.
- **Checkboxen:** Nutze das M3-Checkbox-Design (abgerundete Ecken, State-Layer/Ripple beim Hover).
- **Bottom Bar:** Verwandle die untere Leiste in eine 'Bottom App Bar'.
  - Höhe: 80px.
  - Icons und Text müssen vertikal zentriert sein.
  - Interaktive Elemente brauchen einen 'State Layer' (kreisförmige Aufhellung bei Hover/Touch).

## 8. Layout-Hierarchie
- Der Hauptbereich (Hintergrund) nutzt `--md-sys-color-surface`.
- Die Container der Gruppen nutzen `--md-sys-color-surface-container`.
- Text-Farben: Titel in `--md-sys-color-on-surface`, sekundäre Infos (wie "0.0 B") in `--md-sys-color-on-surface-variant`.

## 9. Strikte Kontrast- & Dark-Mode-Regeln
- **Kein "Hard-White":** Verbiete explizit `background-color: white` oder `#fff` innerhalb der App-Container.
- **Flächen-Logik:** Jedes Element, das eine Fläche darstellt (Cards, List-Items, Boxen), MUSS eine der Surface-Container-Variablen nutzen:
  - Hintergrund: `--md-sys-color-surface`
  - Listen-Elemente: `--md-sys-color-surface-container-low`
  - Hervorgehobene Elemente: `--md-sys-color-surface-container-high`
- **Text-Logik:** Text darf niemals hardcodiert sein. Nutze:
  - Haupttext: `--md-sys-color-on-surface`
  - Dezentere Infos: `--md-sys-color-on-surface-variant`
- **Lesbarkeit:** Erhöhe die Basis-Schriftgröße für `body-medium` auf 16px. Sorge für ausreichendes Padding (min. 12px oben/unten) in den Zeilen, damit die Klickflächen groß genug sind.