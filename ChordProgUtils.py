"""
ChordProgUtils.py
Python translation of ChordProgUtils.pm

Utility functions for jazz chord-progression analysis:
  - Parsing song files
  - Normalizing chord names to a canonical enharmonic form
  - Compressing repeated adjacent chords
  - Estimating the reference major key of a progression
  - Mapping chords to Roman-numeral form
  - Transposing a progression to a new key
  - Flagging harmonic phrase types (cadences, secondary dominants,
    borrowed chords, modal colours, chains of dominants, etc.)
  - Merging overlapping flag/mark arrays

Flag-code reference
-------------------
Patterns
  p251           [-36, -35, -34, -33, -32, -31, 30, 31, 32, 33, 34, 35]
  pm251          [-46, -45, -44, -43, -42, -41, 40, 41, 42, 43, 44, 45]
  p2b21          [-136,-135,-134,-133,-132,-131,130,131,132,133,134,135]
  pm2b21         [-146,-145,-144,-143,-142,-141,140,141,142,143,144,145]

  p25            [-16, -15, -14, -13, -12, -11, 10, 11, 12, 13, 14, 15]
  pm25           [-26, -25, -23, -21, 21, 23, 25]
  p2b2           [-116,-115,-114,-113,-112,-111,110,111,112,113,114,115]
  pm2b2          [-126,-125,-124,-123,-122,-121,120,121,122,123,124,125]

  p51            [-56, -55, -54, -53, -52, -51, 50, 51, 52, 53, 54, 55]
  pb21           [-156,-155,-154,-153,-152,-151,150,151,152,153,154,155]

  pchain_doms    [2] [6] and [7]
  p2nd_doms      [3]
  pdim_doms      [4]

  mainkey        [1]
  pminorkey      [-1]
  pLydiankey     [-2]
  pPhrygiankey   [-3]
  pDoriankey     [-4]
  pMixolydiankey [-5]
  pLocriankey    [-6]
"""

import re


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _getroot(chord):
    """Extract the chord root (e.g., 'Bb' from 'Bbm7b5').
    Returns 'NC' unchanged."""
    if chord == 'NC':
        return 'NC'
    m = re.match(r'([A-G]b?)', chord)
    return m.group(1) if m else chord


def _chordclass(p):
    """Return the harmonic class of a chord string.

    Classes:
      'h'  half-diminished  (m7b5 / h7)
      '7'  dominant seventh and extensions (7, 9, 11, 13, sus)
      'M'  major (maj7, add9, major triads, etc.)
      'm'  minor
      'o'  diminished
      '5'  power chord
      'N'  no chord (NC)
      'U'  unrecognised
    """
    p = p.strip().replace(' ', '')
    if re.search(r'[A-G](b|#)?(m7b5|h7)', p):
        return 'h'
    elif re.search(r'[A-G](b|#)?(7|9|11|13|sus)', p):
        return '7'
    elif re.search(r'[A-G](b|#)?maj(7|9|11|13)', p):
        return 'M'
    elif re.search(r'[A-G](b|#)?m(M|Maj)?(7|9|11|13|6|69)?', p):
        return 'm'
    elif re.search(r'[A-G](b|#)?(o|dim)', p):
        return 'o'
    elif re.search(r'[A-G](b|#)?(\+|add|/|M|M7|M9|2|6|69)', p):
        return 'M'
    elif re.match(r'^[A-G](b|#)?$', p):
        return 'M'
    elif re.match(r'^[A-G](b|#)?(4|phryg)$', p):
        return 'm'
    elif re.search(r'[A-G](b|#)?5', p):
        return '5'
    elif 'NC' in p:
        return 'N'
    else:
        return 'U'


def _chordnormalize(cin):
    """Convert a chord to its canonical enharmonic form.

    All sharps are converted to their flat equivalents, and the
    enharmonic spellings Cb, Fb, B#, and E# are converted to B, E, C,
    and F respectively.  Slash chords are handled recursively.
    """
    cin = cin.strip().replace(' ', '')
    if '/' in cin:
        parts = cin.split('/', 1)
        return _chordnormalize(parts[0]) + '/' + _chordnormalize(parts[1])

    _norm = {
        'A': 'A', 'B': 'B', 'C': 'C', 'D': 'D', 'E': 'E',
        'F': 'F', 'G': 'G',
        'Ab': 'Ab', 'Bb': 'Bb', 'Cb': 'B',  'Db': 'Db', 'Eb': 'Eb',
        'Fb': 'E',  'Gb': 'Gb',
        'A#': 'Bb', 'B#': 'C',  'C#': 'Db', 'D#': 'Eb', 'E#': 'F',
        'F#': 'Gb', 'G#': 'Ab',
        'x': 'x', 'NC': 'NC',
    }

    m = re.match(r'([A-G](b|#)?)(.*)', cin)
    if not m:
        return cin
    root, _, ext = m.group(1), m.group(2), m.group(3)
    if cin == 'NC':
        return 'NC'
    return _norm.get(root, root) + ext


def _getinterval(r1, r2):
    """Return the interval name from root r1 to root r2 (both in concert pitch).

    The interval is expressed in functional form (e.g., 'iv', 'bvii').
    """
    chromatic = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B']
    intervals = ['0', 'bii', 'ii', 'biii', 'iii', 'iv', 'bv', 'v', 'bvi', 'vi', 'bvii', 'vii']
    b1 = chromatic.index(r1)
    b2 = chromatic.index(r2)
    delta = (b2 - b1) % 12
    return intervals[delta]


def _match_chord_phrase(pattern, tokens):
    """Find all occurrences of a chord phrase (with possible repetitions) in a
    token list, including wrap-around occurrences.

    Parameters
    ----------
    pattern : list of str
        Ordered list of Roman-numeral chord tokens defining the phrase.
    tokens : list of str
        The full chord progression in Roman-numeral form.

    Returns
    -------
    list of list of int
        Each inner list contains the token indices of one match.

    Algorithm
    ---------
    Convert the token array to an indexed string
      '__0__iim__1__v7__2__iM'
    then duplicate it (to capture wrap-around patterns), build a regex
    that allows each phrase element to be repeated one or more times,
    and extract all matching index lists.
    """
    # Build the indexed string
    w = ''.join(f'__{i}__{tokens[i]}' for i in range(len(tokens)))
    w = w + w   # duplicate to capture wrap-arounds

    # Build the regex: each phrase token may repeat one or more times
    pat_regex = '(' + ''.join(
        r'(?:__[0-9]+__' + re.escape(p) + r')+' for p in pattern
    ) + ')'

    matches = re.findall(pat_regex, w)
    # Deduplicate (the doubled string can produce identical strings)
    unique = list(dict.fromkeys(matches))
    unique = _clean(unique)

    # Extract embedded indices from each matched string
    result = []
    for seq in unique:
        idx = [int(x) for x in re.findall(r'__([0-9]+)__', seq)]
        result.append(idx)
    return result


def _clean(seqs):
    """Remove any sequence that is a strict substring of another sequence.

    This handles the edge case where a wrap-around pattern produces a
    shorter duplicate that is fully contained within a longer match.
    """
    if not seqs:
        return seqs
    bad = None
    for k, sk in enumerate(seqs):
        for n, sn in enumerate(seqs):
            if k != n and sk in sn:
                bad = k
    if bad is not None:
        seqs = [s for i, s in enumerate(seqs) if i != bad]
    return seqs


def _absorb_repeats(chords, flags, marks):
    """Extend flags/marks across neighbouring repeated chords.

    If two adjacent chords are identical but only one is flagged, the
    flag is extended to the other, and the marks array is updated
    accordingly.

    Parameters
    ----------
    chords, flags, marks : list
        Parallel arrays of equal length.

    Returns
    -------
    flags, marks : list
        Updated arrays.
    """
    n = len(chords)
    # Backwards pass
    for i in range(n - 2, 0, -1):
        if flags[i - 1] == 0 and flags[i] != 0 and chords[i - 1] == chords[i]:
            flags[i - 1] = flags[i]
            marks[i - 1] = marks[i]
            marks[i] = 0
    # Forwards pass
    for i in range(1, n - 2):
        if flags[i] != 0 and flags[i + 1] == 0 and chords[i] == chords[i + 1]:
            flags[i + 1] = flags[i]
            marks[i + 1] = marks[i]
            marks[i] = 0
    return flags, marks


# ---------------------------------------------------------------------------
# Merge helpers
# ---------------------------------------------------------------------------

def _merge_cadence(flags1, marks1, flags2, marks2):
    """Merge a second set of flags/marks into the first.

    For each bracketed group in flags2/marks2 (delimited by +1 and -1
    in marks2), the group is only merged if all positions in flags1
    within that group are still zero.  Wrap-around groups are handled
    specially: if the group is already (partially) claimed in flags1 it
    is zeroed out from flags2 before the addition.

    Returns
    -------
    flags1, marks1 : list
        Updated merged arrays.
    """
    n = len(flags1)
    enc_l = [i for i, m in enumerate(marks2) if m == 1]
    enc_r = [i for i, m in enumerate(marks2) if m == -1]

    # Handle wrap-around: enc_r[0] < enc_l[0]
    if enc_r and enc_l and enc_r[0] < enc_l[0]:
        clump = list(range(enc_l[-1], n)) + list(range(0, enc_r[0] + 1))
        occupied = any(flags1[k] != 0 for k in clump)
        if occupied:
            for i in clump:
                flags2[i] = 0
                marks2[i] = 0
        enc_r = enc_r[1:]
        enc_l = enc_l[:-1]

    for i in range(len(enc_l)):
        clump = list(range(enc_l[i], enc_r[i] + 1))
        occupied = any(flags1[k] != 0 for k in clump)
        if occupied:
            for j in clump:
                flags2[j] = 0
                marks2[j] = 0

    for k in range(n):
        flags1[k] += flags2[k]
        marks1[k] += marks2[k]
    return flags1, marks1


# ---------------------------------------------------------------------------
# Individual phrase-flagging functions
# ---------------------------------------------------------------------------

def _apply_pattern_dict(chords, patterns):
    """Generic helper: apply a dict of {phrase_string: flag_value} patterns.

    For each matched phrase, all indices receive the flag value, and the
    first / last index receive marks +1 / -1.

    Returns
    -------
    flags, marks : list
    """
    flags = [0] * len(chords)
    marks = [0] * len(chords)
    for key, value in patterns.items():
        phrase = key.split('-')
        for idx_list in _match_chord_phrase(phrase, chords):
            for i in idx_list:
                flags[i] = value
            marks[idx_list[0]] = 1
            marks[idx_list[-1]] = -1
    return flags, marks


def flag_cadence(chords):
    """Flag major II-V-I cadences in all 12 keys.

    Codes:  30 (iim-v7-iM)  through  35 (biim-bv7-viiM)
            and their negatives for the other six keys.
    """
    p251 = {
        'bvim-bii7-bvM': -36, 'biiim-bvi7-biiM': -35, 'bviim-biii7-bviM': -34,
        'ivm-bvii7-biiiM': -33, 'im-iv7-bviiM': -32, 'vm-i7-ivM': -31,
        'iim-v7-iM': 30, 'vim-ii7-vM': 31, 'iiim-vi7-iiM': 32,
        'viim-iii7-viM': 33, 'bvm-vii7-iiiM': 34, 'biim-bv7-viiM': 35,
    }
    return _apply_pattern_dict(chords, p251)


def flag_minor_cadence(chords):
    """Flag minor II-V-I cadences in all 12 keys.

    Codes:  40 (viih-iii7-vim)  through  45 and their negatives.
    """
    pm251 = {
        'ivh-bvii7-biiim': -46, 'ih-iv7-bviim': -45, 'vh-i7-ivm': -44,
        'iih-v7-im': -43, 'vih-ii7-vm': -42, 'iiih-vi7-iim': -41,
        'viih-iii7-vim': 40, 'bvh-vii7-iiim': 41, 'biih-bv7-viim': 42,
        'bvih-bii7-bvm': 43, 'biiih-bvi7-biim': 44, 'bviih-biii7-bvim': 45,
    }
    return _apply_pattern_dict(chords, pm251)


def flag_2b21(chords):
    """Flag major II-bII-I (tritone-sub) cadences in all 12 keys.

    Codes:  130 (iim-bii7-iM)  through  135 and their negatives.
    For the dominant chord in each pattern, flag 5 (tritone sub) is used
    instead of the cadence code.
    """
    p2b21 = {
        'bvim-v7-bvM': -136, 'biiim-ii7-biiM': -135, 'bviim-vi7-bviM': -134,
        'ivm-iii7-biiiM': -133, 'im-vii7-bviiM': -132, 'vm-bv7-ivM': -131,
        'iim-bii7-iM': 130, 'vim-bvi7-vM': 131, 'iiim-biii7-iiM': 132,
        'viim-bvii7-viM': 133, 'bvm-iv7-iiiM': 134, 'biim-i7-viiM': 135,
    }
    flags = [0] * len(chords)
    marks = [0] * len(chords)
    for key, value in p2b21.items():
        phrase = key.split('-')
        for idx_list in _match_chord_phrase(phrase, chords):
            for i in idx_list:
                # Dominant chord in pattern gets tritone-sub flag (5)
                flags[i] = 5 if re.search(r'7', chords[i]) else value
            marks[idx_list[0]] = 1
            marks[idx_list[-1]] = -1
    return flags, marks


def flag_minor_2b21(chords):
    """Flag minor II-bII-I cadences in all 12 keys.

    Codes:  140 through 145 and their negatives.
    Dominant chord positions receive flag 5 (tritone sub).
    """
    pm2b21 = {
        'ivh-iii7-biiim': -146, 'ih-vii7-bviim': -145, 'vh-bv7-ivm': -144,
        'iih-bii7-im': -143, 'vih-bvi7-vm': -142, 'iiih-biii7-iim': -141,
        'viih-bvii7-vim': 140, 'bvh-iv7-iiim': 141, 'biih-i7-viim': 142,
        'bvih-v7-bvm': 143, 'biiih-ii7-biim': 144, 'bviih-vi7-bvim': 145,
    }
    flags = [0] * len(chords)
    marks = [0] * len(chords)
    for key, value in pm2b21.items():
        phrase = key.split('-')
        for idx_list in _match_chord_phrase(phrase, chords):
            for i in idx_list:
                flags[i] = 5 if re.search(r'7', chords[i]) else value
            marks[idx_list[0]] = 1
            marks[idx_list[-1]] = -1
    return flags, marks


def flag_25s(chords):
    """Flag major II-V two-chord phrases in all 12 keys.

    Codes:  10 (iim-v7)  through  15 and their negatives.
    """
    p25 = {
        'bvim-bii7': -16, 'biiim-bvi7': -15, 'bviim-biii7': -14,
        'ivm-bvii7': -13, 'im-iv7': -12, 'vm-i7': -11,
        'iim-v7': 10, 'vim-ii7': 11, 'iiim-vi7': 12,
        'viim-iii7': 13, 'bvm-vii7': 14, 'biim-bv7': 15,
    }
    return _apply_pattern_dict(chords, p25)


def flag_m25s(chords):
    """Flag minor II-V two-chord phrases in all 12 keys.

    Codes:  20/21...25 and their negatives.
    """
    pm25 = {
        'ivh-bvii7': -26, 'ih-iv7': -25, 'vh-i7': -24,
        'iih-v7': -23, 'vih-ii7': -22, 'iiih-vi7': -21,
        'viih-iii7': 20, 'bvh-vii7': 21, 'biih-bv7': 22,
        'bvih-bii7': 23, 'biiih-bvi7': 24, 'bviih-biii7': 25,
    }
    return _apply_pattern_dict(chords, pm25)


def flag_2b2s(chords):
    """Flag major II-bII two-chord (tritone approach) phrases in all 12 keys.

    Codes:  110 through 115 and their negatives.
    """
    p2b2 = {
        'bvim-v7': -116, 'biiim-ii7': -115, 'bviim-vi7': -114,
        'ivm-iii7': -113, 'im-vii7': -112, 'vm-bv7': -111,
        'iim-bii7': 110, 'vim-bvi7': 111, 'iiim-biii7': 112,
        'viim-bvii7': 113, 'bvm-iv7': 114, 'biim-i7': 115,
    }
    return _apply_pattern_dict(chords, p2b2)


def flag_m2b2s(chords):
    """Flag minor II-bII two-chord phrases in all 12 keys.

    Codes:  120 through 125 and their negatives.
    """
    pm2b2 = {
        'ivh-iii7': -126, 'ih-vii7': -125, 'vh-bv7': -124,
        'iih-bii7': -123, 'vih-bvi7': -122, 'iiih-biii7': -121,
        'viih-bvii7': 120, 'bvh-iv7': 121, 'biih-i7': 122,
        'bvih-v7': 123, 'biiih-ii7': 124, 'bviih-vi7': 125,
    }
    return _apply_pattern_dict(chords, pm2b2)


def flag_51s(chords):
    """Flag dominant-to-major (V-I without preceding II) phrases in all 12 keys.

    Codes:  50 (v7-iM)  through  55 and their negatives.
    """
    p51 = {
        'bii7-bvM': -56, 'bvi7-biiM': -55, 'biii7-bviM': -54,
        'bvii7-biiiM': -53, 'iv7-bviiM': -52, 'i7-ivM': -51,
        'v7-iM': 50, 'ii7-vM': 51, 'vi7-iiM': 52,
        'iii7-viM': 53, 'vii7-iiiM': 54, 'bv7-viiM': 55,
    }
    return _apply_pattern_dict(chords, p51)


def flag_b21s(chords):
    """Flag bII-I (Neapolitan cadence) phrases in all 12 keys.

    Codes:  150 (bii7-iM)  through  155 and their negatives.
    """
    pb21 = {
        'v7-bvM': -156, 'ii7-biiM': -155, 'vi7-bviM': -154,
        'iii7-biiiM': -153, 'vii7-bviiM': -152, 'bv7-ivM': -151,
        'bii7-iM': 150, 'bvi7-vM': 151, 'biii7-iiM': 152,
        'bvii7-viM': 153, 'iv7-iiiM': 154, 'i7-viiM': 155,
    }
    return _apply_pattern_dict(chords, pb21)


def flag_secondary_doms(chords):
    """Flag secondary dominant chords (dominant moving a fifth or semitone).

    The dominant chord in each matched pair receives flag 3.
    Only the dominant-to-major patterns are active (the commented-out
    dominant-to-minor section from the Perl original is preserved but
    inactive here as well).
    """
    # Only V7->I (major) patterns are enabled; V7->i patterns were
    # commented out in the original.
    p2nd_doms = [
        'i7-ivM', 'bii7-bvM', 'ii7-vM', 'biii7-bviM', 'iii7-viM',
        'iv7-bviiM', 'bv7-viiM', 'v7-iM', 'bvi7-biiM', 'vi7-iiM',
        'bvii7-biiiM', 'vii7-iiiM',

        'i7-ivm', 'bii7-bvm', 'ii7-vm', 'biii7-bvim', 'iii7-vim',
        'iv7-bviim', 'bv7-viim', 'v7-im', 'bvi7-biim', 'vi7-iim',
        'bvii7-biiim', 'vii7-iiim',
    ]
    flags = [0] * len(chords)
    marks = [0] * len(chords)
    for phrase_str in p2nd_doms:
        phrase = phrase_str.split('-')
        for idx_list in _match_chord_phrase(phrase, chords):
            for i in idx_list:
                if re.search(r'7', chords[i]):
                    flags[i] = 3
    return flags, marks


def flag_dim_doms_new(chords):
    """Flag all diminished chords (flag 4), regardless of context.

    Each of the twelve diminished-chord Roman-numeral forms is matched
    anywhere in the progression.
    """
    pdim_doms = [
        'io', 'biio', 'iio', 'biiio', 'iiio', 'ivo',
        'bvo', 'vo', 'bvio', 'vio', 'bviio', 'viio'
    ]
    flags = [0] * len(chords)
    marks = [0] * len(chords)
    for phrase_str in pdim_doms:
        phrase = [phrase_str]
        for idx_list in _match_chord_phrase(phrase, chords):
            for i in idx_list:
                flags[i] = 4
    return flags, marks


def flag_chain_of_doms(chords):
    """Flag chains and interpolated chains of dominant chords.

    Interpolated chain patterns receive flag 6 (for minor-quality tokens)
    or 7 (for dominant-quality tokens).  Direct chain-of-dominants
    patterns receive flag 2.
    """
    # Interpolated chains (minor chord between two dominants)
    pint_doms = [
        'vm-i7-im-iv7',    'bvim-bii7-biim-bv7',  'vim-ii7-iim-v7',
        'bviim-biii7-biiim-bvi7', 'viim-iii7-iiim-vi7', 'im-iv7-ivm-bvii7',
        'biim-bv7-bvm-vii7', 'iim-v7-vm-i7',        'biiim-bvi7-bvim-bii7',
        'iiim-vi7-vim-ii7',  'ivm-bvii7-bviim-biii7', 'bvm-vii7-viim-iii7',
        'vm-i7-ivm-bvii7',  'bvim-bii7-vm-i7',     'vim-ii7-bvim-bii7',
        'bviim-biii7-vim-ii7', 'viim-iii7-bviim-biii7', 'im-iv7-viim-iii7',
        'biim-bv7-im-iv7',  'iim-v7-biim-bv7',     'biiim-bvi7-iim-v7',
        'iiim-vi7-biiim-bvi7', 'ivm-bvii7-iiim-vi7', 'bvm-vii7-ivm-bvii7',
    ]
    # Mid-interpolated chains
    pmid_int_doms = [
        'i7-im-iv7',   'bii7-biim-bv7',  'ii7-iim-v7',
        'biii7-biiim-bvi7', 'iii7-iiim-vi7', 'iv7-ivm-bvii7',
        'bv7-bvm-vii7', 'v7-vm-i7',      'bvi7-bvim-bii7',
        'vi7-vim-ii7',  'bvii7-bviim-biii7', 'vii7-viim-iii7',
        'i7-ivm-bvii7', 'bii7-vm-i7',    'ii7-bvim-bii7',
        'biii7-vim-ii7', 'iii7-bviim-biii7', 'iv7-viim-iii7',
        'bv7-im-iv7',  'v7-biim-bv7',   'bvi7-iim-v7',
        'vi7-biiim-bvi7', 'bvii7-iiim-vi7', 'vii7-ivm-bvii7',
    ]
    # Leading interpolated chains
    plead_int_doms = [
        'vm-i7-iv7',   'bvim-bii7-bv7',  'vim-ii7-v7',
        'bviim-biii7-bvi7', 'viim-iii7-vi7', 'im-iv7-bvii7',
        'biim-bv7-vii7', 'iim-v7-i7',     'biiim-bvi7-bii7',
        'iiim-vi7-ii7',  'ivm-bvii7-biii7', 'bvm-vii7-iii7',
        'vm-i7-bvii7',  'bvim-bii7-i7',   'vim-ii7-bii7',
        'bviim-biii7-ii7', 'viim-iii7-biii7', 'im-iv7-iii7',
        'biim-bv7-iv7', 'iim-v7-bv7',    'biiim-bvi7-v7',
        'iiim-vi7-bvi7', 'ivm-bvii7-vi7', 'bvm-vii7-bvii7',
    ]
    # Direct chains of dominants
    pchain_doms = [
        'i7-iv7',  'bii7-bv7', 'ii7-v7',
        'biii7-bvi7', 'iii7-vi7', 'iv7-bvii7',
        'bv7-vii7', 'v7-i7',  'bvi7-bii7',
        'vi7-ii7',  'bvii7-biii7', 'vii7-iii7',
        'i7-vii7',  'bii7-i7', 'ii7-bii7',
        'biii7-ii7', 'iii7-biii7', 'iv7-iii7',
        'bv7-iv7',  'v7-bv7',  'bvi7-v7',
        'vi7-bvi7', 'bvii7-vi7', 'vii7-bvii7',
    ]

    flags = [0] * len(chords)

    def _apply_interp(patterns):
        for phrase_str in patterns:
            phrase = phrase_str.split('-')
            for idx_list in _match_chord_phrase(phrase, chords):
                for i in idx_list:
                    flags[i] = 6 if re.search(r'm', chords[i]) else 7

    _apply_interp(pint_doms)
    _apply_interp(pmid_int_doms)
    _apply_interp(plead_int_doms)

    for phrase_str in pchain_doms:
        phrase = phrase_str.split('-')
        for idx_list in _match_chord_phrase(phrase, chords):
            for i in idx_list:
                flags[i] = 2

    return flags


def flag_turnarounds(chords):
    """Flag turnaround patterns (interpolated dominant chains).

    Returns only a flags array (no marks).
    """
    # Big turnarounds (4-chord)
    pbig_turn = [
        'iim-v7-im-iv7',     'biiim-bvi7-biim-bv7',   'iiim-vi7-iim-v7',
        'ivm-bvii7-biiim-bvi7', 'bvm-vii7-iiim-vi7',   'vm-i7-ivm-bvii7',
        'bvim-bii7-bvm-vii7', 'vim-ii7-vm-i7',          'bviim-biii7-bvim-bii7',
        'viim-iii7-vim-ii7',  'im-iv7-bviim-biii7',     'biim-bv7-viim-iii7',
    ]
    # Medium turnarounds (3-chord)
    pmed_turn = [
        'v7-im-iv7',    'bvi7-biim-bv7',  'vi7-iim-v7',
        'bvii7-biiim-bvi7', 'vii7-iiim-vi7', 'i7-ivm-bvii7',
        'bii7-bvm-vii7', 'ii7-vm-i7',     'biii7-bvim-bii7',
        'iii7-vim-ii7',  'iv7-bviim-biii7', 'bv7-viim-iii7',
    ]
    # Small turnarounds (2-chord)
    psmall_turn = [
        'im-iv7',   'biim-bv7', 'iim-v7',
        'biiim-bvi7', 'iiim-vi7', 'ivm-bvii7',
        'bvm-vii7', 'vm-i7',   'bvim-bii7',
        'vim-ii7',  'bviim-biii7', 'viim-iii7',
    ]

    flags = [0] * len(chords)

    # NOTE: the Perl original references @pint_doms, @pmid_int_doms,
    # @plead_int_doms, and @pchain_doms from flag_chain_of_doms here
    # (they are declared in the same lexical scope in Perl).  Those same
    # lists are re-specified below for clarity and self-containment.

    pint_doms = [
        'vm-i7-im-iv7', 'bvim-bii7-biim-bv7', 'vim-ii7-iim-v7',
        'bviim-biii7-biiim-bvi7', 'viim-iii7-iiim-vi7', 'im-iv7-ivm-bvii7',
        'biim-bv7-bvm-vii7', 'iim-v7-vm-i7', 'biiim-bvi7-bvim-bii7',
        'iiim-vi7-vim-ii7', 'ivm-bvii7-bviim-biii7', 'bvm-vii7-viim-iii7',
        'vm-i7-ivm-bvii7', 'bvim-bii7-vm-i7', 'vim-ii7-bvim-bii7',
        'bviim-biii7-vim-ii7', 'viim-iii7-bviim-biii7', 'im-iv7-viim-iii7',
        'biim-bv7-im-iv7', 'iim-v7-biim-bv7', 'biiim-bvi7-iim-v7',
        'iiim-vi7-biiim-bvi7', 'ivm-bvii7-iiim-vi7', 'bvm-vii7-ivm-bvii7',
    ]
    pmid_int_doms = [
        'i7-im-iv7', 'bii7-biim-bv7', 'ii7-iim-v7',
        'biii7-biiim-bvi7', 'iii7-iiim-vi7', 'iv7-ivm-bvii7',
        'bv7-bvm-vii7', 'v7-vm-i7', 'bvi7-bvim-bii7',
        'vi7-vim-ii7', 'bvii7-bviim-biii7', 'vii7-viim-iii7',
        'i7-ivm-bvii7', 'bii7-vm-i7', 'ii7-bvim-bii7',
        'biii7-vim-ii7', 'iii7-bviim-biii7', 'iv7-viim-iii7',
        'bv7-im-iv7', 'v7-biim-bv7', 'bvi7-iim-v7',
        'vi7-biiim-bvi7', 'bvii7-iiim-vi7', 'vii7-ivm-bvii7',
    ]
    plead_int_doms = [
        'vm-i7-iv7', 'bvim-bii7-bv7', 'vim-ii7-v7',
        'bviim-biii7-bvi7', 'viim-iii7-vi7', 'im-iv7-bvii7',
        'biim-bv7-vii7', 'iim-v7-i7', 'biiim-bvi7-bii7',
        'iiim-vi7-ii7', 'ivm-bvii7-biii7', 'bvm-vii7-iii7',
        'vm-i7-bvii7', 'bvim-bii7-i7', 'vim-ii7-bii7',
        'bviim-biii7-ii7', 'viim-iii7-biii7', 'im-iv7-iii7',
        'biim-bv7-iv7', 'iim-v7-bv7', 'biiim-bvi7-v7',
        'iiim-vi7-bvi7', 'ivm-bvii7-vi7', 'bvm-vii7-bvii7',
    ]
    pchain_doms = [
        'i7-iv7', 'bii7-bv7', 'ii7-v7',
        'biii7-bvi7', 'iii7-vi7', 'iv7-bvii7',
        'bv7-vii7', 'v7-i7', 'bvi7-bii7',
        'vi7-ii7', 'bvii7-biii7', 'vii7-iii7',
        'i7-vii7', 'bii7-i7', 'ii7-bii7',
        'biii7-ii7', 'iii7-biii7', 'iv7-iii7',
        'bv7-iv7', 'v7-bv7', 'bvi7-v7',
        'vi7-bvi7', 'bvii7-vi7', 'vii7-bvii7',
    ]

    def _apply_interp(patterns):
        for phrase_str in patterns:
            phrase = phrase_str.split('-')
            for idx_list in _match_chord_phrase(phrase, chords):
                for i in idx_list:
                    flags[i] = 6 if re.search(r'm', chords[i]) else 7

    _apply_interp(pint_doms)
    _apply_interp(pmid_int_doms)
    _apply_interp(plead_int_doms)

    for phrase_str in pchain_doms:
        phrase = phrase_str.split('-')
        for idx_list in _match_chord_phrase(phrase, chords):
            for i in idx_list:
                flags[i] = 2

    return flags


def _flag_parallel_mode(chords, mode_chords, flag_value):
    """Generic helper for parallel-mode flagging.

    Each chord listed in mode_chords that appears in the progression is
    given flag_value.
    """
    flags = [0] * len(chords)
    marks = [0] * len(chords)
    for phrase_str in mode_chords:
        phrase = [phrase_str]
        for idx_list in _match_chord_phrase(phrase, chords):
            for i in idx_list:
                flags[i] = flag_value
    return flags, marks


def flag_mainkey(chords):
    """Flag chords that are diatonic to the reference major key (flag 1)."""
    mainkey = ['iM', 'iim', 'iiim', 'ivM', 'v7', 'vim', 'viih']
    return _flag_parallel_mode(chords, mainkey, 1)


def flag_pminor(chords):
    """Flag chords borrowed from the parallel natural minor (flag -1)."""
    pminorkey = ['im', 'iih', 'biiiM', 'ivm', 'vm', 'bviM', 'bvii7']
    return _flag_parallel_mode(chords, pminorkey, -1)


def flag_pLydian(chords):
    """Flag chords borrowed from the parallel Lydian mode (flag -2)."""
    pLydiankey = ['iM', 'ii7', 'iiim', 'bvh', 'vM', 'vim', 'viim']
    return _flag_parallel_mode(chords, pLydiankey, -2)


def flag_pPhrygian(chords):
    """Flag chords borrowed from the parallel Phrygian mode (flag -3)."""
    pPhrygiankey = ['im', 'biiM', 'biii7', 'ivm', 'vh', 'bviM', 'bviim']
    return _flag_parallel_mode(chords, pPhrygiankey, -3)


def flag_pDorian(chords):
    """Flag chords borrowed from the parallel Dorian mode (flag -4)."""
    pDoriankey = ['im', 'iim', 'biiiM', 'iv7', 'vm', 'vih', 'bviiM']
    return _flag_parallel_mode(chords, pDoriankey, -4)


def flag_pMixolydian(chords):
    """Flag chords borrowed from the parallel Mixolydian mode (flag -5)."""
    pMixolydiankey = ['i7', 'iim', 'iiih', 'ivM', 'vm', 'vim', 'bviiM']
    return _flag_parallel_mode(chords, pMixolydiankey, -5)


def flag_pLocrian(chords):
    """Flag chords borrowed from the parallel Locrian mode (flag -6)."""
    pLocriankey = ['ih', 'biiM', 'biiim', 'ivm', 'bvM', 'bvi7', 'bviim']
    return _flag_parallel_mode(chords, pLocriankey, -6)


# ---------------------------------------------------------------------------
# Master flag_phrases function
# ---------------------------------------------------------------------------

def flag_phrases(roman, diagnose=False):
    """Compute harmonic-phrase flags and bracket marks for a Roman-numeral progression.

    This is the top-level flagging routine.  It calls each of the
    individual phrase detectors, then merges their results according to
    a strict priority order:

      1. Major 251 and 2b21 cadences (mutually exclusive; added together)
      2. Minor 251 cadences
      3. Minor 2b21 cadences
      4. Chains of dominants (collisions zeroed out; isolated doms zeroed)
      5. V-I (51) cadences
      6. bII-I (b21) cadences
      7. Secondary dominants
      8. Major 25 two-chord phrases
      9. Minor 25 two-chord phrases
     10. Major 2b2 two-chord phrases
     11. Minor 2b2 two-chord phrases
     12. Remaining main-key diatonic chords
     13. Parallel minor
     14. Parallel Lydian
     15. Parallel Phrygian
     16. Parallel Dorian
     17. Parallel Mixolydian
     18. Parallel Locrian
     19. Diminished dominants

    Parameters
    ----------
    roman : list of str
        Chord progression in Roman-numeral form.
    diagnose : bool
        If True, print a diagnostic table to stdout.

    Returns
    -------
    list
        Concatenation of flags (len N) then marks (len N), so the caller
        can split at index N.
    """
    N = len(roman)

    flags_cadence,       marks_cadence       = flag_cadence(roman)
    flags_minor_cadence, marks_minor_cadence = flag_minor_cadence(roman)
    flags_2b21,          marks_2b21          = flag_2b21(roman)
    flags_minor_2b21,    marks_minor_2b21    = flag_minor_2b21(roman)
    flags_25s,           marks_25s           = flag_25s(roman)
    flags_m25s,          marks_m25s          = flag_m25s(roman)
    flags_2b2s,          marks_2b2s          = flag_2b2s(roman)
    flags_m2b2s,         marks_m2b2s         = flag_m2b2s(roman)
    flags_b21s,          marks_b21s          = flag_b21s(roman)
    flags_51s,           marks_51s           = flag_51s(roman)
    flag_chains                              = flag_chain_of_doms(roman)
    flags_sec_dom,       marks_sec_dom       = flag_secondary_doms(roman)
    flags_mainkey,       marks_mainkey       = flag_mainkey(roman)
    flags_pminor,        marks_pminor        = flag_pminor(roman)
    flags_pLydian,       marks_pLydian       = flag_pLydian(roman)
    flags_pPhrygian,     marks_pPhrygian     = flag_pPhrygian(roman)
    flags_pDorian,       marks_pDorian       = flag_pDorian(roman)
    flags_pMixolydian,   marks_pMixolydian   = flag_pMixolydian(roman)
    flags_pLocrian,      marks_pLocrian      = flag_pLocrian(roman)
    flags_dimdoms,       marks_dimdoms       = flag_dim_doms_new(roman)
    flag_turnarounds_arr                     = flag_turnarounds(roman)

    # --- Merge major 251 and 2b21 (mutually exclusive; simply add) ---
    flags1 = [flags_cadence[k] + flags_2b21[k] for k in range(N)]
    marks1 = [marks_cadence[k] + marks_2b21[k] for k in range(N)]

    # --- Merge minor cadences ---
    flags1, marks1 = _merge_cadence(flags1, marks1, flags_minor_cadence, marks_minor_cadence)
    flags1, marks1 = _merge_cadence(flags1, marks1, flags_minor_2b21,    marks_minor_2b21)

    # --- Merge chains of dominants ---
    # Zero out any chain flags that coincide with already-placed cadence flags.
    # Also zero out isolated chain flags (not part of a true chain).
    taken = [i for i in range(N) if flags1[i] != 0]
    for i in taken:
        flag_chains[i] = 0

    # Zero isolated single-element occurrences (0-2-0, 0-6-0, 0-7-0, 0-6-7-0)
    chain_str = '-'.join(str(x) for x in flag_chains)
    chain_str = chain_str.replace('0-2-0', '0-0-0')
    chain_str = chain_str.replace('0-6-0', '0-0-0')
    chain_str = chain_str.replace('0-7-0', '0-0-0')
    chain_str = chain_str.replace('0-6-7-0', '0-0-0-0')
    flag_chains = [int(x) for x in chain_str.split('-')]

    for k in range(N):
        flags1[k] += flag_chains[k]

    # --- Merge 51s and b21s ---
    flags1, marks1 = _merge_cadence(flags1, marks1, flags_51s,  marks_51s)
    flags1, marks1 = _merge_cadence(flags1, marks1, flags_b21s, marks_b21s)

    # --- Secondary dominants (only where flags1 is still zero) ---
    for k in range(N):
        if flags1[k] == 0 and flags_sec_dom[k] != 0:
            flags1[k] = flags_sec_dom[k]

    # --- Merge 25 and 2b2 two-chord phrases ---
    flags1, marks1 = _merge_cadence(flags1, marks1, flags_25s,   marks_25s)
    flags1, marks1 = _merge_cadence(flags1, marks1, flags_m25s,  marks_m25s)
    flags1, marks1 = _merge_cadence(flags1, marks1, flags_2b2s,  marks_2b2s)
    flags1, marks1 = _merge_cadence(flags1, marks1, flags_m2b2s, marks_m2b2s)

    # --- Remaining main-key diatonic and parallel-mode chords ---
    for src in [flags_mainkey, flags_pminor, flags_pLydian,
                flags_pPhrygian, flags_pDorian, flags_pMixolydian,
                flags_pLocrian]:
        for k in range(N):
            if flags1[k] == 0 and src[k] != 0:
                flags1[k] = src[k]

    # --- Diminished dominants (lowest priority) ---
    for k in range(N):
        if flags1[k] == 0 and flags_dimdoms[k] != 0:
            flags1[k] = flags_dimdoms[k]

    # --- Optional diagnostic print ---
    if diagnose and diagnose != 'NA':
        print("\nmarks merged   251     m251    2b21   chain     25      51    "
              "2nddom dimdom   main+pmodes        | (k, sym)")
        print("-" * 114)
        for k in range(N):
            f_modes = [flags_mainkey[k], flags_pDorian[k], flags_pPhrygian[k],
                       flags_pLydian[k], flags_pMixolydian[k], flags_pminor[k],
                       flags_pLocrian[k]]
            print(f"{marks1[k]}\t{flags1[k]}\t{flags_cadence[k]}\t"
                  f"{flags_minor_cadence[k]}\t{flags_2b21[k]}\t"
                  f"{flag_chains[k]}\t{flags_25s[k]}\t{flags_51s[k]}\t"
                  f"{flags_sec_dom[k]}\t{flags_dimdoms[k]}  "
                  f"({f_modes})\t| ({k}, {roman[k]})")

    return flags1 + marks1


# ---------------------------------------------------------------------------
# Key estimation
# ---------------------------------------------------------------------------

def estimatekey(bpm, normalform):
    """Estimate the reference major key from a normalised chord progression.

    Each chord is classified and its root assigned to the major scales it
    could belong to.  Chords are weighted by their duration (beats per
    measure divided by the number of chords in the measure).

    Parameters
    ----------
    bpm : int
        Beats per measure (time-signature numerator).
    normalform : list of str
        Full progression including '|' bar separators.

    Returns
    -------
    dict
        Mapping of major-key name -> accumulated weight.
    """
    # Major chord: can come from two major scales
    major = {
        'C': 'C.G', 'F': 'F.C', 'Bb': 'Bb.F', 'Eb': 'Eb.Bb', 'Ab': 'Ab.Eb',
        'Db': 'Db.Ab', 'Gb': 'Gb.Db', 'B': 'B.Gb', 'E': 'E.B', 'A': 'A.E',
        'D': 'D.A', 'G': 'G.D',
    }
    # Minor chord: can come from three major scales
    minor = {
        'C': 'Bb.Ab.Eb', 'F': 'Eb.Db.Ab', 'Bb': 'Ab.Gb.Db', 'Eb': 'Db.B.Gb',
        'Ab': 'Gb.E.B',  'Db': 'B.A.E',   'Gb': 'E.D.A',    'B': 'A.G.D',
        'E': 'D.C.G',    'A': 'G.F.C',    'D': 'C.Bb.F',     'G': 'F.Eb.Bb',
    }
    # Dominant seventh: one major scale
    seven = {
        'C': 'F', 'F': 'Bb', 'Bb': 'Eb', 'Eb': 'Ab', 'Ab': 'Db', 'Db': 'Gb',
        'Gb': 'B', 'B': 'E', 'E': 'A',   'A': 'D',   'D': 'G',   'G': 'C',
    }
    # Half-diminished (m7b5): one major scale
    half = {
        'C': 'Db', 'F': 'Gb', 'Bb': 'B',  'Eb': 'E',  'Ab': 'A',  'Db': 'D',
        'Gb': 'G', 'B': 'C',  'E': 'F',   'A': 'Bb',  'D': 'Eb',  'G': 'Ab',
    }
    # Power chord (5): six major scales
    five = {
        'C': 'C.Eb.F.G.Ab.Bb',   'F': 'C.Db.Eb.F.Ab.Bb',
        'Bb': 'Db.Eb.F.Gb.Ab.Bb', 'Eb': 'Db.Eb.Gb.Ab.Bb.B',
        'Ab': 'Db.Eb.E.Gb.Ab.B',  'Db': 'Db.E.Gb.Ab.A.B',
        'Gb': 'Db.D.E.Gb.A.B',    'B': 'D.E.Gb.G.A.B',
        'E': 'C.D.E.G.A.B',       'A': 'C.D.E.F.G.A',
        'D': 'C.D.F.G.A.Bb',      'G': 'C.D.Eb.F.G.Bb',
    }

    chords = [p for p in normalform if p != '|']

    # Build per-chord weights based on the number of chords per measure
    cpm = []
    cnt = 0
    for p in normalform:
        if p != '|':
            cnt += 1
        else:
            cpm.append(cnt)
            cnt = 0
    wgts = []
    for b in cpm:
        if b > 0:
            wgts.extend([bpm / b] * b)

    majpop = {}
    for chord, wgt in zip(chords, wgts):
        cls = _chordclass(chord)
        root = _getroot(chord)
        scales = []
        if cls == '7':
            scales = [seven.get(root, '')]
        elif cls == 'M':
            scales = major.get(root, '').split('.')
        elif cls == 'm':
            scales = minor.get(root, '').split('.')
        elif cls == 'h':
            scales = [half.get(root, '')]
        elif cls == '5':
            scales = five.get(root, '').split('.')
        for s in scales:
            if s:
                majpop[s] = majpop.get(s, 0) + wgt

    return majpop


# ---------------------------------------------------------------------------
# Public API functions
# ---------------------------------------------------------------------------

def getsong(filename):
    """Read and parse a song file in the iRealPro/LeadSheet (.ls) format.

    The file format is expected to have key=value header lines followed
    by chord progression lines delimited with '|' characters.

    Parameters
    ----------
    filename : str
        Path to the song file.

    Returns
    -------
    tuple
        (title, composer, dbkey, truekey, bpm, btyp, Nbars, *progression)
        where *progression is the flat list of chords and '|' separators.
    """
    title = composer = dbkey = truekey = bpm = btyp = Nbars = None
    progression = []

    with open(filename, 'r', encoding='utf-8') as fh:
        for line in fh:
            if '|' in line:
                parts = line.strip().split()
                progression.extend(parts)
            elif line.startswith('TimeSig'):
                m = re.match(r'TimeSig\s*=\s*(\d+)\s+(\d+)', line)
                if m:
                    bpm, btyp = int(m.group(1)), int(m.group(2))
            elif line.startswith('ComposedBy'):
                m = re.match(r'ComposedBy\s*=\s*(.*)', line)
                if m:
                    composer = m.group(1).strip()
            elif line.startswith('DBKeySig'):
                m = re.match(r'DBKeySig\s*=\s*(.*)', line)
                if m:
                    dbkey = m.group(1).strip()
            elif 'Title' in line:
                m = re.match(r'Title\s*=\s*(.*)', line)
                if m:
                    title = m.group(1).strip()
            elif line.startswith('True Key'):
                m = re.match(r'True Key\s*=\s*(.*)', line)
                if m:
                    truekey = m.group(1).strip()
            elif line.startswith('Bars'):
                m = re.match(r'Bars\s*=\s*(\d+)', line)
                if m:
                    Nbars = int(m.group(1))

    # Prepend a space to the first chord (preserves original Perl hack)
    if progression:
        progression[0] = ' ' + progression[0]

    return (title, composer, dbkey, truekey, bpm, btyp, Nbars) + tuple(progression)


def progNormalize(progression):
    """Normalise chord names and resolve harmonically ambiguous chord types.

    Steps
    -----
    1. Convert all chord roots to canonical enharmonic form (sharps -> flats).
    2. Convert slash chords that function as sus chords to their sus equivalents.
    3. Convert major triads that function as dominant sevenths.
    4. Convert sus chords to 7 or m7 (etc.) based on the following chord.
    5. Propagate flags to repeated neighbouring chords.

    Parameters
    ----------
    progression : list of str
        Raw chord progression including '|' bar separators.

    Returns
    -------
    list of str
        Normalised progression with the same '|' structure.
    """
    chords_idx = [i for i, p in enumerate(progression) if p != '|']
    chords = [progression[i] for i in chords_idx]
    prognorm = list(progression)
    mrk = [0] * len(chords)

    # --- Step 1: enharmonic normalisation ---
    normalform = [_chordnormalize(c.replace(' ', '')) for c in chords]

    # --- Lookup tables for chord conversion ---
    # Circle of 5ths (dominant motion, e.g. G -> C)
    co5 = {'C': 'F', 'Db': 'Gb', 'D': 'G', 'Eb': 'Ab', 'E': 'A',
           'F': 'Bb', 'Gb': 'B', 'G': 'C', 'Ab': 'Db', 'A': 'D',
           'Bb': 'Eb', 'B': 'E'}
    # Circle of 4ths (e.g. C -> G)
    co4 = {'F': 'C', 'Gb': 'Db', 'G': 'D', 'Ab': 'Eb', 'A': 'E',
           'Bb': 'F', 'B': 'Gb', 'C': 'G', 'Db': 'Ab', 'D': 'A',
           'Eb': 'Bb', 'E': 'B'}
    # Chromatic descent
    chrom = {'F': 'E', 'Gb': 'F', 'G': 'Gb', 'Ab': 'G', 'A': 'Ab',
             'Bb': 'A', 'B': 'Bb', 'C': 'B', 'Db': 'C', 'D': 'Db',
             'Eb': 'D', 'E': 'Eb'}
    # Major 9th (add9 resolution target)
    add9 = {'F': 'G', 'Gb': 'Ab', 'G': 'A', 'Ab': 'Bb', 'A': 'B',
            'Bb': 'C', 'B': 'Db', 'C': 'D', 'Db': 'Eb', 'D': 'E',
            'Eb': 'F', 'E': 'Gb'}

    # --- Step 2: slash-chord conversion ---
    slashconverted = []
    for i in range(len(normalform)):
        sub = normalform[i]
        c1 = normalform[i]
        c2 = normalform[(i + 1) % len(normalform)]
        if '/' in c1 and c1 != c2:
            parts = c1.split('/', 1)
            top, bottom = parts[0], parts[1]
            r1t = _getroot(top)
            r1b = _getroot(bottom)
            r2 = _getroot(c2)
            delta1 = _getinterval(r1t, r1b)
            delta2 = _getinterval(r1b, r2)
            cls1 = _chordclass(c1)
            cls2 = _chordclass(c2)
            pat = f'{cls1}-{delta1}-{delta2}-{cls2}'
            # Dm/G => G9sus4, etc.
            if pat in ('m-iv-iv-M', 'm-iv-0-7', 'm-iv-iv-m'):
                sub = r1b + '9sus4'
            elif pat in ('M-ii-iv-M', 'M-ii-0-7', 'M-ii-iv-m'):
                sub = r1b + '9sus4'
        slashconverted.append(sub)

    # --- Step 3: major-triad dominant conversion ---
    slashconverted.append(slashconverted[0])   # wrap-around
    majtriadconverted = []
    for i in range(len(slashconverted) - 1):
        c1 = slashconverted[i]
        c2 = slashconverted[i + 1]
        r1 = _getroot(c1)
        r2 = _getroot(c2)
        sub = c1
        m = re.match(r'[A-G]b?(.*)', c1)
        ext = m.group(1) if m else ''
        if ext == '':   # bare major triad
            if co5.get(r1) == r2:
                sub = r1 + '7'
                mrk[i] = 1
        majtriadconverted.append(sub)

    # --- Step 4: sus-chord conversion ---
    majtriadconverted.append(majtriadconverted[0])  # wrap-around
    susconverted = []
    for i in range(len(majtriadconverted) - 1):
        c1 = majtriadconverted[i]
        c2 = majtriadconverted[i + 1]
        r1 = _getroot(c1)
        r2 = _getroot(c2)
        sub = c1

        # sus2 => equivalent sus4 (e.g., Esus2 = B E F# = Bsus4)
        if re.search(r'sus2\b', c1):
            sub = co4.get(r1, r1) + 'sus4'
            mrk[i] = 1
            c1 = sub

        if re.search(r'sus4?b9', sub):
            if co5.get(r1) == r2:
                sub = r1 + '7b9'
            elif r1 == r2:
                sub = co4.get(r1, r1) + 'm7b5'
            elif chrom.get(r1) == r2:
                sub = r1 + '7b9'
            else:
                sub = r1 + '7b9'
            mrk[i] = 1
        elif re.search(r'sus2?4?', sub):
            if co5.get(r1) == r2:
                sub = r1 + '7'
            elif r1 == r2:
                sub = co4.get(r1, r1) + 'm7'
            elif chrom.get(r1) == r2:
                sub = r1 + '7'
            else:
                sub = r1 + '7'
            mrk[i] = 1
        susconverted.append(sub)

    # --- Step 5: backwards propagation of flags across repeated chords ---
    for i in range(len(susconverted) - 2, -1, -1):
        if (i + 1 < len(susconverted) and mrk[i + 1] == 1
                and susconverted[i] == susconverted[i + 1] and mrk[i] == 0):
            susconverted[i] = susconverted[i + 1]
            mrk[i] = 1

    # Inject normalised chords back into the progression (preserving '|')
    for idx, val in zip(chords_idx, susconverted):
        prognorm[idx] = val

    return prognorm


def compress(progression):
    """Remove consecutive duplicate entries (but preserve '|' separators).

    If the same chord appears in successive positions within the
    progression, only the first occurrence is kept.

    Parameters
    ----------
    progression : list of str

    Returns
    -------
    list of str
    """
    if not progression:
        return []
    compressed = [progression[0]]
    for item in progression[1:]:
        if item != compressed[-1]:
            compressed.append(item)
    return compressed


def map2roman(songkey, chords):
    """Convert a list of chords to Roman-numeral notation relative to songkey.

    Parameters
    ----------
    songkey : str
        The reference major key (e.g., 'D', 'Bb').
    chords : list of str
        Chords in concert-pitch notation.

    Returns
    -------
    list of str
        Roman-numeral equivalents (e.g., 'iim', 'v7', 'iM').
    """
    chordmap = {
        'C':  'C.Db.D.Eb.E.F.Gb.G.Ab.A.Bb.B',
        'F':  'F.Gb.G.Ab.A.Bb.B.C.Db.D.Eb.E',
        'Bb': 'Bb.B.C.Db.D.Eb.E.F.Gb.G.Ab.A',
        'Eb': 'Eb.E.F.Gb.G.Ab.A.Bb.B.C.Db.D',
        'Ab': 'Ab.A.Bb.B.C.Db.D.Eb.E.F.Gb.G',
        'Db': 'Db.D.Eb.E.F.Gb.G.Ab.A.Bb.B.C',
        'Gb': 'Gb.G.Ab.A.Bb.B.C.Db.D.Eb.E.F',
        'B':  'B.C.Db.D.Eb.E.F.Gb.G.Ab.A.Bb',
        'E':  'E.F.Gb.G.Ab.A.Bb.B.C.Db.D.Eb',
        'A':  'A.Bb.B.C.Db.D.Eb.E.F.Gb.G.Ab',
        'D':  'D.Eb.E.F.Gb.G.Ab.A.Bb.B.C.Db',
        'G':  'G.Ab.A.Bb.B.C.Db.D.Eb.E.F.Gb',
    }
    # [i, bii, ii, biii, iii, iv, bv, v, bvi, vi, bvii, vii]
    target = ['i', 'bii', 'ii', 'biii', 'iii', 'iv', 'bv', 'v', 'bvi', 'vi', 'bvii', 'vii']
    keyarray = chordmap[songkey].split('.')

    roman = []
    for c in chords:
        if 'NC' in c:
            roman.append(c)
        else:
            r = _getroot(c)
            t = _chordclass(c)
            idx = keyarray.index(r) if r in keyarray else 0
            roman.append(target[idx] + t)
    return roman


def transpose(songkey, transposekey, chords):
    """Transpose a chord progression from songkey to transposekey.

    Parameters
    ----------
    songkey : str
        Source key.
    transposekey : str
        Target key.
    chords : list of str
        Concert-pitch chord names.

    Returns
    -------
    list of str
        Transposed chord names.
    """
    chordmap = {
        'C':  'C.Db.D.Eb.E.F.Gb.G.Ab.A.Bb.B',
        'F':  'F.Gb.G.Ab.A.Bb.B.C.Db.D.Eb.E',
        'Bb': 'Bb.B.C.Db.D.Eb.E.F.Gb.G.Ab.A',
        'Eb': 'Eb.E.F.Gb.G.Ab.A.Bb.B.C.Db.D',
        'Ab': 'Ab.A.Bb.B.C.Db.D.Eb.E.F.Gb.G',
        'Db': 'Db.D.Eb.E.F.Gb.G.Ab.A.Bb.B.C',
        'Gb': 'Gb.G.Ab.A.Bb.B.C.Db.D.Eb.E.F',
        'B':  'B.C.Db.D.Eb.E.F.Gb.G.Ab.A.Bb',
        'E':  'E.F.Gb.G.Ab.A.Bb.B.C.Db.D.Eb',
        'A':  'A.Bb.B.C.Db.D.Eb.E.F.Gb.G.Ab',
        'D':  'D.Eb.E.F.Gb.G.Ab.A.Bb.B.C.Db',
        'G':  'G.Ab.A.Bb.B.C.Db.D.Eb.E.F.Gb',
    }
    key_array       = chordmap[songkey].split('.')
    transpose_array = chordmap[transposekey].split('.')

    result = []
    for c in chords:
        if 'NC' in c:
            result.append(c)
        elif '/' in c:
            parts = c.split('/', 1)
            r_top  = _getroot(parts[0])
            t_top  = _chordclass(parts[0])
            r_bass = _getroot(parts[1])
            i_top  = key_array.index(r_top)  if r_top  in key_array else 0
            i_bass = key_array.index(r_bass) if r_bass in key_array else 0
            result.append(transpose_array[i_top] + t_top + '/' + transpose_array[i_bass])
        else:
            r = _getroot(c)
            t = _chordclass(c)
            i = key_array.index(r) if r in key_array else 0
            result.append(transpose_array[i] + t)
    return result
