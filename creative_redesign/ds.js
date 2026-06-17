/* Cloud POS — Creative Redesign interaction engine
   Pure vanilla JS. Drives: count-up, ring gauges, animated bars,
   interactive line charts (hover tooltip + range morph), ⌘K palette. */
(function () {
  'use strict';
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const ease = (t) => 1 - Math.pow(1 - t, 3);

  /* ---------- count-up ---------- */
  function countUp(el) {
    const target = parseFloat(el.dataset.count);
    const dec = parseInt(el.dataset.dec || '0', 10);
    const prefix = el.dataset.prefix || '';
    const suffix = el.dataset.suffix || '';
    const dur = 1100, t0 = performance.now();
    function frame(now) {
      const p = Math.min(1, (now - t0) / dur);
      const v = target * ease(p);
      el.textContent = prefix + v.toLocaleString('en-US', { minimumFractionDigits: dec, maximumFractionDigits: dec }) + suffix;
      if (p < 1) requestAnimationFrame(frame);
      else el.textContent = prefix + target.toLocaleString('en-US', { minimumFractionDigits: dec, maximumFractionDigits: dec }) + suffix;
    }
    requestAnimationFrame(frame);
  }

  /* ---------- ring gauges ---------- */
  function initRing(el) {
    const pct = parseFloat(el.dataset.pct);
    const circle = $('.prog', el);
    const r = circle.r.baseVal.value;
    const C = 2 * Math.PI * r;
    circle.style.strokeDasharray = C;
    circle.style.strokeDashoffset = C;
    requestAnimationFrame(() => requestAnimationFrame(() => {
      circle.style.strokeDashoffset = C * (1 - pct / 100);
    }));
    const pcEl = $('.pc', el);
    if (pcEl && pcEl.dataset.count == null) {
      pcEl.dataset.count = pct; pcEl.dataset.suffix = '%';
    }
  }

  /* ---------- animated bars ---------- */
  function initBars() {
    $$('[data-w]').forEach((el) => {
      const w = el.dataset.w;
      requestAnimationFrame(() => requestAnimationFrame(() => { el.style.width = w + '%'; }));
    });
  }

  /* ---------- interactive line chart ----------
     <div class="chartwrap" data-chart='{"series":{"12M":[...]}, "labels":[...], "fmt":"sar"}'> */
  function buildPath(vals, W, H, pad) {
    const max = Math.max(...vals) * 1.08, min = Math.min(...vals) * 0.96;
    const span = (max - min) || 1;
    const innerW = W - pad * 2, innerH = H - pad * 2;
    const pts = vals.map((v, i) => {
      const x = pad + (innerW * i) / (vals.length - 1);
      const y = pad + innerH * (1 - (v - min) / span);
      return [x, y];
    });
    let d = 'M' + pts[0][0] + ',' + pts[0][1];
    for (let i = 1; i < pts.length; i++) {
      const [x0, y0] = pts[i - 1], [x1, y1] = pts[i];
      const cx = (x0 + x1) / 2;
      d += ' C' + cx + ',' + y0 + ' ' + cx + ',' + y1 + ' ' + x1 + ',' + y1;
    }
    return { d, pts };
  }
  function fmt(v, kind) {
    if (kind === 'sar') return 'SAR ' + Math.round(v).toLocaleString('en-US');
    if (kind === 'int') return Math.round(v).toLocaleString('en-US');
    return v;
  }
  function initChart(wrap) {
    const cfg = JSON.parse(wrap.dataset.chart);
    const svg = $('svg.chart', wrap);
    const W = 640, H = parseInt(svg.dataset.h || '200', 10), pad = 14;
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    const area = $('.c-area', svg), line = $('.c-line', svg), dotE = $('.c-end', svg);
    const cross = $('.crosshair', svg), cdot = $('.cdot', svg);
    const tip = $('.ctip', wrap);
    let cur = wrap.dataset.range || Object.keys(cfg.series)[0];

    function render(key, animate) {
      const vals = cfg.series[key];
      const { d, pts } = buildPath(vals, W, H, pad);
      line.setAttribute('d', d);
      area.setAttribute('d', d + ` L${pts[pts.length-1][0]},${H} L${pts[0][0]},${H} Z`);
      dotE.setAttribute('cx', pts[pts.length - 1][0]);
      dotE.setAttribute('cy', pts[pts.length - 1][1]);
      wrap._pts = pts; wrap._vals = vals; wrap._labels = cfg.labelsByRange ? cfg.labelsByRange[key] : cfg.labels;
      if (animate && line.getTotalLength) {
        const L = line.getTotalLength();
        line.style.transition = 'none'; line.style.strokeDasharray = L; line.style.strokeDashoffset = L;
        requestAnimationFrame(() => { line.style.transition = 'stroke-dashoffset 1s ease'; line.style.strokeDashoffset = 0; });
      }
    }
    render(cur, true);

    svg.addEventListener('mousemove', (e) => {
      const rect = svg.getBoundingClientRect();
      const x = (e.clientX - rect.left) / rect.width * W;
      const pts = wrap._pts; if (!pts) return;
      let idx = 0, best = 1e9;
      pts.forEach((p, i) => { const dd = Math.abs(p[0] - x); if (dd < best) { best = dd; idx = i; } });
      const [px, py] = pts[idx];
      cross.setAttribute('x1', px); cross.setAttribute('x2', px);
      cross.setAttribute('y1', pad); cross.setAttribute('y2', H - pad);
      cross.style.opacity = 1; cdot.style.opacity = 1;
      cdot.setAttribute('cx', px); cdot.setAttribute('cy', py);
      const lbl = (wrap._labels && wrap._labels[idx]) || '';
      tip.innerHTML = '<div class="cap">' + lbl + '</div><b>' + fmt(wrap._vals[idx], cfg.fmt) + '</b>';
      tip.style.left = (px / W * rect.width) + 'px';
      tip.style.top = (py / H * rect.height) + 'px';
      tip.style.opacity = 1;
    });
    svg.addEventListener('mouseleave', () => {
      cross.style.opacity = 0; cdot.style.opacity = 0; tip.style.opacity = 0;
    });

    // range toggle
    const seg = wrap.closest('.tile') && $('.seg[data-for="' + wrap.id + '"]', wrap.closest('.tile'));
    if (seg) {
      $$('button', seg).forEach((b) => b.addEventListener('click', () => {
        $$('button', seg).forEach((x) => x.classList.remove('active'));
        b.classList.add('active'); cur = b.dataset.range; render(cur, true);
        const xl = wrap.closest('.tile').querySelector('.xlabels');
        if (xl && cfg.xticksByRange && cfg.xticksByRange[cur]) {
          xl.innerHTML = cfg.xticksByRange[cur].map((t) => '<span>' + t + '</span>').join('');
        }
      }));
    }
  }

  /* ---------- ⌘K palette ---------- */
  function initPalette() {
    const bg = $('#palette'); if (!bg) return;
    const open = () => { bg.classList.add('open'); const i = $('input', bg); if (i) { i.value=''; i.focus(); } };
    const close = () => bg.classList.remove('open');
    window.addEventListener('keydown', (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); bg.classList.contains('open') ? close() : open(); }
      if (e.key === 'Escape') close();
    });
    $$('.cmdk, #cmdk-trigger').forEach((t) => t.addEventListener('click', open));
    bg.addEventListener('click', (e) => { if (e.target === bg) close(); });
    const input = $('input', bg);
    if (input) input.addEventListener('input', () => {
      const q = input.value.toLowerCase();
      $$('.opt', bg).forEach((o) => { o.style.display = o.textContent.toLowerCase().includes(q) ? '' : 'none'; });
    });
  }

  /* ---------- boot ---------- */
  function boot() {
    $$('[data-count]').forEach(countUp);
    $$('.gauge').forEach(initRing);
    // re-run count-up on gauge centers (they got data-count set in initRing)
    $$('.gauge .pc[data-count]').forEach(countUp);
    initBars();
    $$('.chartwrap[data-chart]').forEach(initChart);
    initPalette();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
