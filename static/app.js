/* =========================================================================
   JazzVis — Harmony Visualizer
   d3-driven controls that map onto JazzVis.py's command-line arguments:

     python JazzVis.py <song> [N] [K] [xT] [chords]

       N        -> Bars-per-row entry box  (#bpl-input)
       K        -> Tonal-center wheel      (#key-wheel)
       xT       -> Transpose wheel         (#transpose-wheel)
       chords   -> Display segmented control (#display-toggle)

   Every control change updates a shared `state` object and immediately
   re-runs JazzVis.py; changes accumulate (e.g. transposing to a key and
   then switching to chord names both apply together). The Reset button
   restores all defaults.

   Each response includes the tonal center JazzVis actually used (whether
   estimated automatically or chosen via -K), and the tonal-center wheel is
   always synced to it — so the wheel highlights the key in effect even in
   Auto mode.
   ========================================================================= */

(() => {

  // The 12 major keys JazzVis/ChordProgUtils understand, in circle-of-
  // fifths order, starting at 12 o'clock and proceeding clockwise.
  const CIRCLE_OF_FIFTHS = ['C', 'G', 'D', 'A', 'E', 'B', 'Gb', 'Db', 'Ab', 'Eb', 'Bb', 'F'];

  // Display labels (flat symbol for readability)
  const KEY_LABEL = {
    C: 'C', G: 'G', D: 'D', A: 'A', E: 'E', B: 'B',
    Gb: 'G♭', Db: 'D♭', Ab: 'A♭', Eb: 'E♭', Bb: 'B♭', F: 'F',
  };

  const DEFAULT_BPL = '8 8 8 8';

  // ----------------------------------------------------------------------
  // Circle-of-fifths key wheel
  // ----------------------------------------------------------------------
  //
  // Builds a 12-slice pie inside `container`. Slices are arranged clockwise
  // from 12 o'clock starting with C, matching the legend drawn by
  // JazzVis.py itself. The centre hub shows the auto-computed tonal center
  // so the user always knows where Reset returns to.

  function createKeyWheel(container, { hubLabel = '', allowDeselect = true,
                                        initial = null, onChange = () => {} }) {
    let currentHubLabel = hubLabel;
    const size  = 200;
    const r     = size / 2;
    const inner = r * 0.46;
    const outer = r * 0.94;

    const svg = d3.select(container)
      .append('svg')
      .attr('viewBox', `0 0 ${size} ${size}`)
      .attr('preserveAspectRatio', 'xMidYMid meet');

    const g = svg.append('g').attr('transform', `translate(${r},${r})`);

    const step = (2 * Math.PI) / 12;
    const data = CIRCLE_OF_FIFTHS.map((key, i) => ({
      key,
      startAngle: i * step - step / 2,
      endAngle:   i * step + step / 2,
    }));

    const arcGen = d3.arc()
      .innerRadius(inner)
      .outerRadius(outer)
      .padAngle(0.018)
      .cornerRadius(3);

    const labelArc = d3.arc()
      .innerRadius((inner + outer) / 2)
      .outerRadius((inner + outer) / 2);

    let selected = initial;

    const slices = g.selectAll('path.slice')
      .data(data)
      .join('path')
      .attr('class', 'slice')
      .attr('d', arcGen)
      .on('click', (event, d) => {
        if (allowDeselect && selected === d.key) {
          selected = null;
        } else {
          selected = d.key;
        }
        render();
        onChange(selected);
      });

    const labels = g.selectAll('text.slice-label')
      .data(data)
      .join('text')
      .attr('class', 'slice-label')
      .attr('transform', d => `translate(${labelArc.centroid(d)})`)
      .attr('text-anchor', 'middle')
      .attr('dy', '0.32em')
      .text(d => KEY_LABEL[d.key])
      .style('pointer-events', 'none');

    g.append('circle').attr('class', 'hub').attr('r', inner - 5);
    const hubText = g.append('text')
      .attr('class', 'hub-text')
      .attr('text-anchor', 'middle')
      .attr('dy', '0.32em')
      .style('pointer-events', 'none');

    function render() {
      slices.classed('selected', d => d.key === selected);
      labels.classed('on-selected', d => d.key === selected);
      hubText.text(currentHubLabel);
    }
    render();

    return {
      get: () => selected,
      set: (key) => { selected = key; render(); },
      setHubLabel: (label) => { currentHubLabel = label; render(); },
    };
  }

  // ----------------------------------------------------------------------
  // Wire everything up once the DOM is ready
  // ----------------------------------------------------------------------

  document.addEventListener('DOMContentLoaded', () => {

    // Shared state, mirrored directly onto JazzVis.py's CLI arguments.
    // Changes to any control update this object and trigger generate(),
    // so adjustments accumulate (e.g. transpose + chord-name display).
    const state = {
      song: null,
      key: null,            // null = Auto (omit K)
      transpose: false,
      transposeKey: 'C',
      display: 'symbols',
      bpl: '8-8-8-8',        // dash-joined, as JazzVis.py's N argument expects
    };

    const statusMsg     = document.getElementById('status-msg');
    const chartFrame    = document.getElementById('chart-frame');
    const downloadBtn   = document.getElementById('download-btn');

    function setStatus(text, kind) {
      statusMsg.textContent = text;
      statusMsg.className = `status ${kind || ''}`.trim();
    }

    // --- Download ------------------------------------------------------------
    // Each successful response carries the chart as a data URL plus a
    // suggested filename; nothing is saved on the server, so "downloading"
    // just means handing that data URL to the browser as a file.
    let currentChart = null;

    downloadBtn.addEventListener('click', () => {
      if (!currentChart) return;
      const a = document.createElement('a');
      a.href = currentChart.url;
      a.download = currentChart.filename || 'chart.png';
      document.body.appendChild(a);
      a.click();
      a.remove();
    });

    // --- Generation, with stale-response protection -----------------------
    let requestSeq = 0;

    function generate() {
      if (!state.song) return;

      const seq = ++requestSeq;
      const payload = {
        song: state.song,
        bpl: state.bpl,
        key: state.key || '',
        transpose: state.transpose,
        transposeKey: state.transposeKey,
        display: state.display,
      };

      setStatus('Generating chart…', 'ok');

      fetch('/api/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
        .then(r => r.json().then(body => ({ ok: r.ok, body })))
        .then(({ ok, body }) => {
          if (seq !== requestSeq) return;   // a newer request superseded this one

          if (!ok) {
            setStatus(body.error || 'Something went wrong.', 'error');
            return;
          }

          chartFrame.innerHTML = '';
          const img = document.createElement('img');
          img.src = body.image;
          img.alt = `Harmony chart for ${state.song}`;
          chartFrame.appendChild(img);

          currentChart = { url: body.image, filename: body.filename };
          downloadBtn.disabled = false;

          // Highlight whichever tonal center JazzVis actually used — the
          // wheel reflects this even in Auto mode.
          if (body.tonalCenter) {
            // Hub always shows the auto-computed key so the user knows
            // where Reset returns to; only update it when in Auto mode.
            if (!state.key) keyWheel.setHubLabel(KEY_LABEL[body.tonalCenter]);
            keyWheel.set(body.tonalCenter);
          }

          setStatus('', '');
        })
        .catch(() => {
          if (seq === requestSeq) setStatus('Could not reach the JazzVis service.', 'error');
        });
    }

    // --- Tonal-center wheel -------------------------------------------------
    const keyWheel = createKeyWheel(document.getElementById('key-wheel'), {
      hubLabel: 'Auto',
      allowDeselect: true,
      onChange: (key) => {
        state.key = key;
        generate();
      },
    });
    document.getElementById('key-auto-btn').addEventListener('click', () => {
      state.key = null;
      generate();   // the response will highlight the auto-detected key
    });

    // --- Transpose wheel + button --------------------------------------------
    const transposeWrap = document.getElementById('transpose-wheel-wrap');
    const transposeBtn  = document.getElementById('transpose-btn');
    const displayToggleEl = document.getElementById('display-toggle');

    const transposeWheel = createKeyWheel(document.getElementById('transpose-wheel'), {
      hubLabel: 'TO',
      allowDeselect: false,
      initial: state.transposeKey,
      onChange: (key) => {
        state.transposeKey = key;
        if (state.transpose) generate();
      },
    });

    transposeBtn.addEventListener('click', () => {
      state.transpose = !state.transpose;
      transposeBtn.classList.toggle('active', state.transpose);
      transposeBtn.setAttribute('aria-pressed', String(state.transpose));
      transposeWrap.classList.toggle('collapsed', !state.transpose);

      // JazzVis.py always shows chord names while transposing, so reflect
      // (and lock) that in the display toggle.
      if (state.transpose) {
        setDisplay('chords');
        displayToggleEl.classList.add('disabled');
      } else {
        displayToggleEl.classList.remove('disabled');
        setDisplay('symbols');
      }

      if (state.transpose) generate();
      else generate();
    });

    // --- Display toggle -----------------------------------------------------
    function setDisplay(value) {
      state.display = value;
      document.querySelectorAll('#display-toggle .seg-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.value === value);
      });
    }

    document.querySelectorAll('#display-toggle .seg-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        if (displayToggleEl.classList.contains('disabled')) return;
        setDisplay(btn.dataset.value);
        generate();
      });
    });

    // --- Bars-per-row -------------------------------------------------------
    const bplInput = document.getElementById('bpl-input');
    const bplApply = document.getElementById('bpl-apply');

    function applyBpl() {
      const raw = bplInput.value.trim();
      const parts = raw.split(/\s+/).filter(Boolean);

      if (!parts.length || !parts.every(p => /^[0-9]+$/.test(p) && Number(p) >= 1)) {
        setStatus('Bars per row must be one or more positive numbers, e.g. "8 8 8 8".', 'error');
        return;
      }

      bplInput.value = parts.join(' ');
      state.bpl = parts.join('-');
      generate();
    }
      
    bplApply.addEventListener('click', applyBpl);
    bplInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); applyBpl(); }
    });

    // --- Reset --------------------------------------------------------------
    function resetControls() {
      state.key = null;
      state.transpose = false;
      state.transposeKey = 'C';
      state.display = 'symbols';
      state.bpl = '8-8-8-8';

      transposeBtn.classList.remove('active');
      transposeBtn.setAttribute('aria-pressed', 'false');
      transposeWrap.classList.add('collapsed');
      transposeWheel.set('C');

      displayToggleEl.classList.remove('disabled');
      setDisplay('symbols');

      bplInput.value = DEFAULT_BPL;
    }

    document.getElementById('reset-btn').addEventListener('click', () => {
      resetControls();
      generate();
    });

    // --- Song library (fuzzy-search combobox) -------------------------------
    //
    // Rather than relying on the browser's native <select> type-ahead (which
    // only matches the start of an option), this is a small combobox: typed
    // characters are matched as an in-order subsequence anywhere in each
    // filename, matches are highlighted, and results are ranked so tighter /
    // earlier matches sort first.

    const songInput = document.getElementById('song-search');
    const songList  = document.getElementById('song-list');

    let allSongs = [];
    let filtered = [];
    let activeIndex = -1;

    function escapeHtml(s) {
      return s.replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
      }[c]));
    }

    // Returns the indices in `text` matched by `query` as an in-order
    // subsequence (case-insensitive), or null if `query` doesn't match at
    // all. An empty query matches everything with no highlights.
    function fuzzyMatch(query, text) {
      if (!query) return [];
      const q = query.toLowerCase();
      const t = text.toLowerCase();
      const indices = [];
      let qi = 0;
      for (let ti = 0; ti < t.length && qi < q.length; ti++) {
        if (t[ti] === q[qi]) { indices.push(ti); qi++; }
      }
      return qi === q.length ? indices : null;
    }

    function highlight(name, indices) {
      if (!indices.length) return escapeHtml(name);
      const idxSet = new Set(indices);
      let html = '';
      for (let i = 0; i < name.length; i++) {
        const ch = escapeHtml(name[i]);
        html += idxSet.has(i) ? `<mark>${ch}</mark>` : ch;
      }
      return html;
    }

    function filterSongs(query) {
      const results = [];
      for (const name of allSongs) {
        const indices = fuzzyMatch(query, name);
        if (indices === null) continue;
        const span = indices.length ? indices[indices.length - 1] - indices[0] : 0;
        const start = indices.length ? indices[0] : 0;
        results.push({ name, indices, span, start });
      }
      results.sort((a, b) => a.span - b.span || a.start - b.start || a.name.localeCompare(b.name));
      return results;
    }

    function renderList() {
      songList.innerHTML = '';

      if (!filtered.length) {
        const li = document.createElement('li');
        li.className = 'empty';
        li.textContent = 'No matching lead sheets';
        songList.appendChild(li);
        songList.hidden = false;
        songInput.setAttribute('aria-expanded', 'true');
        return;
      }

      filtered.forEach((item, i) => {
        const li = document.createElement('li');
        li.innerHTML = highlight(item.name, item.indices);
        li.setAttribute('role', 'option');
        li.classList.toggle('active', i === activeIndex);
        li.addEventListener('mousedown', (e) => {
          e.preventDefault();   // keep focus on the input
          selectSong(item.name);
        });
        songList.appendChild(li);
      });
      songList.hidden = false;
      songInput.setAttribute('aria-expanded', 'true');
    }

    function openList() {
      filtered = filterSongs(songInput.value.trim());
      activeIndex = filtered.length ? 0 : -1;
      renderList();
    }

    function closeList() {
      songList.hidden = true;
      songInput.setAttribute('aria-expanded', 'false');
    }

    function selectSong(name) {
      songInput.value = name;
      closeList();
      if (name !== state.song) {
        state.song = name;
        resetControls();
        generate();
      }
    }

    songInput.addEventListener('input', openList);
    songInput.addEventListener('focus', openList);

    songInput.addEventListener('keydown', (e) => {
      if (songList.hidden && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
        openList();
        return;
      }
      switch (e.key) {
        case 'ArrowDown':
          if (filtered.length) {
            activeIndex = (activeIndex + 1) % filtered.length;
            renderList();
          }
          e.preventDefault();
          break;
        case 'ArrowUp':
          if (filtered.length) {
            activeIndex = (activeIndex - 1 + filtered.length) % filtered.length;
            renderList();
          }
          e.preventDefault();
          break;
        case 'Enter':
          if (!songList.hidden && activeIndex >= 0 && filtered[activeIndex]) {
            selectSong(filtered[activeIndex].name);
          }
          e.preventDefault();
          break;
        case 'Escape':
          closeList();
          songInput.value = state.song || '';
          songInput.blur();
          break;
      }
    });

    songInput.addEventListener('blur', () => {
      closeList();
      // Revert to the current selection if the typed text wasn't applied.
      songInput.value = state.song || '';
    });

    // Ctrl/Cmd+F jumps straight to the song search box, overriding the
    // browser's native page-search shortcut.
    document.addEventListener('keydown', (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'f') {
        e.preventDefault();
        songInput.focus();
        songInput.select();
        openList();
      }
    });

    function loadSongs(selectName) {
      fetch('/api/songs')
        .then(r => r.json())
        .then(names => {
          allSongs = names;
          const target = (selectName && names.includes(selectName)) ? selectName : null;
          if (target) {
            songInput.value = target;
            state.song = target;
            resetControls();   // a new lead sheet starts from defaults
            generate();
          }
        });
    }
    loadSongs();

    document.getElementById('song-upload').addEventListener('change', (e) => {
      const file = e.target.files[0];
      if (!file) return;
      const fd = new FormData();
      fd.append('file', file);
      setStatus('Uploading…', 'ok');
      fetch('/api/upload', { method: 'POST', body: fd })
        .then(r => r.json().then(body => ({ ok: r.ok, body })))
        .then(({ ok, body }) => {
          if (!ok) { setStatus(body.error || 'Upload failed.', 'error'); return; }
          loadSongs(body.filename);   // selects the new song and generates
        })
        .catch(() => setStatus('Upload failed.', 'error'));
      e.target.value = '';
    });

  });

})();
