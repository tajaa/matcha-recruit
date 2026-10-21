(function () {
  // The owner's editor on the page (services/magazine: an edit render, never
  // a reader's page; client: magazine/canvas/EditFrame.tsx). It runs in a
  // frame sandboxed with scripts but without same-origin, so it can't reach
  // the dashboard or its session: it talks to the editor outside only by
  // postMessage, and the editor checks everything it is sent.
  //
  // Words are typed straight into the page: every [data-mz-f] is editable
  // (plain, or rich with a toolbar over the selection) and reports its value
  // as `mz-edit`. A click selects what it lands on (`mz-select`): a block of
  // a story, a cover element, the contents. Grips drag a selected cover
  // element or words on a photo (`mz-move`), a dot moves a cover photo's
  // focus (`mz-focal`), a "+" under a block adds one after it (`mz-insert`).
  // The book is the reader's own (book.js); `mz-goto` turns it back to the
  // place being edited after the editor re-renders the page.
  var reader = document.querySelector('[data-mz-edit]');
  if (!reader) return;
  var book = reader.querySelector('.mz-book');
  var mz = function () { return window.mzBook; };
  var post = function (m) { parent.postMessage(m, '*'); };

  var INSERTABLE = [['text', 'Text'], ['photo', 'Photo'], ['photos', 'Photos'], ['quote', 'Quote'],
    ['sidebar', 'Sidebar'], ['qa', 'Q&A'], ['divider', 'Divider']];
  var selected = null, selectedEl = null, editing = null, original = '', timer = null, savedRange = null;
  var overlay = null;  // the words on a photo last clicked, which the grip moves

  // ── what a click is on ────────────────────────────────────────────────
  var esc = function (s) { return window.CSS && CSS.escape ? CSS.escape(s) : String(s).replace(/"/g, '\\"'); };
  function storyOf(el) { var s = el.closest('[data-mz-s]'); return s ? s.getAttribute('data-mz-s') : ''; }
  function blockOf(el) { var b = el.closest('[data-mz-b]'); return b ? +b.getAttribute('data-mz-b') : -1; }
  function targetOf(el) {
    var c = el.closest('[data-mzc-el]');
    if (c) return { kind: 'cover', el: c.getAttribute('data-mzc-el') };
    if (el.closest('.mz-issue__face')) return { kind: 'cover', el: 'photo' };
    if (el.closest('[data-mz-contents]')) return { kind: 'contents' };
    var b = el.closest('[data-mz-b]');
    if (b) return { kind: 'block', story: storyOf(b), block: +b.getAttribute('data-mz-b') };
    var a = el.closest('[data-mz-s]');
    if (a) return { kind: 'story', story: a.getAttribute('data-mz-s') };
    return { kind: 'none' };
  }
  function elFor(t) {
    if (!t) return null;
    if (t.kind === 'cover') {
      return t.el === 'photo' ? document.querySelector('.mz-issue__face .mzc')
        : document.querySelector('[data-mzc-el="' + esc(t.el) + '"]');
    }
    if (t.kind === 'contents') return document.querySelector('[data-mz-contents]');
    var art = document.querySelector('[data-mz-s="' + esc(t.story || '') + '"]');
    if (t.kind === 'block') return art && art.querySelector('[data-mz-b="' + (t.block | 0) + '"]');
    if (t.kind === 'story') return art;
    return null;
  }

  // ── selection ─────────────────────────────────────────────────────────
  function select(t, el, turn) {
    if (selectedEl) selectedEl.classList.remove('mze-sel');
    selected = t; selectedEl = el;
    if (el && t.kind !== 'story' && t.kind !== 'none') el.classList.add('mze-sel');
    if (el && turn && mz()) mz().go(mz().spreadOf(el), turn === 'now');
    placeHandles();
  }
  // Outlines are drawn over the page from an element's own pieces on screen:
  // a paragraph running on into the next column gets a box in each, and the
  // empty sliver a column break can leave gets none (a CSS outline draws it).
  var boxes = { sel: [], hov: [] }, hovEl = null;
  function drawBoxes(kind, el) {
    var list = boxes[kind], rs = [];
    if (el && document.contains(el)) {
      var inBook = el.closest('.mz-book'), clip = inBook ? inBook.getBoundingClientRect() : null, all = el.getClientRects();
      for (var i = 0; i < all.length; i++) {
        var r = all[i], l = r.left - 3, t = r.top - 3, rt = r.right + 3, bt = r.bottom + 3;
        if (clip) { l = Math.max(l, clip.left); rt = Math.min(rt, clip.right); }
        if (r.height > 4 && rt - l > 8) rs.push([l, t, rt - l, bt - t]);
      }
    }
    while (list.length < rs.length) {
      var d = document.createElement('div');
      d.className = 'mze-ui mze-box mze-box--' + kind;
      document.body.appendChild(d); list.push(d);
    }
    list.forEach(function (d, i) {
      var b = rs[i];
      d.style.display = b ? 'block' : 'none';
      if (b) { d.style.left = b[0] + 'px'; d.style.top = b[1] + 'px'; d.style.width = b[2] + 'px'; d.style.height = b[3] + 'px'; }
    });
  }
  function drawOutlines() {
    var sel = selected && selected.kind !== 'story' && selected.kind !== 'none' ? selectedEl : null;
    drawBoxes('sel', sel);
    drawBoxes('hov', hovEl && hovEl !== sel ? hovEl : null);
  }
  document.addEventListener('click', function (e) {
    var t = e.target;
    if (!(t instanceof Element) || t.closest('.mze-ui')) return;
    // Links, contents entries and cover lines don't take you anywhere here.
    if (t.closest('a, label')) { e.preventDefault(); e.stopPropagation(); }
    if (t.closest('.mz-turn')) return;
    var target = targetOf(t);
    overlay = t.closest('[data-mz-drag]');
    select(target, elFor(target));
    post({ type: 'mz-select', target: target });
    var pick = t.closest('[data-mz-pick]');
    if (pick) {
      var item = pick.getAttribute('data-mz-item');
      post({ type: 'mz-pick', story: storyOf(pick), block: blockOf(pick), item: item === null ? null : +item });
    }
  }, true);

  // ── typing ────────────────────────────────────────────────────────────
  var plainMode = (function () {
    var d = document.createElement('div');
    try { d.contentEditable = 'plaintext-only'; } catch (err) { return 'true'; }
    return d.contentEditable === 'plaintext-only' ? 'plaintext-only' : 'true';
  })();
  var isRich = function (f) { return f.getAttribute('data-mz-k') === 'rich'; };
  // A plain field's words as typed: not `innerText`, which would hand back
  // what CSS shows (a kicker set in capitals); a line break is a newline,
  // and a typed space at a line's end (a no-break space) is a space.
  function plainOf(f) {
    var out = '';
    (function walk(n) {
      n.childNodes.forEach(function (c) {
        if (c.nodeType === 3) out += c.nodeValue;
        else if (c.nodeName === 'BR') out += '\n';
        else {
          if (/^(DIV|P)$/.test(c.nodeName) && out && out.slice(-1) !== '\n') out += '\n';
          walk(c);
        }
      });
    })(f);
    return out.replace(/\u00a0/g, ' ').replace(/\n+$/, '');
  }
  var valueOf = function (f) { return isRich(f) ? f.innerHTML : plainOf(f); };
  document.querySelectorAll('[data-mz-f]').forEach(function (f) {
    f.setAttribute('contenteditable', isRich(f) ? 'true' : plainMode);
    f.setAttribute('spellcheck', 'true');
  });
  try { document.execCommand('defaultParagraphSeparator', false, 'p'); } catch (err) { /* older engines */ }

  function commit(f) {
    clearTimeout(timer);
    var v = valueOf(f);
    if (v === f.__mzLast) return;
    f.__mzLast = v;
    post({ type: 'mz-edit', story: storyOf(f), block: blockOf(f), field: f.getAttribute('data-mz-f'), value: v,
      rich: isRich(f) });
  }
  document.addEventListener('focusin', function (e) {
    var f = e.target instanceof Element && e.target.closest('[data-mz-f]');
    if (!f) return;
    editing = f; original = valueOf(f); f.__mzLast = original;
    post({ type: 'mz-editing', on: true });
  });
  document.addEventListener('focusout', function (e) {
    var f = e.target instanceof Element && e.target.closest('[data-mz-f]');
    if (!f || f !== editing) return;
    // Clicking the toolbar keeps the field: only a real leave ends editing.
    setTimeout(function () {
      if (document.activeElement && document.activeElement.closest && document.activeElement.closest('.mze-bar')) return;
      commit(f);
      if (editing !== f) return;  // already typing in the next field
      editing = null; hideBar();
      post({ type: 'mz-editing', on: false });
    }, 0);
  });
  document.addEventListener('input', function (e) {
    var f = e.target instanceof Element && e.target.closest('[data-mz-f]');
    if (!f) return;
    clearTimeout(timer);
    timer = setTimeout(function () { commit(f); }, 250);
    placeHandles();
  });
  document.addEventListener('paste', function (e) {
    var f = e.target instanceof Element && e.target.closest('[data-mz-f]');
    if (!f) return;
    // Words only: another page's formatting never comes in with them.
    e.preventDefault();
    document.execCommand('insertText', false, (e.clipboardData && e.clipboardData.getData('text/plain')) || '');
  });
  document.addEventListener('keydown', function (e) {
    var mod = e.metaKey || e.ctrlKey, k = (e.key || '').toLowerCase();
    if (editing) {
      if (e.key === 'Escape') {
        // A headline goes back to what it was; a paragraph's typing is kept
        // (undo takes it back), so a stray key never throws it away.
        e.preventDefault();
        if (!isRich(editing)) editing.textContent = original;
        editing.blur();
      } else if (e.key === 'Enter' && !e.shiftKey && !isRich(editing)) {
        e.preventDefault(); editing.blur();
      } else if (mod && k === 'k' && isRich(editing)) {
        e.preventDefault(); openLink();
      } else if (mod && k === 's') {
        e.preventDefault(); commit(editing); post({ type: 'mz-key', key: 'save' });
      } else if (/^(Home|End|PageUp|PageDown)$/.test(e.key) && !e.shiftKey) {
        // On a Mac these scroll the page rather than move the caret, which
        // here would carry the book off screen mid-sentence.
        e.preventDefault();
      }
      return;
    }
    if (mod && k === 'z') { e.preventDefault(); post({ type: 'mz-key', key: e.shiftKey ? 'redo' : 'undo' }); }
    else if (mod && k === 'y') { e.preventDefault(); post({ type: 'mz-key', key: 'redo' }); }
    else if (mod && k === 's') { e.preventDefault(); post({ type: 'mz-key', key: 'save' }); }
    else if (e.key === 'Delete' || e.key === 'Backspace') {
      // Never the browser's own "back", which would leave the editor.
      if (!(e.target instanceof Element && e.target.closest('input, textarea'))) e.preventDefault();
      if (selected && selected.kind === 'block') post({ type: 'mz-key', key: 'delete' });
    } else if (e.key === 'Escape' && selected) {
      select({ kind: 'none' }, null); post({ type: 'mz-select', target: { kind: 'none' } });
    }
  });

  // Keep the words being typed on screen: when they run onto another page,
  // turn to it.
  function caretRect() {
    var s = getSelection();
    if (!s.rangeCount) return null;
    var r = s.getRangeAt(0), rects = r.getClientRects();
    var rect = rects.length ? rects[rects.length - 1] : null;
    if (!rect || (!rect.width && !rect.height)) {
      var n = r.startContainer;
      rect = (n.nodeType === 1 ? n : n.parentElement).getBoundingClientRect();
    }
    return rect;
  }
  document.addEventListener('selectionchange', function () {
    if (!editing) return;
    var rect = caretRect();
    if (rect && editing.closest('.mz-book') && mz()) {
      var b = book.getBoundingClientRect();
      if (rect.left < b.left || rect.right > b.right + 1) {
        mz().go(Math.floor((rect.left - b.left + book.scrollLeft) / (book.clientWidth || 1)), true);
      }
    }
    if (isRich(editing)) showBar(); else hideBar();
  });

  // ── the toolbar over selected words (rich fields) ─────────────────────
  var bar = document.createElement('div');
  bar.className = 'mze-ui mze-bar';
  bar.setAttribute('role', 'toolbar');
  bar.setAttribute('aria-label', 'Format');
  var TOOLS = [['bold', 'B', 'Bold'], ['italic', 'I', 'Italic'], ['link', 'Link', 'Link'], ['h2', 'H2', 'Heading'],
    ['h3', 'H3', 'Small heading'], ['blockquote', '“', 'Quote'], ['ul', '•', 'Bulleted list'], ['ol', '1.', 'Numbered list']];
  bar.innerHTML = TOOLS.map(function (t) {
    return '<button type="button" data-cmd="' + t[0] + '" title="' + t[2] + '" aria-label="' + t[2] + '">' + t[1] + '</button>';
  }).join('') + '<input class="mze-link" type="url" placeholder="Paste a link, then Enter" aria-label="Link address" hidden>';
  document.body.appendChild(bar);
  var linkInput = bar.querySelector('.mze-link');
  bar.addEventListener('mousedown', function (e) { if (e.target !== linkInput) e.preventDefault(); });
  bar.addEventListener('click', function (e) {
    var b = e.target instanceof Element && e.target.closest('button');
    if (!b || !editing) return;
    var cmd = b.getAttribute('data-cmd'), block = (document.queryCommandValue('formatBlock') || '').toLowerCase();
    if (cmd === 'bold' || cmd === 'italic') document.execCommand(cmd);
    else if (cmd === 'h2' || cmd === 'h3' || cmd === 'blockquote') document.execCommand('formatBlock', false, block === cmd ? 'p' : cmd);
    else if (cmd === 'ul') document.execCommand('insertUnorderedList');
    else if (cmd === 'ol') document.execCommand('insertOrderedList');
    else if (cmd === 'link') { openLink(); return; }
    commit(editing); showBar();
  });
  function openLink() {
    var s = getSelection();
    if (!s.rangeCount) return;
    savedRange = s.getRangeAt(0).cloneRange();
    var a = savedRange.startContainer.parentElement && savedRange.startContainer.parentElement.closest('a');
    linkInput.value = a ? a.getAttribute('href') || '' : '';
    linkInput.hidden = false; showBar(true); linkInput.focus();
  }
  linkInput.addEventListener('keydown', function (e) {
    if (e.key !== 'Enter' && e.key !== 'Escape') return;
    e.preventDefault();
    var url = linkInput.value.trim(), field = editing;
    linkInput.hidden = true;
    if (!field || !savedRange) return;
    field.focus();
    var s = getSelection(); s.removeAllRanges(); s.addRange(savedRange);
    if (e.key === 'Enter') {
      if (!url) document.execCommand('unlink');
      else document.execCommand('createLink', false, /^(https?:|mailto:)/i.test(url) ? url : 'https://' + url);
      commit(field);
    }
    showBar();
  });
  function showBar(keep) {
    var s = getSelection();
    if (!editing || !isRich(editing) || !s.rangeCount || (s.isCollapsed && !keep && linkInput.hidden)) { hideBar(); return; }
    var rect = s.getRangeAt(0).getBoundingClientRect();
    if (!rect.width && !rect.height) rect = caretRect() || rect;
    bar.style.display = 'flex';
    var w = bar.offsetWidth, h = bar.offsetHeight;
    var top = rect.top - h - 8 < 4 ? rect.bottom + 8 : rect.top - h - 8;
    bar.style.top = top + 'px';
    bar.style.left = Math.max(4, Math.min(innerWidth - w - 4, rect.left + rect.width / 2 - w / 2)) + 'px';
    bar.querySelectorAll('button').forEach(function (b) {
      var c = b.getAttribute('data-cmd'), on = false;
      try {
        if (c === 'bold' || c === 'italic') on = document.queryCommandState(c);
        else if (c === 'ul') on = document.queryCommandState('insertUnorderedList');
        else if (c === 'ol') on = document.queryCommandState('insertOrderedList');
        else if (c !== 'link') on = (document.queryCommandValue('formatBlock') || '').toLowerCase() === c;
      } catch (err) { on = false; }
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
  }
  function hideBar() { bar.style.display = 'none'; linkInput.hidden = true; }

  // ── "+": add a block after the one under the pointer ──────────────────
  var plus = document.createElement('button');
  plus.type = 'button'; plus.className = 'mze-ui mze-plus'; plus.textContent = '+';
  plus.setAttribute('aria-label', 'Add a block here');
  var menu = document.createElement('div');
  menu.className = 'mze-ui mze-menu'; menu.setAttribute('role', 'menu');
  document.body.appendChild(plus); document.body.appendChild(menu);
  var plusFor = null, plusHide = null;
  function placePlus(blockEl) {
    var rects = blockEl.getClientRects(), r = rects[rects.length - 1];
    if (!r) return;
    // In the gap under the block, clear of its last line.
    plus.style.display = 'block';
    plus.style.left = (r.left + r.width / 2 - 11) + 'px';
    plus.style.top = (r.bottom + 2) + 'px';
  }
  document.addEventListener('mouseover', function (e) {
    var t = e.target instanceof Element ? e.target : null;
    if (!t || t.closest('.mze-ui')) { clearTimeout(plusHide); return; }
    var b = t.closest('[data-mz-s] [data-mz-b]');
    if (b !== hovEl) { hovEl = b; drawOutlines(); }
    if (!b) { clearTimeout(plusHide); plusHide = setTimeout(function () { plus.style.display = 'none'; }, 400); return; }
    clearTimeout(plusHide);
    plusFor = b; placePlus(b);
  });
  plus.addEventListener('click', function () {
    if (!plusFor) return;
    var r = plus.getBoundingClientRect();
    menu.innerHTML = INSERTABLE.map(function (t) {
      return '<button type="button" role="menuitem" data-type="' + t[0] + '">' + t[1] + '</button>';
    }).join('');
    menu.style.display = 'grid';
    menu.style.left = Math.min(innerWidth - 180, r.left) + 'px';
    menu.style.top = Math.max(4, Math.min(innerHeight - menu.offsetHeight - 4, r.bottom + 4)) + 'px';
    menu.__for = plusFor;
  });
  menu.addEventListener('click', function (e) {
    var b = e.target instanceof Element && e.target.closest('button');
    menu.style.display = 'none';
    if (!b || !menu.__for) return;
    var at = +menu.__for.getAttribute('data-mz-b') + 1;
    post({ type: 'mz-insert', story: storyOf(menu.__for), at: at, kind: b.getAttribute('data-type') });
  });
  document.addEventListener('mousedown', function (e) {
    if (!(e.target instanceof Element) || !e.target.closest('.mze-menu, .mze-plus')) menu.style.display = 'none';
  });

  // ── moving cover elements and words on a photo; a photo's focus ───────
  var grip = document.createElement('span'), width = document.createElement('span'), dot = document.createElement('span');
  grip.className = 'mze-ui mze-grip'; grip.title = 'Drag to move';
  width.className = 'mze-ui mze-grip mze-width'; width.title = 'Drag to widen';
  dot.className = 'mze-ui mze-focal'; dot.title = 'Drag to choose what the picture keeps in view';
  [grip, width, dot].forEach(function (n) { document.body.appendChild(n); });
  function movable() {
    if (!selectedEl) return null;
    if (selected.kind === 'cover' && selected.el !== 'photo') return { el: selectedEl, box: selectedEl.closest('[data-mz-art]'), centred: false };
    if (overlay && selectedEl.contains(overlay) && document.contains(overlay)) {
      return { el: overlay, box: overlay.closest('.mz-frame'), centred: true };
    }
    return null;
  }
  function focalTarget() {
    if (!selectedEl) return null;
    if (selected.kind === 'cover' && selected.el === 'photo') return document.querySelector('.mz-issue__face [data-mz-focal]');
    if (selected.kind === 'block') return selectedEl.querySelector(':scope > [data-mz-focal], .mz-cover__media[data-mz-focal]');
    return null;
  }
  function placeHandles() {
    drawOutlines();
    var m = movable(), f = focalTarget();
    grip.style.display = width.style.display = dot.style.display = 'none';
    if (m && m.box) {
      var r = m.el.getBoundingClientRect();
      grip.style.display = 'block'; grip.style.left = (r.left - 9) + 'px'; grip.style.top = (r.top - 9) + 'px';
      if (!m.centred) { width.style.display = 'block'; width.style.left = (r.right - 9) + 'px'; width.style.top = (r.top + r.height / 2 - 9) + 'px'; }
    }
    if (f) {
      var fr = f.getBoundingClientRect(), xy = (f.getAttribute('data-mz-focal') || '50,50').split(',');
      dot.style.display = 'block';
      dot.style.left = (fr.left + fr.width * xy[0] / 100 - 11) + 'px';
      dot.style.top = (fr.top + fr.height * xy[1] / 100 - 11) + 'px';
    }
  }
  var r1 = function (n) { return Math.round(n * 10) / 10; };
  var clamp = function (n, lo, hi) { return Math.max(lo, Math.min(hi, n)); };
  function drag(handle, onMove, onEnd) {
    handle.addEventListener('pointerdown', function (e) {
      e.preventDefault(); handle.setPointerCapture(e.pointerId);
      var x0 = e.clientX, y0 = e.clientY;
      var move = function (ev) { onMove(ev.clientX - x0, ev.clientY - y0); };
      var up = function () {
        handle.removeEventListener('pointermove', move); handle.removeEventListener('pointerup', up);
        onEnd(); placeHandles();
      };
      handle.addEventListener('pointermove', move); handle.addEventListener('pointerup', up);
    });
  }
  var start = null;
  function begin(m) {
    var s = m.el.style;
    return { x: parseFloat(s.left) || 0, y: parseFloat(s.top) || 0, w: parseFloat(s.width) || 0, box: m.box.getBoundingClientRect(), m: m };
  }
  function moveTarget(m) {
    if (selected.kind === 'cover') return selected;
    return { kind: 'overlay', story: storyOf(m.el), block: blockOf(m.el), overlay: m.el.getAttribute('data-mz-drag') };
  }
  drag(grip, function (dx, dy) {
    var m = movable(); if (!m) return;
    if (!start) start = begin(m);
    var x = clamp(start.x + dx / start.box.width * 100, 0, m.centred ? 100 : 100 - (start.w || 0));
    var y = clamp(start.y + dy / start.box.height * 100, 0, 100);
    m.el.style.left = r1(x) + '%'; m.el.style.top = r1(y) + '%'; placeHandles();
  }, function () {
    var m = movable();
    if (m && start) {
      // Words on a photo are placed in whole percents (story_schema).
      var round = m.centred ? Math.round : r1;
      post({ type: 'mz-move', target: moveTarget(m), x: round(parseFloat(m.el.style.left)), y: round(parseFloat(m.el.style.top)) });
    }
    start = null;
  });
  drag(width, function (dx) {
    var m = movable(); if (!m) return;
    if (!start) start = begin(m);
    var w = clamp(start.w + dx / start.box.width * 100, 10, 100 - start.x);
    m.el.style.width = r1(w) + '%'; placeHandles();
  }, function () {
    var m = movable();
    if (m && start) post({ type: 'mz-move', target: moveTarget(m), x: start.x, y: start.y, w: r1(parseFloat(m.el.style.width)) });
    start = null;
  });
  var focalStart = null;
  drag(dot, function (dx, dy) {
    var f = focalTarget(); if (!f) return;
    if (!focalStart) { var xy = (f.getAttribute('data-mz-focal') || '50,50').split(','); focalStart = { x: +xy[0], y: +xy[1], r: f.getBoundingClientRect() }; }
    var x = Math.round(clamp(focalStart.x + dx / focalStart.r.width * 100, 0, 100));
    var y = Math.round(clamp(focalStart.y + dy / focalStart.r.height * 100, 0, 100));
    f.setAttribute('data-mz-focal', x + ',' + y);
    var img = f.querySelector('img');
    if (img) { img.style.objectPosition = x + '% ' + y + '%'; if (img.style.transformOrigin) img.style.transformOrigin = x + '% ' + y + '%'; }
    placeHandles();
  }, function () {
    var f = focalTarget();
    if (f && focalStart) {
      var xy = f.getAttribute('data-mz-focal').split(',');
      post({ type: 'mz-focal', target: selected, x: +xy[0], y: +xy[1] });
    }
    focalStart = null;
  });
  book.addEventListener('scroll', function () {
    placeHandles();
    if (plus.style.display === 'block' && plusFor) placePlus(plusFor);
    clearTimeout(book.__mzPlace);
    book.__mzPlace = setTimeout(function () { if (mz()) post({ type: 'mz-place', spread: mz().at() }); }, 200);
  }, { passive: true });
  addEventListener('resize', placeHandles);
  addEventListener('scroll', placeHandles, { passive: true });

  // ── the editor outside ────────────────────────────────────────────────
  addEventListener('message', function (e) {
    if (e.source !== parent || !e.data || typeof e.data.type !== 'string') return;
    var d = e.data;
    if (d.type === 'mz-goto') {
      // Once the page's own type has loaded (or a moment has passed): the
      // pages are measured with it, so the place found is where it stays,
      // and the editor shows this page without a flash of other type.
      var done = false;
      var show = function () {
        if (done) return;
        done = true;
        if (mz()) mz().refit();
        var el = elFor(d.target);
        if (el) select(d.target, el, 'now');
        else if (mz() && typeof d.spread === 'number') mz().go(d.spread, true);
        reader.classList.add('mze-on');
        post({ type: 'mz-shown' });
      };
      (document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve()).then(show, show);
      setTimeout(show, 1500);
    } else if (d.type === 'mz-select') {
      var to = elFor(d.target);
      select(d.target, to, to ? 'smooth' : null);
    }
  });
  reader.scrollIntoView({ block: 'start' });
  post({ type: 'mz-ready' });
})();
