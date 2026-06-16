# JazzVis Web

A small local web interface for [`JazzVis.py`](JazzVis.py), the jazz
chord-progression visualizer. A narrow sidebar of d3.js-driven controls maps
directly onto JazzVis's command-line arguments; the generated chart fills
the rest of the page.

Every control updates immediately — there's no "Generate" button. Changes
accumulate (e.g. picking a tonal center, then turning on transpose, then
switching to chord names all apply together), and a **Reset** button
restores every control to its default. Loading a different lead sheet also
resets every control.

| Control                         | JazzVis.py argument |
| -------------------------------- | -------------------- |
| Circle-of-fifths **Tonal Center** wheel | `K` (e.g. `Bb`) — **Reset to Auto** omits it so JazzVis estimates the key; the wheel always highlights the key actually used |
| **Display** segmented control    | `chords` flag (Roman numerals when off) |
| **Bars Per Row** entry box       | `N` (e.g. `8 8 8 8` → `8-8-8-8`, or `12 12 8 12`) |
| **Transpose** button + wheel     | `xT` (e.g. `xC`) — forces chord-name display, matching `JazzVis.py` |

## Setup

Requires Python 3.9+.

```bash
cd jazzvis_web
python3 -m venv .venv
source .venv/bin/activate        # on Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

`JazzVis.py` and `ChordProgUtils.py` are included alongside the web app —
no separate install step needed for those.

## Run

```bash
python3 app.py
```

Then open **http://127.0.0.1:5050** in your browser.

## Using it

1. **Choose a lead sheet** — type into the search box (or press
   **Ctrl+F** / **⌘F** anywhere on the page to jump to it). Matching letters
   anywhere in a filename are highlighted, so `vrmt` can find "Moonlight in
   Vermont." Click **Upload** to add your own `.ls` / `.txt` file (kept in
   `uploads/`, separate from the bundled `songs/` collection). Loading a new
   lead sheet resets every control to its default.
2. **Download Chart** — saves the chart currently on screen as a PNG.
   Nothing is written to disk on the server; each chart is generated,
   handed to the page, and discarded.
3. **Tonal Center** — click a slice of the circle-of-fifths wheel to set the
   key JazzVis analyzes the chart against. The wheel always highlights the
   key actually in effect, even when left on Auto. A major key and its
   relative natural minor share the same tonal center (e.g. C major and A
   minor). Click **Reset to Auto** to let JazzVis estimate it from the
   chords again.
4. **Display** — choose Roman-numeral analysis or actual chord names.
5. **Bars Per Row** — type space-separated values (e.g. `12 12 8 12`) and
   press **Enter** or click **⏎** to redraw.
6. **Transpose** — click the **Transpose** button, then pick a target key on
   the small wheel to redraw the whole chart in that key. This locks the
   display to chord names while active; click **Transpose** again to turn it
   off.
7. **Reset** — restores the tonal center to Auto, turns transpose off,
   switches display back to Roman numerals, and resets the layout to
   `8 8 8 8`.

Two collapsible panels below the chart — **How to Use These Controls** and
**How to Read the Chart** — repeat this guidance and explain the chart's
colors, shapes, and glyphs (including the lighter central stripe used for
minor cadences). A third, **Song File Format**, documents the `.ls`/`.txt`
format using `Wave.txt` as an example.

## How it works

`app.py` is a thin Flask wrapper: each control change runs

```
python3 JazzVis.py <song path> [N] [K] [xT] [chords]
```

as a subprocess inside a temporary directory. The resulting PNG is read into
memory, returned to the page as a base64 data URL (along with the tonal
center JazzVis used), and the temporary directory is deleted — nothing
persists on disk. The **Download Chart** button hands that same data URL to
the browser as a file download.

JazzVis.py bundles its own copies of the DejaVu fonts in `fonts/` (resolved
relative to the script itself, regardless of the working directory), so the
♭/♯ symbols and chart text render correctly and stay crisp even if your
system doesn't have those fonts installed. The whole chart is also rendered
at 1.5× its original size (see `SCALE` near the top of `JazzVis.py`) so it
stays sharp when stretched to fill the page.

## Project layout

```
jazzvis_web/
├── app.py                # Flask backend
├── JazzVis.py             # visualizer (unchanged CLI behaviour)
├── ChordProgUtils.py      # chord-analysis utilities used by JazzVis.py
├── requirements.txt
├── fonts/                 # bundled DejaVu fonts used by JazzVis.py
├── songs/                 # bundled .ls / .txt chord charts (Wave.txt included)
├── uploads/               # user-uploaded lead sheets (created at runtime)
├── templates/
│   └── index.html
└── static/
    ├── style.css
    └── app.js             # d3.js controls
```

## Citation
Bunks, C., Weyde, T., Slingsby, A. & Wood, J. (2022). Visualization ofTonal Harmony for Jazz Lead Sheets. In: EuroVis 2022 - Short Papers. (pp. 109-113). The Eurographics Association: Eindhoven, The Netherlands. ISBN 978-3-03868-184-7 doi: 10.2312/evs20221102

## Paper
[Visualization of Tonal Harmony for Jazz Lead Sheets](https://openaccess.city.ac.uk/id/eprint/28140/1/Visualization_of_Harmonic_Structure%20Camera%20Ready%20Copy.pdf)
