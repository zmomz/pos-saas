/* Cloud POS — prototype controls: variation toolbar, RTL toggle, theme toggle, QR placeholder */
(function () {
  /* ---- Deterministic pseudo-QR (square modules only — a real ZATCA TLV QR is generated server-side) ---- */
  window.makeQR = function (el, opts) {
    opts = opts || {};
    const n = opts.modules || 25;
    const seedStr = (opts.seed || 'ZATCA-2026') + '';
    let h = 2166136261;
    for (let i = 0; i < seedStr.length; i++) { h ^= seedStr.charCodeAt(i); h = Math.imul(h, 16777619); }
    const rng = () => { h ^= h << 13; h ^= h >>> 17; h ^= h << 5; return ((h >>> 0) % 1000) / 1000; };
    const cells = [];
    const isFinder = (r, c) => {
      const inBox = (br, bc) => r >= br && r < br + 7 && c >= bc && c < bc + 7;
      return inBox(0, 0) || inBox(0, n - 7) || inBox(n - 7, 0);
    };
    for (let r = 0; r < n; r++) for (let c = 0; c < n; c++) {
      let on;
      if (isFinder(r, c)) {
        const lr = r >= n - 7 ? r - (n - 7) : r, lc = c >= n - 7 ? c - (n - 7) : c;
        const ring = (lr === 0 || lr === 6 || lc === 0 || lc === 6);
        const core = (lr >= 2 && lr <= 4 && lc >= 2 && lc <= 4);
        on = ring || core;
      } else { on = rng() > 0.52; }
      if (on) cells.push(`<rect x="${c}" y="${r}" width="1" height="1"/>`);
    }
    const dark = opts.color || 'oklch(0.24 0.02 252)';
    el.innerHTML = `<svg viewBox="0 0 ${n} ${n}" width="100%" height="100%" shape-rendering="crispEdges" fill="${dark}">${cells.join('')}</svg>`;
  };
  window.hydrateQR = function (root) {
    (root || document).querySelectorAll('[data-qr]').forEach(el => {
      window.makeQR(el, { modules: +el.dataset.qrModules || 25, seed: el.dataset.qr, color: el.dataset.qrColor });
    });
  };

  /* ---- Build the floating prototype toolbar ----
     config = { variations: [{key,label,options:[{val,label,icon}]}], themes:bool, rtl:bool, onChange } */
  window.protoBar = function (config) {
    config = config || {};
    const state = {};
    const bar = document.createElement('div');
    bar.className = 'proto-bar ui';
    let html = `<span class="pb-label">${config.title || 'Variations'}</span>`;

    (config.variations || []).forEach(v => {
      state[v.key] = v.options[0].val;
      html += `<div class="pb-group" data-key="${v.key}">`;
      v.options.forEach((o, i) => {
        html += `<button class="pb-btn ${i === 0 ? 'active' : ''}" data-val="${o.val}">${o.icon ? window.icon(o.icon) : ''}${o.label}</button>`;
      });
      html += `</div>`;
    });

    const hasToggles = config.themes || config.rtl;
    if (hasToggles && (config.variations || []).length) html += `<span class="pb-divider"></span>`;

    if (config.themes) {
      html += `<div class="pb-group" data-key="__theme">
        <button class="pb-btn active" data-theme="">Petrol</button>
        <button class="pb-btn" data-theme="green">Green</button>
        <button class="pb-btn" data-theme="indigo">Indigo</button>
      </div>`;
    }
    if (config.rtl) {
      html += `<button class="pb-btn" data-rtl style="background:oklch(1 0 0 / .06)">${window.icon('globe')}<span data-rtl-label>عربي</span></button>`;
    }
    bar.innerHTML = html;
    document.body.appendChild(bar);

    function emit() { if (config.onChange) config.onChange(state); }

    bar.querySelectorAll('.pb-group[data-key]:not([data-key="__theme"])').forEach(group => {
      const key = group.dataset.key;
      group.querySelectorAll('.pb-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          group.querySelectorAll('.pb-btn').forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
          state[key] = btn.dataset.val;
          document.documentElement.setAttribute('data-var-' + key, btn.dataset.val);
          emit();
        });
      });
      // set initial attribute
      document.documentElement.setAttribute('data-var-' + key, state[key]);
    });

    const themeGroup = bar.querySelector('[data-key="__theme"]');
    if (themeGroup) {
      themeGroup.querySelectorAll('.pb-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          themeGroup.querySelectorAll('.pb-btn').forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
          const t = btn.dataset.theme;
          if (t) document.documentElement.setAttribute('data-theme', t);
          else document.documentElement.removeAttribute('data-theme');
        });
      });
    }

    const rtlBtn = bar.querySelector('[data-rtl]');
    if (rtlBtn) {
      rtlBtn.addEventListener('click', () => {
        const isRtl = document.documentElement.getAttribute('dir') === 'rtl';
        if (isRtl) {
          document.documentElement.removeAttribute('dir');
          document.documentElement.lang = 'en';
          rtlBtn.classList.remove('active');
          rtlBtn.querySelector('[data-rtl-label]').textContent = 'عربي';
        } else {
          document.documentElement.setAttribute('dir', 'rtl');
          document.documentElement.lang = 'ar';
          rtlBtn.classList.add('active');
          rtlBtn.querySelector('[data-rtl-label]').textContent = 'EN';
        }
        if (config.onRtl) config.onRtl(!isRtl);
      });
    }
    emit();
    return state;
  };

  document.addEventListener('DOMContentLoaded', () => window.hydrateQR());
})();
