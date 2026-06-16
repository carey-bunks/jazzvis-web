#!/usr/bin/env python3
"""
app.py — JazzVis Web Service
=============================

A small local Flask service that wraps JazzVis.py and exposes its
command-line arguments as a web UI (see templates/index.html and
static/app.js, which provide a d3.js circle-of-fifths tonal-center picker,
a bars-per-row entry box, and a display / transpose toggle).

Run locally with:

    pip install -r requirements.txt
    python3 app.py

Then open http://127.0.0.1:5050 in a browser.

Endpoints
---------
GET  /                       -> the single-page UI
GET  /api/songs              -> JSON list of available song files
POST /api/upload             -> upload a new .ls / .txt song file
POST /api/generate           -> run JazzVis.py with the requested options

JazzVis.py is run inside a temporary directory that is deleted as soon as
its output PNG has been read, so nothing is written persistently to disk by
this service — the generated chart is returned to the page as a base64 data
URL, which the page can also offer as a download.
"""

import os
import re
import glob
import base64
import shutil
import tempfile
import subprocess

from flask import Flask, request, jsonify, render_template

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
SONGS_DIR   = os.path.join(BASE_DIR, 'songs')      # bundled lead sheets
UPLOADS_DIR = os.path.join(BASE_DIR, 'uploads')    # user-uploaded lead sheets
JAZZVIS     = os.path.join(BASE_DIR, 'JazzVis.py')

os.makedirs(SONGS_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)

app = Flask(__name__)

ALLOWED_EXT = {'.ls', '.txt'}

# The 12 major keys accepted by ChordProgUtils.chordmap / JazzVis's K and
# xT command-line arguments.
VALID_KEYS = {'C', 'F', 'Bb', 'Eb', 'Ab', 'Db', 'Gb', 'B', 'E', 'A', 'D', 'G'}

# Diagnostic flags accepted by JazzVis's d=... argument are intentionally
# not exposed in this UI (developer-only).


# ---------------------------------------------------------------------------
# Static pages
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    return render_template('index.html')


# ---------------------------------------------------------------------------
# Song library
# ---------------------------------------------------------------------------

def _find_song(name):
    """Resolve a song filename to a full path.

    User uploads (in uploads/) take precedence over same-named bundled
    lead sheets (in songs/), so an uploaded file always shadows a bundled
    one with the same name.
    """
    for directory in (UPLOADS_DIR, SONGS_DIR):
        path = os.path.join(directory, name)
        if os.path.isfile(path):
            return path
    return None


@app.route('/api/songs')
def list_songs():
    """Return the names of all song files available in songs/ and uploads/."""
    names = set()
    for directory in (SONGS_DIR, UPLOADS_DIR):
        for ext in ALLOWED_EXT:
            for f in glob.glob(os.path.join(directory, f'*{ext}')):
                names.add(os.path.basename(f))
    return jsonify(sorted(names))


@app.route('/api/upload', methods=['POST'])
def upload():
    """Accept an uploaded .ls or .txt chord-progression file.

    Uploaded files are kept in uploads/, separate from the bundled lead
    sheets in songs/, so they don't get mixed into the main collection.
    """
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({'error': 'No file was provided.'}), 400

    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ALLOWED_EXT:
        return jsonify({'error': 'Only .ls and .txt chord-chart files are supported.'}), 400

    # Sanitize the filename to something safe to use on disk / on the URL.
    safe_name = re.sub(r'[^A-Za-z0-9._-]+', '_', f.filename)
    if not safe_name:
        safe_name = 'song' + ext

    dest = os.path.join(UPLOADS_DIR, safe_name)
    f.save(dest)
    return jsonify({'filename': safe_name})


# ---------------------------------------------------------------------------
# Chart generation
# ---------------------------------------------------------------------------

@app.route('/api/generate', methods=['POST'])
def generate():
    """Run JazzVis.py with the options selected in the UI.

    Expected JSON body
    -------------------
    {
      "song":        "Wave.txt",     # required, in songs/ or uploads/
      "bpl":         "8-8-8-8-8-4",  # optional bars-per-row layout
      "key":         "Bb",           # optional tonal center (omit = auto)
      "transpose":   true/false,     # whether to transpose
      "transposeKey":"C",            # required if transpose is true
      "display":     "symbols"|"chords"
    }

    Returns the generated chart as a base64 data URL (image), plus the
    tonal center JazzVis actually used (tonalCenter) so the UI can
    highlight it on the circle-of-fifths wheel even in Auto mode.
    """
    data = request.get_json(force=True, silent=True) or {}

    song = data.get('song', '')
    song_path = _find_song(song) if song else None
    if not song_path:
        return jsonify({'error': 'Please choose a valid song file.'}), 400

    args = ['python3', JAZZVIS, song_path]

    # --- Bars per row (N) -------------------------------------------------
    bpl = (data.get('bpl') or '').strip()
    if bpl:
        if not re.fullmatch(r'\d+(-\d+)*', bpl):
            return jsonify({'error':
                'Bars-per-row must be a number or dash-separated numbers, '
                'e.g. "8" or "12-12-8-12".'}), 400
        if any(int(n) < 1 for n in bpl.split('-')):
            return jsonify({'error': 'Each bars-per-row value must be at least 1.'}), 400
        args.append(bpl)

    # --- Tonal center (K) ---------------------------------------------------
    key = (data.get('key') or '').strip()
    if key:
        if key not in VALID_KEYS:
            return jsonify({'error': f'"{key}" is not one of the supported keys.'}), 400
        args.append(key)

    # --- Transpose (xT) ------------------------------------------------------
    if data.get('transpose'):
        tkey = (data.get('transposeKey') or '').strip()
        if tkey not in VALID_KEYS:
            return jsonify({'error':
                f'"{tkey}" is not a valid transpose target key.'}), 400
        args.append('x' + tkey)

    # --- Display mode --------------------------------------------------------
    if data.get('display') == 'chords':
        args.append('chords')

    # --- Run JazzVis.py in a scratch directory that's removed afterwards -----
    env = dict(os.environ)
    env['JAZZVIS_NO_OPEN'] = '1'

    with tempfile.TemporaryDirectory(prefix='jazzvis_') as run_dir:
        try:
            result = subprocess.run(
                args, cwd=run_dir, capture_output=True, text=True,
                timeout=60, env=env,
            )
        except subprocess.TimeoutExpired:
            return jsonify({'error': 'JazzVis.py took too long to respond.'}), 504

        log = result.stdout
        if result.stderr.strip():
            log += ('\n' if log else '') + result.stderr

        if result.returncode != 0:
            return jsonify({
                'error': 'JazzVis.py reported an error — see the log for details.',
                'log': log,
                'command': args[1:],
            }), 500

        m = re.search(r'Saved:\s*(\S.*\.png)\s*$', result.stdout, re.MULTILINE)
        if not m:
            return jsonify({'error': 'JazzVis.py did not report a saved image.', 'log': log}), 500

        img_name = m.group(1).strip()
        img_path = os.path.join(run_dir, img_name)
        if not os.path.isfile(img_path):
            return jsonify({'error': 'The generated image could not be found.', 'log': log}), 500

        with open(img_path, 'rb') as fh:
            image_bytes = fh.read()

    # run_dir (and its contents) is deleted here, on exiting the `with` block.

    tonal_center = None
    tm = re.search(r'Tonal center:\s*(\S+)', result.stdout)
    if tm:
        tonal_center = tm.group(1).strip()

    image_data_url = 'data:image/png;base64,' + base64.b64encode(image_bytes).decode('ascii')

    return jsonify({
        'image':       image_data_url,
        'filename':    img_name,
        'tonalCenter': tonal_center,
        'log':         log,
        'command':     args[1:],
    })


# ---------------------------------------------------------------------------

if __name__ == '__main__':
    app.run(debug=True, port=5050)
