#!/usr/bin/env python3
"""
JazzVis.py  –  Jazz Chord Progression Visualiser
Python translation of JazzVis.pl

Version history (inherited from Perl original)
----------------------------------------------
26-Jan-2022
  - Implemented display of songs with variable row lengths.
    Examples: Wave.ls (12-12-8-12), MoonlightInVermont-CB.ls (6-6-8-6).
    Default is 8 bars per line; a single integer argument sets all rows.
  - Fixed secondary dominants (in ChordProgUtils) to work for all modulations.
27-Jan-2022
  - Changed flag_dimdom to simply flag all diminished chords.

Special symbols used in labels
-------------------------------
  flat:        ♭
  sharp:       ♯
  center dot:  •

Usage
-----
    python JazzVis.py SongDB/<song.ls> [N] [K] [xT] [chords] [d=@par] [help]

Command-line parameters (optional):
    N      Integer or dash-separated integers, bars per row (default 8)
    K      Reference major key e.g. Bb, F# (default: auto-computed)
    xT     Transpose to key T, e.g. xC, xBb  (forces --chords display)
    chords Show actual chords instead of Roman numerals
    d=...  Comma-separated diagnostics: fgr, bgr, keys, flgs
    help   Print this message and exit
"""

import sys
import os
import math
import re
import subprocess
from PIL import Image, ImageDraw, ImageFont

import ChordProgUtils

# ---------------------------------------------------------------------------
# Some special symbols (use for searching)
# flat: ♭   sharp: ♯   center dot: •
# ---------------------------------------------------------------------------

# ===========================================================================
# Parse the command line
# ===========================================================================

filename     = None
altkey       = None
songkey      = None
altflag      = False
transpose_flag = False
transpose_key  = None
diagnose     = {}
displayflag  = 'symbols'
bpl_arg      = None   # raw bars-per-line argument string

for argv in sys.argv[1:]:
    # Accept any song file: paths containing SongDB/XtraDB (original convention)
    # or any .ls / .txt file that exists on disk.
    if re.search(r'SongDB|XtraDB', argv) or (os.path.isfile(argv) and re.search(r'\.(ls|txt)$', argv)):
        filename = argv
    elif re.match(r'^[\d-]+$', argv):
        bpl_arg = argv
    elif re.match(r'^x([A-G](b|#)?)$', argv):
        transpose_flag = True
        transpose_key  = re.match(r'^x([A-G](b|#)?)$', argv).group(1)
    elif re.match(r'^[A-G](b|#)?$', argv):
        altkey = argv
        altflag = True
    elif argv.startswith('d='):
        params = argv[2:].split(',')
        for p in params:
            diagnose[p] = True
    elif argv == 'chords':
        displayflag = 'chords'
    elif argv == 'help':
        print(__doc__)
        sys.exit(0)

# Diagnostic background/foreground colour
diagnose_color = 'lightgray'

# ===========================================================================
# Configuration parameters
# ===========================================================================

# ===========================================================================
# Resolution scale
# ===========================================================================
# JazzVis is now often displayed full-width in a browser rather than at its
# native pixel size, so the whole chart is rendered at SCALE x its original
# dimensions (fonts, minimum canvas width, line weights) for a sharper
# result when the PNG is stretched to fill the page.
SCALE = 1.5

def _sc(n):
    """Scale a pixel/font-size value by SCALE, rounding to an int >= 1."""
    return max(1, round(n * SCALE))


# $rowheightfactor adjusts cell height as a multiple of the tallest glyph
rowheightfactor = 1.2

# Font sizes (pre-scale values; SCALE is applied just below)
#   fs_glyph : key-membership glyphs (e.g., 4♭)
#   fs_spc   : space tokens
#   fs_chord : chord / Roman-numeral labels
#   fs_en    : bracket enclosures
#   fs_title : song title
fs_glyph = 11
fs_spc   = 11
fs_chord = 14
fs_en    = 24
fs_title = 18

# Bracket enclosure characters and space placeholder
enl = '['
enr = ']'
spc = 'o'

# Font paths. Checked in order:
#   1. ./DejaVu-ttf/...            (original Perl-era convention, cwd-relative)
#   2. <this script's dir>/fonts/  (bundled with the JazzVis web app, so it
#                                    works regardless of the process's cwd
#                                    or which fonts happen to be installed
#                                    on the host system)
#   3. system DejaVu fonts
_SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
_LOCAL_SERIF = './DejaVu-ttf/DejaVuSerifCondensed.ttf'
_LOCAL_SANS  = './DejaVu-ttf/DejaVuSans.ttf'
_BUNDLED_SERIF = os.path.join(_SCRIPT_DIR, 'fonts', 'DejaVuSerifCondensed.ttf')
_BUNDLED_SANS  = os.path.join(_SCRIPT_DIR, 'fonts', 'DejaVuSans.ttf')
_SYS_SERIF   = '/usr/share/fonts/truetype/dejavu/DejaVuSerifCondensed.ttf'
_SYS_SANS    = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'

if os.path.exists(_LOCAL_SERIF):
    font_path = _LOCAL_SERIF
elif os.path.exists(_BUNDLED_SERIF):
    font_path = _BUNDLED_SERIF
else:
    font_path = _SYS_SERIF

if os.path.exists(_LOCAL_SANS):
    font_info_path = _LOCAL_SANS
elif os.path.exists(_BUNDLED_SANS):
    font_info_path = _BUNDLED_SANS
else:
    font_info_path = _SYS_SANS

# Adjust sizes for chord-name display mode
if displayflag == 'chords':
    fs_glyph = 9
    fs_spc   = 9
    fs_chord = 12
    fs_en    = 20
    fs_title = 18
    rowheightfactor = 1.2

# Apply the resolution scale to every font size now that the display-mode
# adjustment above has been made.
fs_glyph = _sc(fs_glyph)
fs_spc   = _sc(fs_spc)
fs_chord = _sc(fs_chord)
fs_en    = _sc(fs_en)
fs_title = _sc(fs_title)

if not filename:
    sys.exit("\n*** INPUT SONGS ARE LOCATED IN THE SongDB DIRECTORY ***\n")

# ===========================================================================
# Helper: load a PIL font at a given size
# ===========================================================================

_warned_no_truetype = False

def _pil_font(path, size):
    """Load a TrueType font; fall back to the built-in default on failure.

    The built-in PIL default font is a small, non-scaling bitmap font with
    no glyphs for the music flat/sharp symbols (♭/♯) used throughout this
    chart, so falling back to it produces both "tofu" boxes and visibly
    pixelated text. If that happens, print a one-time warning so the cause
    is easy to diagnose.
    """
    global _warned_no_truetype
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        if not _warned_no_truetype:
            print(
                f"Warning: could not load TrueType font '{path}'. "
                "Falling back to a built-in bitmap font, which will not "
                "render the ♭/♯ symbols correctly and will look pixelated.",
                file=sys.stderr,
            )
            _warned_no_truetype = True
        return ImageFont.load_default()


def _text_bbox(font_obj, text):
    """Return (width, height, center_x_offset, center_y_offset) for text.

    Pillow's getbbox() returns (left, top, right, bottom) in pixel offsets
    from the draw origin, where top is typically negative (ascender above
    baseline) and bottom is positive (descender below baseline).

    We derive the same four quantities that the GD stringFT call returns
    and that the Perl code uses:
        w  = right  - left     (total pixel width of the glyph)
        h  = bottom - top      (total pixel height, ascender + descender)
        cw = (right + left)/2  (horizontal offset from origin to glyph centre)
        ch = (bottom + top)/2  (vertical offset from origin to glyph centre)
    These are used to centre each symbol on the cell midline.
    """
    if not text or text == ' ':
        # Space: use an 'm' for sizing then scale down
        try:
            l, t, r, b = font_obj.getbbox('m')
        except Exception:
            sz = getattr(font_obj, 'size', 12)
            return sz // 2, sz, 0, 0
        w = (r - l) // 2
        h = b - t
        return w, h, w / 2, (b + t) / 2

    try:
        l, t, r, b = font_obj.getbbox(text)
    except Exception:
        sz = getattr(font_obj, 'size', 12)
        w_guess = len(text) * sz // 2
        return w_guess, sz, w_guess / 2, sz / 2
    w  = r - l
    h  = b - t
    cw = (r + l) / 2
    ch = (b + t) / 2
    return w, h, cw, ch


# ===========================================================================
# Read and process the progression
# ===========================================================================

song_data = ChordProgUtils.getsong(filename)
title, composer, dbkey, truekey, bpm, btyp, Nbars = song_data[:7]
progression = list(song_data[7:])

normalform = ChordProgUtils.progNormalize(progression)
normalform = ChordProgUtils.compress(normalform)

# ---------------------------------------------------------------------------
# Work out the bars-per-line (bpl) layout
# The default is 8, or 4 for short songs (8, 12, or 16 bars).
# A single integer command-line argument overrides the default; a
# dash-separated list sets individual row lengths.
# ---------------------------------------------------------------------------

if bpl_arg:
    bpl_list_raw = [int(x) for x in bpl_arg.split('-')]
    if len(bpl_list_raw) == 1:
        b = bpl_list_raw[0]
        bpl = [b] * (Nbars // b)
        rem = Nbars % b
        if rem:
            bpl.append(rem)
    else:
        bpl = bpl_list_raw
        total = sum(bpl)
        if total < Nbars:
            bpl.append(Nbars - total)
else:
    b = 4 if Nbars in (8, 12, 16) else 8
    bpl = [b] * (Nbars // b)
    rem = Nbars % b
    if rem:
        bpl.append(rem)

# ===========================================================================
# Estimate the reference key (or use the one given on the command line)
# ===========================================================================

keyhash = ChordProgUtils.estimatekey(bpm, normalform)
ksort   = sorted(keyhash, key=lambda k: keyhash[k], reverse=True)

if altflag:
    songkey = altkey
else:
    songkey = ksort[0]
    if dbkey in keyhash and keyhash[dbkey] == keyhash[songkey]:
        songkey = dbkey

# Always report the analysis key (the "tonal center"), regardless of
# diagnostics flags, so callers can show which key was actually used —
# whether it came from -K or was estimated automatically.
print(f"Tonal center: {songkey}")

# ===========================================================================
# Convert chords to Roman numerals
# ===========================================================================

chords_idx = [i for i, p in enumerate(normalform) if p != '|']
chords     = [normalform[i] for i in chords_idx]

roman      = ChordProgUtils.map2roman(songkey, chords)
progroman  = list(normalform)
for i, idx in enumerate(chords_idx):
    progroman[idx] = roman[i]

tonic_cnt = sum(1 for k in roman if k in ('iM', 'vim'))

# ===========================================================================
# Optional transposition
# ===========================================================================

if transpose_flag:
    chords = ChordProgUtils.transpose(songkey, transpose_key, chords)
    displayflag = 'chords'
    print(f"Transposing from {songkey} to {transpose_key}")
    songkey = transpose_key

# ===========================================================================
# Flag and mark harmonic phrases
# ===========================================================================

results = ChordProgUtils.flag_phrases(roman, diagnose.get('flgs', False))
Nroman  = len(roman)
flags1  = results[:Nroman]
marks1  = results[Nroman:]

# Inject flags and marks back into the full progression (including '|')
flagsprog  = list(normalform)
marksprog  = list(normalform)
chordsprog = list(normalform)
for i, idx in enumerate(chords_idx):
    flagsprog[idx]  = flags1[i]
    marksprog[idx]  = marks1[i]
    chordsprog[idx] = chords[i]

# Drop the trailing entry (Perl pops these to align with bar count)
progroman  = progroman[:-1]
flagsprog  = flagsprog[:-1]
marksprog  = marksprog[:-1]
chordsprog = chordsprog[:-1]

# Build display strings and substitute the flat symbol
def _to_str_arr(arr):
    return [str(x) for x in arr]

bars_str   = ' '.join(_to_str_arr(progroman)).replace('b', '♭')
chords_str = ' '.join(_to_str_arr(chordsprog)).replace('b', '♭')
flags_str  = ' '.join(_to_str_arr(flagsprog))
marks_str  = ' '.join(_to_str_arr(marksprog))

# ===========================================================================
# Split strings back into per-bar arrays
# ===========================================================================

bars_per_bar   = bars_str.split(' | ')
chords_per_bar = chords_str.split(' | ')
flags_per_bar  = flags_str.split(' | ')
marks_per_bar  = marks_str.split(' | ')

# ===========================================================================
# Colour table
# ===========================================================================

def make_color_table():
    """Return a dict mapping colour name -> RGB tuple.

    The 12 chord-function colours (c_i through c_vii and flattened
    variants) are defined under the 'original' palette (select == 1).
    Three additional pastel versions (m_*) are provided for minor-
    cadence backgrounds.
    """
    ct = {
        'white':     (255, 255, 255),
        'lightgray': (190, 190, 190),
        'cream':     (248, 240, 198),
        'gray':      (127, 127, 127),
        'darkgray':  ( 96,  96,  96),
        'black':     (  0,   0,   0),
        'red':       (255,   0,   0),
        'blue':      (  0,   0, 200),
        'lightblue': (192, 192, 255),
        'green':     (  0, 200,   0),
        'yellow':    (255, 255,   0),
        'magenta':   (200,   0, 200),
    }

    # Palette select == 1 (original)
    ct['c_i']    = (252,  98,  97)
    ct['c_v']    = (253, 149,  98)
    ct['c_ii']   = (252, 192,  96)
    ct['c_vi']   = (252, 222,  97)
    ct['c_iii']  = (251, 251,  97)
    ct['c_vii']  = (205, 252,  97)
    ct['c_bv']   = ( 97, 252, 106)
    ct['c_bii']  = ( 96, 253, 240)
    ct['c_bvi']  = ( 97, 160, 252)
    ct['c_biii'] = (156, 148, 253)
    ct['c_bvii'] = (213, 148, 252)
    ct['c_iv']   = (248, 136, 218)

    # Pastel variants for minor cadences (lighter / mid-tone versions)
    ct['m_i']    = (253, 176, 176)
    ct['m_v']    = (254, 202, 176)
    ct['m_ii']   = (253, 223, 175)
    ct['m_vi']   = (190, 175, 112)
    ct['m_iii']  = (190, 190, 112)
    ct['m_vii']  = (167, 190, 112)
    ct['m_bv']   = (112, 190, 117)
    ct['m_bii']  = (112, 190, 184)
    ct['m_bvi']  = (176, 207, 253)
    ct['m_biii'] = (205, 201, 254)
    ct['m_bvii'] = (234, 201, 253)
    ct['m_iv']   = (251, 195, 236)

    return ct

color = make_color_table()

# ===========================================================================
# Glyph helpers
# ===========================================================================

_flag2glyph = {
    -6: '6♭', -5: '5♭', -4: '4♭', -3: '3♭', -2: '2♭', -1: '1♭',
     0: '•',
     1: '1♯',  2: '2♯',  3: '3♯',  4: '4♯',  5: '5♯',
}

def get_glyph(flag):
    """Return the key-membership glyph string for a given flag integer.

    The glyph encodes how many sharps or flats separate the chord's key
    from the reference key.  The computation strips the tens digit so
    that, e.g., flag 32 (iim in the key a major 2nd above) maps to '2♯'.
    """
    if flag == 0:
        return '•'
    sign = 1 if flag > 0 else -1
    reduced = sign * (abs(flag) % 10)
    return _flag2glyph.get(reduced, '•')


# ===========================================================================
# Polygon geometry helpers
# ===========================================================================

def fg_poly(w, h, poly_type):
    """Compute the foreground polygon geometry for a given symbol size.

    Given a symbol bounding-box width `w` and height `h`, and the
    polygon type, return (wp, hp, px_list, py_list) where:
      wp, hp   – the width and height of the enclosing polygon
      px, py   – vertex x- and y-coordinates centred on (0, 0)

    Polygon types and their flag codes
    ------------------------------------
    'pentagon'  – borrowed chords (flags -1 to -6)
    'diamond'   – secondary dominants / dominant chains (flags 2, 3, 7)
    'circle'    – diminished dominants (flag 4)
    'square'    – tritone substitutions (flag 5)
    """
    dfactor = 1.15   # diamond scale factor
    pfactor = 1.2    # pentagon scale factor
    cfactor = 1.3    # circle scale factor
    sfactor = 1.15   # square scale factor

    if poly_type == 'pentagon':
        # Regular pentagon inscribed in a circle of radius r
        a = (math.cos(math.pi / 5) + math.cos(2 * math.pi / 5)) / \
            (math.sin(math.pi / 5) - math.sin(2 * math.pi / 5))
        r = pfactor * (math.cos(math.pi / 10) * (a * w - h) / (2 * a * math.cos(math.pi / 5)))
        px = [0,
              r * math.sin(2 * math.pi / 5),
              r * math.sin(math.pi / 5),
             -r * math.sin(math.pi / 5),
             -r * math.sin(2 * math.pi / 5),
              0]
        py = [r,
              r * math.cos(2 * math.pi / 5),
             -r * math.cos(math.pi / 5),
             -r * math.cos(math.pi / 5),
              r * math.cos(2 * math.pi / 5),
              r]
        wp = pfactor * 2 * r * math.cos(math.pi / 10)
        hp = pfactor * r * (1 + math.cos(math.pi / 5))

    elif poly_type == 'diamond':
        wp = dfactor * (w + h)
        hp = wp
        r  = wp / 2
        px = [0,  r,  0, -r,  0]
        py = [-r,  0,  r,  0, -r]

    elif poly_type == 'circle':
        wp = cfactor * math.sqrt(w ** 2 + h ** 2)
        hp = wp
        r  = wp
        px = [ r,  r, -r, -r,  r]
        py = [-r,  r,  r, -r, -r]

    elif poly_type == 'square':
        wp = sfactor * w
        hp = wp
        r  = wp / 2
        px = [ r,  r, -r, -r,  r]
        py = [-r,  r,  r, -r, -r]

    else:
        wp = w
        hp = h
        px = []
        py = []

    return wp, hp, px, py


# ===========================================================================
# Symbol dimensions
# ===========================================================================

def symbol_dims(symbols, flags, fsizes):
    """Compute bounding-box dimensions for each display symbol.

    For symbols that require a foreground polygon (diamond, pentagon,
    circle, or square), the returned width and height are enlarged to
    accommodate the polygon rather than just the text.

    Parameters
    ----------
    symbols : list of str
    flags   : list of int  (parallel to symbols)
    fsizes  : list of int  (font size for each symbol)

    Returns
    -------
    widths, heights, center_xs, center_ys : four lists of floats

    Flag -> polygon mapping
    -----------------------
    Type         Flag    Shape
    Cyc of doms   2      Diamond
    2ndary dom    3      Diamond
    Dim dom       4      Circle
    Tritone sub   5      Square
    pMinor       -1      Pentagon
    pLyd         -2      Pentagon
    pPhryg       -3      Pentagon
    pDor         -4      Pentagon
    pMixo        -5      Pentagon
    pLoc         -6      Pentagon
    """
    widths    = []
    heights   = []
    center_xs = []
    center_ys = []

    for sym, flg, fs in zip(symbols, flags, fsizes):
        fnt = _pil_font(font_path, fs)
        w, h, cw, ch = _text_bbox(fnt, sym)

        if flg in (-1, -2, -3, -4, -5, -6):
            wp, hp, _, _ = fg_poly(w, h, 'pentagon')
        elif flg in (2, 3, 7):
            wp, hp, _, _ = fg_poly(w, h, 'diamond')
        elif flg == 4:
            wp, hp, _, _ = fg_poly(w, h, 'circle')
        elif flg == 5:
            wp, hp, _, _ = fg_poly(w, h, 'square')
        else:
            wp, hp = w, h

        widths.append(wp)
        heights.append(hp)
        center_xs.append(cw)
        center_ys.append(ch)

    return widths, heights, center_xs, center_ys


# ===========================================================================
# Build the symbol, chord, flag, font-size, and bar-index chains
# ===========================================================================
# For each bar, and each chord within that bar, one or more display tokens
# are generated:
#   - A space token (spc)
#   - Optionally a key glyph (e.g. '2♯')
#   - Optionally an opening bracket '['
#   - The chord or Roman-numeral label
#   - Optionally a closing bracket ']'
#   - A trailing space token
#
# Parallel chains keep track of the flag, font-size, and bar index for
# each token.

symbolchain = []
chordchain  = []
fschain     = []
flagchain   = []
barindex    = []

for n in range(len(bars_per_bar)):
    roman_n  = bars_per_bar[n].split()
    chords_n = chords_per_bar[n].split()
    flags_n  = [int(x) for x in flags_per_bar[n].split()]
    marks_n  = [int(x) for x in marks_per_bar[n].split()]

    for m in range(len(roman_n)):
        if marks_n[m] == 1:
            glyph = get_glyph(flags_n[m])
            if glyph == '•':
                symbolchain += [spc, enl, roman_n[m]]
                chordchain  += [spc, enl, chords_n[m]]
                flagchain   += [0, 0, flags_n[m]]
                fschain     += [fs_spc, fs_en, fs_chord]
                barindex    += [n, n, n]
            else:
                symbolchain += [spc, glyph, enl, roman_n[m]]
                chordchain  += [spc, glyph, enl, chords_n[m]]
                flagchain   += [0, 0, 0, flags_n[m]]
                fschain     += [fs_spc, fs_glyph, fs_en, fs_chord]
                barindex    += [n, n, n, n]
        elif marks_n[m] == -1:
            if m == len(roman_n) - 1:
                symbolchain += [spc, roman_n[m], enr]
                chordchain  += [spc, chords_n[m], enr]
                flagchain   += [0, flags_n[m], 0]
                fschain     += [fs_spc, fs_chord, fs_en]
                barindex    += [n, n, n]
            else:
                symbolchain += [spc, roman_n[m], enr, spc]
                chordchain  += [spc, chords_n[m], enr, spc]
                flagchain   += [0, flags_n[m], 0, 0]
                fschain     += [fs_spc, fs_chord, fs_en, fs_spc]
                barindex    += [n, n, n, n]
        else:
            symbolchain += [spc, roman_n[m]]
            chordchain  += [spc, chords_n[m]]
            flagchain   += [0, flags_n[m]]
            fschain     += [fs_spc, fs_chord]
            barindex    += [n, n]

    symbolchain.append(spc)
    chordchain.append(spc)
    fschain.append(fs_spc)
    flagchain.append(0)
    barindex.append(n)

# Choose between Roman-numeral or chord-name display
displaychain = chordchain if displayflag == 'chords' else symbolchain

# ===========================================================================
# Compute symbol dimensions
# ===========================================================================

symbolwidth, symbolheight, symcenter_x, symcenter_y = symbol_dims(
    displaychain, flagchain, fschain
)

# ===========================================================================
# Compute per-bar string widths and global cell height
# ===========================================================================

cell_str_width  = [0.0] * len(bars_per_bar)
cell_str_height = 0.0

for k, (w, h, bi) in enumerate(zip(symbolwidth, symbolheight, barindex)):
    cell_str_width[bi] += w
    if h > cell_str_height:
        cell_str_height = h

# ===========================================================================
# Work out column widths for the table layout
# ===========================================================================
# The table has len(bpl) rows; each row has bpl[j] columns.  Each column
# width is set to the widest bar in that column across all rows.

Nlines  = len(bpl)
maxline = max(bpl)
cellwidth  = [0.0] * maxline
cellheight = rowheightfactor * cell_str_height + 8

arg = 0
for j in range(Nlines):
    for i in range(bpl[j]):
        if arg > Nbars - 1:
            break
        if cell_str_width[arg] > cellwidth[i]:
            cellwidth[i] = cell_str_width[arg]
        arg += 1

# ===========================================================================
# Centre each bar's symbol string within its column
# ===========================================================================
# Bars narrower than their column get extra space added to their first
# and last space token so the content is centred.

arg = 0
for j in range(Nlines):
    for i in range(bpl[j]):
        if arg > Nbars - 1:
            break
        delta_width = cellwidth[i] - cell_str_width[arg]
        if delta_width > 0:
            stretch = delta_width / 2
            inds = [k for k, bi in enumerate(barindex) if bi == arg]
            if inds:
                symbolwidth[inds[0]]  += stretch
                symbolwidth[inds[-1]] += stretch
        arg += 1

# ===========================================================================
# Compute canvas dimensions and table/cell coordinates
# ===========================================================================

tablewidth  = sum(cellwidth)
tableheight = cellheight * Nlines

canvaswidth  = max(int(1.1 * tablewidth), _sc(1000))
canvasheight = int(1.1 * tableheight)
legendheight = _sc(250)

x0        = canvaswidth / 2 - tablewidth / 2
topmargin = 0.025 * tablewidth
y0        = topmargin
xf        = x0 + tablewidth
yf        = y0 + tableheight

# Per-cell upper-left corners
cellx = []
celly = []
for j in range(Nlines):
    yj = y0 + j * cellheight
    xi = x0
    for i in range(bpl[j]):
        cellx.append(xi)
        celly.append(yj)
        xi += cellwidth[i]

# ===========================================================================
# Background colour maps
# ===========================================================================

# Map from glyph string -> chord-function colour name
glyph2bgcolor = {
    '6♭': 'c_bv',  '5♭': 'c_bii', '4♭': 'c_bvi', '3♭': 'c_biii',
    '2♭': 'c_bvii','1♭': 'c_iv',   'o':  'c_i',
    '1♯': 'c_v',   '2♯': 'c_ii',   '3♯': 'c_vi',  '4♯': 'c_iii',
    '5♯': 'c_vii', 'sd': 'gray',
}

# Pastel variants for minor cadences
mglyph2bgcolor = {
    '6♭': 'm_bv',  '5♭': 'm_bii', '4♭': 'm_bvi', '3♭': 'm_biii',
    '2♭': 'm_bvii','1♭': 'm_iv',   'o':  'm_i',
    '1♯': 'm_v',   '2♯': 'm_ii',   '3♯': 'm_vi',  '4♯': 'm_iii',
    '5♯': 'm_vii', 'sd': 'gray',
}

# Map from flag integer -> glyph string (for singleton major-key chords)
flag2bgcolor = {
    -36: '6♭', -35: '5♭', -34: '4♭', -33: '3♭', -32: '2♭', -31: '1♭',
     30: 'o',
     31: '1♯',  32: '2♯',  33: '3♯',  34: '4♯',  35: '5♯',
}

# ===========================================================================
# Build the background-colour and minor-flag chains
# ===========================================================================

bgcolorchain   = [0] * len(displaychain)
minorflagchain = [0] * len(displaychain)

enc_l_pos = [i for i, d in enumerate(displaychain) if d == '[']
enc_r_pos = [i for i, d in enumerate(displaychain) if d == ']']

def _is_minor_flag(f):
    """Return True if the flag value indicates a minor cadence."""
    af = abs(f)
    return (40 <= af <= 46) or (20 <= af <= 26) or af == 146

# Handle wrap-around cadence: enc_r[0] < enc_l[0]
if enc_r_pos and enc_l_pos and enc_r_pos[0] < enc_l_pos[0]:
    enr0 = enc_r_pos.pop(0)
    enl0 = enc_l_pos.pop()
    for l in range(enl0 - 1, len(bgcolorchain)):
        bgcolorchain[l] = displaychain[enl0 - 1]
        if _is_minor_flag(flagchain[enl0 + 1]):
            minorflagchain[l] = 1
    for k in range(0, enr0 + 2):
        bgcolorchain[k] = displaychain[enl0 - 1]
        if _is_minor_flag(flagchain[enl0 + 1]):
            minorflagchain[k] = 1
    if displaychain[enl0 - 1] != spc:
        bgcolorchain[enl0 - 2] = displaychain[enl0 - 1]
    if minorflagchain[enl0 - 1] != 0:
        minorflagchain[enl0 - 2] = minorflagchain[enl0 - 1]

# All other cadences (non-wrapping)
for k in range(len(enc_l_pos)):
    el = enc_l_pos[k]
    er = enc_r_pos[k]
    for l in range(el - 1, er + 2):
        bgcolorchain[l] = displaychain[el - 1]
        if _is_minor_flag(flagchain[el + 1]):
            minorflagchain[l] = 1
    if displaychain[el - 1] != spc:
        bgcolorchain[el - 2] = displaychain[el - 1]
        minorflagchain[el - 2] = minorflagchain[el - 1]

# Singleton reference-key chords (flag == 1)
for k in range(len(bgcolorchain)):
    if flagchain[k] == 1:
        for kk in (k - 1, k, k + 1):
            if 0 <= kk < len(bgcolorchain):
                bgcolorchain[kk] = spc

# Dominant chains (flags 2, 6, 7) -> gray background
for k in range(1, len(bgcolorchain) - 1):
    if flagchain[k] in (2, 6, 7):
        bgcolorchain[k - 1] = 'sd'
        bgcolorchain[k]     = 'sd'
        bgcolorchain[k + 1] = 'sd'

# Backwards pass: borrowed / approach chords inherit the colour of the
# chord they resolve to (two positions ahead, already-resolved by this
# point since the loop runs from high index to low index)
for k in range(len(bgcolorchain) - 3, 0, -1):
    if flagchain[k] in (3, 4, -1, -2, -3, -4, -5, -6):
        inherited = bgcolorchain[k + 2]
        bgcolorchain[k + 1] = inherited
        bgcolorchain[k]     = inherited
        bgcolorchain[k - 1] = inherited

# Handle end wrap-around
k = len(bgcolorchain) - 2
if flagchain[k] in (3, 4, -1, -2, -3, -4, -5, -6):
    for kk in (k - 1, k, k + 1):
        if 0 <= kk < len(bgcolorchain):
            bgcolorchain[kk] = bgcolorchain[1]

# Remaining singleton major-key chords
for k in range(len(bgcolorchain)):
    af = abs(flagchain[k])
    if 30 <= af <= 36 and bgcolorchain[k] == 0:
        glyph = flag2bgcolor.get(flagchain[k], 'o')
        for kk in (k - 1, k, k + 1):
            if 0 <= kk < len(bgcolorchain):
                bgcolorchain[kk] = glyph

# ===========================================================================
# Create the PIL image
# ===========================================================================

total_height = canvasheight + legendheight
img  = Image.new('RGB', (canvaswidth, total_height), color['white'])
draw = ImageDraw.Draw(img)

# ---------------------------------------------------------------------------
# Helper: draw a filled polygon given vertex lists
# ---------------------------------------------------------------------------

def _draw_poly(cx, cy, px, py, fill_rgb, outline_rgb):
    """Draw and fill a polygon centred at (cx, cy)."""
    pts = [(cx + x, cy + y) for x, y in zip(px, py)]
    draw.polygon(pts, fill=fill_rgb, outline=outline_rgb)

# ===========================================================================
# Draw background rectangles
# ===========================================================================

arg = 0
for j in range(Nlines):
    for i in range(bpl[j]):
        if arg > Nbars - 1:
            break
        xi = cellx[arg]
        yj = celly[arg]
        inds   = [k for k, bi in enumerate(barindex) if bi == arg]
        widths = [symbolwidth[k]    for k in inds]
        bgc    = [bgcolorchain[k]   for k in inds]
        mnrs   = [minorflagchain[k] for k in inds]

        for k in range(len(widths)):
            xip1 = xi + widths[k]
            yjp1 = yj + cellheight
            bg_name = glyph2bgcolor.get(bgc[k] if isinstance(bgc[k], str) else '', 'white')
            mbg_name = mglyph2bgcolor.get(bgc[k] if isinstance(bgc[k], str) else '', 'white')
            clr  = color.get(bg_name,  color['white'])
            mclr = color.get(mbg_name, color['white'])

            if not mnrs[k]:
                draw.rectangle([xi, yj, xip1, yjp1], fill=clr)
            else:
                # Minor cadence: three horizontal bands
                third = (yjp1 - yj) / 3
                draw.rectangle([xi, yj,           xip1, yj + third],     fill=clr)
                draw.rectangle([xi, yj + third,   xip1, yj + 2 * third], fill=mclr)
                draw.rectangle([xi, yj + 2*third, xip1, yjp1],           fill=clr)

            if diagnose.get('bgr'):
                draw.rectangle([xi, yj, xip1, yjp1], outline=color[diagnose_color])

            xi = xip1
        arg += 1

# ===========================================================================
# Draw cell border rectangles
# ===========================================================================

arg = 0
for j in range(Nlines):
    yj   = y0 + j * cellheight
    yjp1 = yj + cellheight
    xi   = x0
    for i in range(bpl[j]):
        if arg > Nbars - 1:
            break
        xip1 = xi + cellwidth[i]
        draw.rectangle([xi, yj, xip1, yjp1], outline=color['black'], width=_sc(2))
        xi = xip1
        arg += 1

# ===========================================================================
# Foreground colour maps for modal / dominant polygons
# ===========================================================================

# Colour used for the polygon of a borrowed (parallel-mode) chord
modal_color = {
    -6: color['c_bii'],
    -5: color['c_iv'],
    -4: color['c_bvii'],
    -3: color['c_bvi'],
    -2: color['c_v'],
    -1: color['c_biii'],
}

# Colour for dominant (diamond) polygon, keyed by the Roman-numeral token
doms_color = {
    'i7':    color['c_iv'],
    '♭ii7':  color['c_bv'],
    'ii7':   color['c_v'],
    '♭iii7': color['c_bvi'],
    'iii7':  color['c_vi'],
    'iv7':   color['c_bvii'],
    '♭v7':   color['c_vii'],
    'v7':    color['c_i'],
    '♭vi7':  color['c_bii'],
    'vi7':   color['c_ii'],
    '♭vii7': color['c_biii'],
    'vii7':  color['c_iii'],
}

# ===========================================================================
# Draw foreground polygons and text
# ===========================================================================

arg = 0
for j in range(Nlines):
    for i in range(bpl[j]):
        if arg > Nbars - 1:
            break
        xi = cellx[arg]
        yj = celly[arg] + cellheight / 2   # vertical centre of cell

        inds    = [k for k, bi in enumerate(barindex) if bi == arg]
        symbs   = [displaychain[k] for k in inds]
        domcols = [symbolchain[k]  for k in inds]   # for dominant colour lookup
        flgs    = [flagchain[k]    for k in inds]
        fss     = [fschain[k]      for k in inds]
        widths  = [symbolwidth[k]  for k in inds]
        heights = [symbolheight[k] for k in inds]

        for k in range(len(widths)):
            xip1 = xi + widths[k]
            cx   = (xi + xip1) / 2   # horizontal centre
            yjp1 = yj + heights[k] / 2

            if diagnose.get('fgr'):
                draw.rectangle(
                    [xi, yj - heights[k] / 2, xip1, yjp1],
                    outline=color[diagnose_color]
                )

            # Replace the spc token with a regular space for rendering
            display_sym = ' ' if symbs[k] == spc else symbs[k]

            # Measure the symbol for polygon sizing
            fnt = _pil_font(font_path, fss[k])
            w, h, cw, ch = _text_bbox(fnt, display_sym)

            # -----------------------------------------------------------------
            # Foreground polygons
            # -----------------------------------------------------------------

            # Pentagons for borrowed (parallel-mode) chords (flags -1 to -6)
            if flgs[k] in (-1, -2, -3, -4, -5, -6):
                wp, hp, px, py = fg_poly(w, h, 'pentagon')
                fill_c = modal_color.get(flgs[k], color['gray'])
                _draw_poly(cx, yj, px, py, fill_c, color['white'])

            # Diamonds for secondary dominants, chains (flags 2, 3, 7)
            if flgs[k] in (2, 3, 7):
                wp, hp, px, py = fg_poly(w, h, 'diamond')
                dom_key = domcols[k]
                fill_c  = doms_color.get(dom_key, color['gray'])
                _draw_poly(cx, yj, px, py, fill_c, color['white'])

            # Circles for diminished dominants (flag 4)
            if flgs[k] == 4:
                wp, hp, px, py = fg_poly(w, h, 'circle')
                r_ellipse = wp / 2
                draw.ellipse(
                    [cx - r_ellipse, yj - r_ellipse, cx + r_ellipse, yj + r_ellipse],
                    fill=color['black'], outline=color['white']
                )

            # Squares for tritone substitutions (flag 5)
            if flgs[k] == 5:
                wp, hp, px, py = fg_poly(w, h, 'square')
                _draw_poly(cx, yj, px, py, color['gray'], color['white'])

            # -----------------------------------------------------------------
            # Text rendering
            # -----------------------------------------------------------------
            # Determine text colour (white on dark backgrounds)
            text_color = color['black']
            if flgs[k] == 4:
                text_color = color['white']
            if flgs[k] == 5:
                text_color = color['white']
            if flgs[k] == 6:
                text_color = color['white']

            symx = cx - cw
            symy = yj - ch
            fnt  = _pil_font(font_path, fss[k])
            draw.text((symx, symy), display_sym, font=fnt, fill=text_color)

            xi = xip1
        arg += 1

# ===========================================================================
# Legend (key wheel) and song info block
# ===========================================================================

def get_legend(x0_leg, y0_leg, margin, flag, key):
    """Draw a colour-coded circle-of-fifths pie chart at (x0_leg, y0_leg).

    Replicates the GD filledArc / ellipse / line approach from the Perl original:
      - 12 filled pie slices, each 30° wide, starting at 15°
      - Black radial separator lines drawn from centre to rim after filling
      - Thick black outer ellipse border
      - Filled white inner ellipse (donut hole) with black border
      - Inner ring: key-distance labels  (e.g. '1♭', 'ref', '1♯')
      - Outer ring: scale-degree or key-name labels (e.g. 'I', 'V', 'F', 'C')

    Parameters
    ----------
    x0_leg, y0_leg : float   Centre of the pie chart.
    margin         : float   GD filledArc width/height = margin/2; the drawn
                             circle has radius = margin/4.
    flag           : str     'chords' or 'symbols' – controls outer label text.
    key            : str     Reference major key (used in chord-mode labels).
    """
    # In the Perl original:
    #   r = margin / 2            (e.g. 125 when margin=250)
    #   filledArc(x0, y0, r, r, ...) -> GD width=height=r => actual radius = r/2
    # So the drawn circle radius = margin / 4.
    r = margin / 2          # matches Perl's $r variable
    arc_radius = r / 2      # actual pixel radius of the pie circle

    # 12 pie slices, each 30° wide, starting at 15°
    theta = [k * 30 + 15 for k in range(13)]

    # Colour order around the circle of fifths (clockwise from ~45° = iii position)
    piecolor = ['c_iii', 'c_vii', 'c_bv', 'c_bii', 'c_bvi', 'c_biii',
                'c_bvii', 'c_iv', 'c_i', 'c_v', 'c_ii', 'c_vi']

    # --- Draw filled pie slices ---
    bbox = [x0_leg - arc_radius, y0_leg - arc_radius,
            x0_leg + arc_radius, y0_leg + arc_radius]
    for k in range(12):
        draw.pieslice(bbox, start=theta[k], end=theta[k + 1],
                      fill=color[piecolor[k]])

    # --- Draw black radial separator lines (one per slice boundary) ---
    # In Perl: $img->setThickness(1) then $img->line(x0,y0, x0+r*cos/2, y0+r*sin/2, black)
    # The line goes from centre to the rim (arc_radius = r/2).
    for k in range(len(theta)):
        angle_rad = math.radians(theta[k])
        x_end = x0_leg + arc_radius * math.cos(angle_rad)
        y_end = y0_leg + arc_radius * math.sin(angle_rad)
        draw.line([x0_leg, y0_leg, x_end, y_end], fill=color['black'], width=_sc(1))

    # --- Thick black outer ellipse border ---
    draw.ellipse(bbox, outline=color['black'], width=_sc(4))

    # --- Filled white inner circle (donut hole) + black border ---
    hole_r = arc_radius / 2   # Perl: filledEllipse(x0,y0, r/2, r/2, ...) = radius r/4
    hole_bbox = [x0_leg - hole_r, y0_leg - hole_r,
                 x0_leg + hole_r, y0_leg + hole_r]
    draw.ellipse(hole_bbox, fill=color['white'], outline=color['black'], width=_sc(3))

    # --- Labels ---
    labels = ['4♯', '5♯', '6♭', '5♭', '4♭', '3♭', '2♭', '1♭', 'ref', '1♯', '2♯', '3♯']
    if flag == 'chords':
        # modes_all[8] corresponds to 'C' (the 'ref' position when the
        # reference key is C). To rotate so that modes[8] == key, we need
        # modes[i] = modes_all[(i + rot) % 12] with rot = (index_of(key) - 8) % 12.
        modes_all = ['E', 'B', 'Gb', 'Db', 'Ab', 'Eb', 'Bb', 'F', 'C', 'G', 'D', 'A']
        try:
            idx = modes_all.index(key)
        except ValueError:
            idx = 8   # default to C if key not found
        rot = (idx - 8) % 12
        modes = [modes_all[(i + rot) % 12] for i in range(12)]
    else:
        modes = ['III', 'VII', '♭V', '♭II', '♭VI', '♭III', '♭VII', 'IV', 'I', 'V', 'II', 'VI']

    fnt_lbl = _pil_font(font_info_path, fs_spc)
    # Perl: rho1 = (r + r/2)/4 = 3r/8  (inner-ring label radius)
    #        rho2 = 3*r/5              (outer-ring label radius)
    rho1 = (r + r / 2) / 4
    rho2 = 3 * r / 5

    for k in range(12):
        phi = math.radians((theta[k] + theta[k + 1]) / 2)
        # Inner label (key-distance glyph, e.g. '1♭', 'ref')
        wt, ht, cwt, cht = _text_bbox(fnt_lbl, labels[k])
        xl = x0_leg - cwt + rho1 * math.cos(phi)
        yl = y0_leg - cht + rho1 * math.sin(phi)
        draw.text((xl, yl), labels[k], font=fnt_lbl, fill=color['black'])
        # Outer label (Roman numeral or key name; render flats with '♭')
        mode_label = re.sub(r'b$', '♭', modes[k])
        wt, ht, cwt, cht = _text_bbox(fnt_lbl, mode_label)
        xl = x0_leg - cwt + rho2 * math.cos(phi)
        yl = y0_leg - cht + rho2 * math.sin(phi)
        draw.text((xl, yl), mode_label, font=fnt_lbl, fill=color['black'])


# Draw the legend
px_legend = x0 + tablewidth / 2 - legendheight / 4 - 50
py_legend = y0 + tableheight + legendheight / 2
get_legend(px_legend, py_legend, legendheight, displayflag, songkey)

# ---------------------------------------------------------------------------
# Song info block (title, key, time signature, bar count)
# ---------------------------------------------------------------------------

fnt_spc   = _pil_font(font_path, fs_spc)
fnt_chord = _pil_font(font_info_path, fs_chord)
fnt_title = _pil_font(font_info_path, fs_title)

_, hspc, _, _ = _text_bbox(fnt_spc, 'o')

info_lines = [
    (title,                                              fnt_title),
    (f"Number of Bars: {Nbars}",                        fnt_chord),
    (f"Time Signature: {bpm}/{btyp}",                   fnt_chord),
    (f"DB Key Signature: {dbkey}",                      fnt_chord),
    (f"{'Display transposed to' if transpose_flag else 'Ref. Major Scale'}: {songkey}", fnt_chord),
]

infox = x0 + tablewidth / 2 + 50
block_h = sum(_text_bbox(f, t)[1] + hspc for t, f in info_lines)
infoy = y0 + tableheight + legendheight / 2 - block_h / 2

cur_y = infoy
for text, fnt in info_lines:
    _, ht, _, _ = _text_bbox(fnt, text)
    draw.text((infox, cur_y), text, font=fnt, fill=color['black'])
    cur_y += ht + hspc

# Diagnostic key weights
if diagnose.get('keys'):
    term = "Major Key Weights: " + " ".join(
        f"{k}({round(keyhash[k])})" for k in ksort
    )
    print(f"\n{term}\n")

# ===========================================================================
# Save and display the image
# ===========================================================================

clean_title = re.sub(r"[,' ]+", '_', title or 'output')
outputname  = f"img_{clean_title}.png"
img.save(outputname)
print(f"Saved: {outputname}")

# Try to open the image in the system viewer (skip when run headless,
# e.g. from the JazzVis web service, via JAZZVIS_NO_OPEN=1)
if not os.environ.get('JAZZVIS_NO_OPEN'):
    try:
        if sys.platform.startswith('darwin'):
            subprocess.run(['open', outputname])
        elif sys.platform.startswith('linux'):
            subprocess.run(['xdg-open', outputname])
        elif sys.platform.startswith('win'):
            os.startfile(outputname)
    except Exception:
        pass
