"""PitchPal 視覺：和弦譜表頭（白紙、墨黑粗線、單一朱紅）。"""
import gradio as gr

ACCENT = "#C8321A"
INK = "#16130f"

_VERMILION = gr.themes.Color(
    c50="#fdf1ee", c100="#fadcd5", c200="#f4b8aa", c300="#ea8d77", c400="#dc6247",
    c500="#c8321a", c600="#b02d17", c700="#8f2413", c800="#6e1c0f", c900="#4d130a",
    c950="#2f0b06", name="vermilion",
)

THEME = gr.themes.Base(
    primary_hue=_VERMILION,
    neutral_hue="stone",
    font=(gr.themes.GoogleFont("Noto Sans TC"), "PingFang TC", "Microsoft JhengHei", "ui-sans-serif", "system-ui", "sans-serif"),
    radius_size=gr.themes.sizes.radius_md,
).set(
    body_background_fill="#ffffff",
    body_text_color=INK,
    block_background_fill="#ffffff",
    block_border_width="0px",
    block_shadow="none",
    button_primary_background_fill=ACCENT,
    button_primary_background_fill_hover="#b02d17",
    button_primary_text_color="#ffffff",
    button_primary_shadow="none",
    button_secondary_background_fill="#ffffff",
    button_secondary_border_color=INK,
    button_secondary_text_color=INK,
)

# 整首對拍：歌用一般的 <audio>，節拍用 Web Audio 依歌的播放時間排程，所以暫停、拖曳進度都對得上；
# 節拍開關可在播放中隨時切換。
METRO_JS = """
window.ppMetro = {
  on: false, drone: false, nodes: null, hz: 0, bpm: 0, phase: 0, ctx: null, timer: null, last: -1,
  audio() { return document.getElementById('pp-metro-audio'); },
  ensureCtx() {
    if (!this.ctx) this.ctx = new (window.AudioContext || window.webkitAudioContext)();
    if (this.ctx.state === 'suspended') this.ctx.resume();
  },
  load(url, bpm, phase, hz, keyLabel) {
    const a = this.audio();
    if (!a || !url || !bpm || phase === null || phase === undefined) return;
    this.bpm = bpm; this.phase = phase; this.last = -1; this.hz = hz || 0;
    this.stopDrone();
    a.src = url; a.currentTime = 0;
    a.onseeked = () => { this.last = -1; };
    a.onplay = () => { if (this.drone) { this.ensureCtx(); this.startDrone(); } };
    a.onpause = () => this.stopDrone();
    a.onended = () => this.stopDrone();
    const lab = document.getElementById('pp-drone-label'); if (lab) lab.textContent = '主音' + (keyLabel ? '（' + keyLabel + '）' : '') + ' 開／關';
    const info = document.getElementById('pp-metro-info');
    if (info) info.textContent = '已載入。按播放，再用下面的開關隨時打開或關掉「節拍」（' + bpm + ' BPM）與「主音」。';
    document.getElementById('pp-metro').classList.add('ready');
    if (!this.timer) this.timer = setInterval(() => this.tick(), 25);
  },
  setOn(v) { this.on = v; this.last = -1; if (v) this.ensureCtx(); },
  setDrone(v) {
    this.drone = v;
    if (v) { this.ensureCtx(); const a = this.audio(); if (a && !a.paused) this.startDrone(); } else this.stopDrone();
  },
  startDrone() {
    if (!this.hz || this.nodes || !this.ctx) return;
    const c = this.ctx, g = c.createGain(), now = c.currentTime;
    g.gain.setValueAtTime(0.0001, now); g.gain.exponentialRampToValueAtTime(0.16, now + 0.2);
    const oscs = [[this.hz, 'triangle', 0.5], [this.hz * 1.5, 'triangle', 0.22], [this.hz / 2, 'sine', 0.4]].map(([f, type, amp]) => {
      const o = c.createOscillator(), og = c.createGain(); o.type = type; o.frequency.value = f; og.gain.value = amp;
      o.connect(og); og.connect(g); o.start(); return o;
    });
    g.connect(c.destination); this.nodes = { g, oscs };
  },
  stopDrone() {
    if (!this.nodes) return;
    const { g, oscs } = this.nodes, c = this.ctx, now = c.currentTime;
    g.gain.cancelScheduledValues(now); g.gain.setValueAtTime(Math.max(g.gain.value, 0.0001), now);
    g.gain.exponentialRampToValueAtTime(0.0001, now + 0.2); oscs.forEach(o => o.stop(now + 0.25)); this.nodes = null;
  },
  tick() {
    const a = this.audio();
    if (!this.on || !a || a.paused || !this.bpm || !this.ctx) return;
    const period = 60 / this.bpm, t = a.currentTime, ahead = 0.12;
    let k = Math.ceil((t - this.phase) / period - 1e-6);
    let tb = this.phase + k * period;
    while (tb < t + ahead) {
      if (tb >= t - 0.02 && k > this.last) { this.click(Math.max(0, tb - t)); this.last = k; }
      k++; tb = this.phase + k * period;
    }
  },
  click(delay) {
    const c = this.ctx, o = c.createOscillator(), g = c.createGain(), at = c.currentTime + delay;
    o.frequency.value = 1000; g.gain.setValueAtTime(0.0001, at);
    g.gain.exponentialRampToValueAtTime(0.7, at + 0.002); g.gain.exponentialRampToValueAtTime(0.0001, at + 0.05);
    o.connect(g); g.connect(c.destination); o.start(at); o.stop(at + 0.06);
  },
};
"""

# Gradio 會依系統設定加上 .dark；現場多半在明亮空間，固定亮色。
_LIGHT_BODY = """
  const light = () => {
    document.documentElement.classList.remove('dark');
    document.body.classList.remove('dark');
  };
  const zh = { 'Drop Audio Here': '把音檔拖到這裡', 'Click to Upload': '點一下選檔', '- or -': '或', 'or': '或' };
  const localize = () => {
    const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    for (let n = w.nextNode(); n; n = w.nextNode()) {
      const k = n.nodeValue.trim();
      if (zh[k]) n.nodeValue = zh[k];
    }
  };
  light(); localize();
  new MutationObserver(localize).observe(document.body, { childList: true, subtree: true });
  const opts = { attributes: true, attributeFilter: ['class'] };
  new MutationObserver(light).observe(document.body, opts);
  new MutationObserver(light).observe(document.documentElement, opts);
"""

# 頁面載入時執行：節拍器 + 固定亮色 + 上傳區中文化
FORCE_LIGHT_JS = "() => {\n" + METRO_JS + _LIGHT_BODY + "\n}"

# 結果回來後自己播一次。不用 Gradio 內建的 autoplay：它在不同瀏覽器上會對同一個聲音播兩次。
PLAY_JS = """(a) => {
  const url = a && (a.url || a.path);
  if (!url) return;
  if (window.__ppAudio) { try { window.__ppAudio.pause(); } catch (e) {} }
  const au = new Audio(url);
  window.__ppAudio = au;
  au.play().catch(() => {});
}"""

METRO_LOAD_JS = "(a, bpm, phase, hz, key) => { window.ppMetro.load(a && (a.url || a.path), bpm, phase, hz, key); }"

METRO_HTML = """
<div id="pp-metro" class="pp-metro">
  <audio id="pp-metro-audio" controls preload="auto"></audio>
  <label class="pp-switch">
    <input type="checkbox" onchange="ppMetro.setOn(this.checked)">
    <span class="pp-switch-track"><span class="pp-switch-knob"></span></span>
    <span class="pp-switch-label">節拍 開／關</span>
  </label>
  <label class="pp-switch">
    <input type="checkbox" onchange="ppMetro.setDrone(this.checked)">
    <span class="pp-switch-track"><span class="pp-switch-knob"></span></span>
    <span class="pp-switch-label" id="pp-drone-label">主音 開／關</span>
  </label>
  <p id="pp-metro-info" class="pp-hint">上傳歌曲後按上方「載入整首歌」。載入後按播放，再用下面的開關在播放中隨時打開或關掉節拍與主音。</p>
</div>
"""

MASTHEAD = """
<div class="pp-masthead">
  <svg class="pp-logo" viewBox="0 0 48 48" role="img" aria-label="PitchPal">
    <rect width="48" height="48" rx="10" fill="#C8321A"/>
    <ellipse cx="19" cy="34" rx="8.5" ry="6" transform="rotate(-20 19 34)" fill="#fff"/>
    <rect x="25.5" y="9" width="3.6" height="25" fill="#fff"/>
    <path d="M29 9 C 36 12 38 17 36 23 C 35 19 33 17 29 16 Z" fill="#fff"/>
  </svg>
  <div class="pp-brand">
    <h1>PitchPal</h1>
    <p>辨調、調 KEY、Capo 建議、旋律試聽</p>
  </div>
</div>
<svg class="pp-staff" viewBox="0 0 100 20" preserveAspectRatio="none" aria-hidden="true">
  <g stroke="#16130f" stroke-width="0.5" vector-effect="non-scaling-stroke" opacity="0.35">
    <line x1="0" y1="2" x2="100" y2="2" vector-effect="non-scaling-stroke"/>
    <line x1="0" y1="6" x2="100" y2="6" vector-effect="non-scaling-stroke"/>
    <line x1="0" y1="10" x2="100" y2="10" vector-effect="non-scaling-stroke"/>
    <line x1="0" y1="14" x2="100" y2="14" vector-effect="non-scaling-stroke"/>
    <line x1="0" y1="18" x2="100" y2="18" vector-effect="non-scaling-stroke"/>
  </g>
</svg>
"""

CSS = """
:root { --ink: #16130f; --muted: #57514a; --accent: #C8321A; --line: #16130f; }
.gradio-container { max-width: 1040px !important; margin: auto; font-size: 17px; color: var(--ink); }
footer { display: none !important; }

/* 字標：徽章 + 字標 + 五線譜 */
.pp-masthead { display: flex; align-items: center; gap: 14px; padding: 12px 0 4px; }
.pp-logo { width: 48px; height: 48px; flex: none; }
.pp-brand h1 { margin: 0; font-size: 1.9rem; font-weight: 900; line-height: 1.05; letter-spacing: 0; }
.pp-brand p { margin: 2px 0 0; color: var(--muted); font-size: 1rem; }
.pp-staff { display: block; width: 100%; height: 22px; border-bottom: 3px solid var(--line); margin-bottom: 2px; }

/* 分頁 */
.tab-nav, div[role="tablist"] { border-bottom: 2px solid var(--line) !important; }
.tab-nav button, div[role="tablist"] button { font-size: 1.05rem !important; font-weight: 700 !important;
  padding: 10px 16px !important; color: var(--muted) !important; }
.tab-nav button.selected, div[role="tablist"] button.selected, button[role="tab"][aria-selected="true"] { color: var(--ink) !important;
  border-bottom: 4px solid var(--ink) !important; font-weight: 900 !important; }
button[role="tab"][aria-selected="false"] { color: #6b645c !important; font-weight: 600 !important; }
.tabs, .tabitem { padding-left: 0 !important; padding-right: 0 !important; }

/* 區塊小標：粗線 + 實心字，不用側邊色條 */
.section-header, .section-header p { font-size: 1.1rem; font-weight: 800; color: var(--ink);
  margin: 18px 0 8px !important; }
.section-header { border-bottom: 2px solid var(--line); padding-bottom: 6px; margin-bottom: 0 !important; }
.pp-hint, .pp-hint p { margin: 2px 0 !important; }
input[type="number"] { font-size: 1.1rem !important; font-weight: 700 !important; min-width: 64px; }

/* 上傳區要看得出邊界 */
.pp-upload { border: 2px dashed var(--line) !important; border-radius: 8px !important; min-height: 140px; }

/* 琴鍵音階圖 */
.pp-kb { padding: 6px 2px 2px; }
.pp-kb-cap { font-size: 0.95rem; font-weight: 700; color: var(--muted); margin-bottom: 6px; }
.pp-kb-svg { display: block; width: 100%; height: auto; max-width: 440px; }

/* 整首對拍 */
.pp-metro { margin: 4px 0 10px; }
.pp-metro audio { width: 100%; height: 48px; }
.pp-switch { display: flex; align-items: center; gap: 12px; min-height: 48px; cursor: pointer; font-weight: 800; font-size: 1.1rem; }
.pp-switch input { position: absolute; opacity: 0; width: 1px; height: 1px; }
.pp-switch-track { width: 60px; height: 34px; border: 3px solid var(--ink); border-radius: 17px; background: #fff; position: relative; flex: none; transition: background 0.15s ease-out; }
.pp-switch-knob { position: absolute; top: 3px; left: 3px; width: 22px; height: 22px; border-radius: 50%; background: var(--ink); transition: transform 0.15s ease-out; }
.pp-switch input:checked + .pp-switch-track { background: var(--accent); border-color: var(--accent); }
.pp-switch input:checked + .pp-switch-track .pp-switch-knob { transform: translateX(26px); background: #fff; }
.pp-switch input:focus-visible + .pp-switch-track { outline: 3px solid var(--accent); outline-offset: 3px; }

/* 五線譜 */
.pp-staff-svg { display: block; max-width: 100%; height: auto; margin: 0 0 6px; }

/* 吉他指板 */
.pp-frets { display: flex; flex-wrap: wrap; gap: 14px 18px; padding: 4px 2px 2px; }
.pp-fret { margin: 0; width: 132px; }
.pp-fret svg { display: block; width: 100%; height: auto; }
.pp-fret figcaption { text-align: center; font-size: 0.95rem; line-height: 1.35; margin-top: 2px; }

/* 樂器語彙：降／升半音像一白一黑的琴鍵；分頁以小節線分隔 */
button.pp-key-white { background: #fff !important; border-radius: 0 0 12px 12px !important; border-width: 2px !important; min-height: 64px !important; }
button.pp-key-black { background: var(--ink) !important; color: #fff !important; border-radius: 0 0 10px 10px !important; border: 2px solid var(--ink) !important; min-height: 64px !important; }
button.pp-key-black:hover { background: #3a342d !important; }
button[role="tab"] + button[role="tab"] { border-left: 2px solid var(--ink) !important; margin-left: 4px; }
.pp-preview { margin-top: 10px; }

/* 單選群組：橫向排列、等寬按鈕 */
.gradio-container .wrap[role="radiogroup"], .gradio-container fieldset .wrap, .gradio-container .block:has(input[type="radio"]) .wrap { display: flex !important; flex-wrap: wrap; gap: 8px; }
.gradio-container .block:has(input[type="radio"]) label { min-width: 84px; justify-content: center; text-align: center; }

/* 結果欄：大字、無外框，像譜上的標題列 */
.pp-big label > span, .pp-big .label-wrap span { font-size: 0.95rem !important; font-weight: 700 !important;
  color: var(--muted) !important; }
.pp-big textarea, .pp-big input[type="text"] { background: transparent !important; box-shadow: none !important;
  border: 0 !important; border-bottom: 2px solid var(--line) !important; border-radius: 0 !important;
  padding: 4px 0 !important; color: var(--ink) !important; -webkit-text-fill-color: var(--ink); opacity: 1 !important; }
.pp-key textarea, .pp-key input[type="text"] { font-size: 3.8rem !important; font-weight: 900 !important; line-height: 1.2 !important; }
.pp-key-target textarea, .pp-key-target input[type="text"] { color: #a82813 !important; -webkit-text-fill-color: var(--accent); }
.pp-bpm textarea, .pp-bpm input[type="text"] { font-size: 2.4rem !important; font-weight: 800 !important; }
.pp-note textarea, .pp-note input[type="text"] { font-size: 1.05rem !important; font-weight: 600 !important; }
.pp-small textarea, .pp-small input[type="text"] { font-size: 0.95rem !important; font-weight: 500 !important; }
.pp-capo textarea { font-size: 1.2rem !important; font-weight: 700 !important; line-height: 1.6 !important; }
.pp-big textarea::placeholder, .pp-big input::placeholder { color: #6b645c; font-weight: 500; }

/* Gradio 內建元件：標籤、數字框、滑桿端點、單選 */
.gradio-container label > span, .gradio-container .block-title, .gradio-container .block-info { font-size: 0.95rem !important;
  font-weight: 700 !important; color: var(--muted) !important; }
.gradio-container .slider_input_container span, .gradio-container .range_input span { font-size: 0.9rem !important; color: var(--muted) !important; }
.gradio-container input[type="radio"] + span, .gradio-container .wrap label span { font-size: 1.05rem !important; }
.gradio-container ::placeholder { color: #6b645c !important; opacity: 1; }
.pp-upload, #pp-upload { --pp-tap: 44px; }
#pp-upload button { min-width: var(--pp-tap) !important; min-height: var(--pp-tap) !important; font-size: 0.95rem !important; }
#pp-upload .time, #pp-upload .timestamps, #pp-upload span, #pp-upload time { font-size: 0.9rem !important; color: var(--muted) !important; }
#pp-upload .waveform-container, #pp-upload [data-testid="waveform-container"] { max-height: 70px; }
.gradio-container .label-wrap + div, .gradio-container .label { font-size: 0.95rem; }

/* 摺疊區：粗線上下框 + 繪製的箭頭，不用預設 ◀ */
.gradio-container button.label-wrap, .gradio-container .label-wrap {
  border-top: 2px solid var(--line) !important; border-bottom: 2px solid var(--line) !important;
  border-radius: 0 !important; min-height: 48px; padding: 8px 4px !important;
  display: flex !important; align-items: center; justify-content: space-between; font-size: 1.05rem !important; font-weight: 700 !important;
}
.gradio-container .label-wrap .icon { display: none !important; }
.gradio-container .label-wrap::after { content: ""; width: 10px; height: 10px; flex: none; margin-right: 6px;
  border-right: 3px solid var(--ink); border-bottom: 3px solid var(--ink); transform: rotate(45deg); transition: transform 0.15s ease-out; }
.gradio-container .label-wrap.open::after { transform: rotate(-135deg); }

/* 左右欄之間：粗細雙線（小節線） */
@media (min-width: 769px) {
  .pp-cols > div:first-child { border-right: 6px double var(--line); padding-right: 20px; margin-right: 8px; }
}

/* 結果格：譜表頭的格子 */
.pp-key, .pp-bpm { border: 3px solid var(--line) !important; border-radius: 6px !important; padding: 10px 18px 6px !important;
  background: #fff !important; }
.pp-key textarea, .pp-key input[type="text"], .pp-bpm textarea, .pp-bpm input[type="text"] { border-bottom: 0 !important; }
.pp-key-target { border-color: var(--accent) !important; background: #fdf1ee !important; }
.pp-bpm { position: relative; }
.pp-bpm label, .pp-bpm textarea, .pp-bpm input[type="text"] { padding-left: 66px !important; }
.pp-bpm label { display: block; text-align: left; }
.gradio-container .secondary-wrap input { border: 0 !important; box-shadow: none !important; }
.pp-bpm::before { content: ""; position: absolute; left: 18px; top: 50%; width: 52px; height: 52px; transform: translateY(-38%);
  background: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 52 52'><ellipse cx='12' cy='38' rx='9' ry='6.4' transform='rotate(-20 12 38)' fill='%2316130f'/><rect x='19' y='6' width='3.6' height='32' fill='%2316130f'/><rect x='30' y='26' width='16' height='3.4' fill='%2316130f'/><rect x='30' y='36' width='16' height='3.4' fill='%2316130f'/></svg>") no-repeat center / contain; }

/* 輸入、下拉、滑桿、單選：同一套粗框語彙 */
.gradio-container input[type="range"] { accent-color: var(--accent); height: 10px; }
.gradio-container input[type="range"]::-webkit-slider-thumb { width: 28px; height: 28px; }
.gradio-container input[type="range"]::-moz-range-thumb { width: 28px; height: 28px; }
.gradio-container .wrap-inner, .gradio-container .secondary-wrap { border-radius: 8px !important; }
.gradio-container .block:not(.pp-big) input[type="text"], .gradio-container .block:not(.pp-big) textarea,
.gradio-container .secondary-wrap { border: 2px solid var(--line) !important; border-radius: 8px !important; background: #fff !important; box-shadow: none !important; }
.gradio-container input[type="radio"] { accent-color: var(--accent); width: 20px; height: 20px; }
.gradio-container fieldset label, .gradio-container .wrap > label { border: 2px solid var(--line) !important; border-radius: 8px !important;
  background: #fff !important; padding: 10px 16px !important; min-height: 44px; }
.gradio-container label.selected { background: var(--ink) !important; border-color: var(--ink) !important; }
.gradio-container label.selected, .gradio-container label.selected span { color: #fff !important; }

/* 按鈕 */
button.lg, button.primary { min-height: 56px !important; font-size: 1.15rem !important; font-weight: 800 !important;
  box-shadow: none !important; border-radius: 8px !important; }
button.secondary { border: 2px solid var(--ink) !important; font-weight: 700 !important; }
.chord-palette button { min-width: 58px !important; font-size: 0.95rem !important; padding: 8px 4px !important; }
.note-palette button  { min-width: 46px !important; font-size: 1rem !important; padding: 8px 4px !important; font-weight: 700 !important; }
.mod-palette button   { min-width: 54px !important; font-size: 0.9rem !important; padding: 8px 4px !important; }
button { min-height: 44px; }

/* 鍵盤焦點與選取，不用瀏覽器預設 */
:focus-visible { outline: 3px solid var(--accent) !important; outline-offset: 2px; }
::selection { background: #f4b8aa; color: var(--ink); }

/* 說明小字不低於 14px */
.pp-hint, .pp-hint p, .pp-hint small { font-size: 0.9rem !important; color: var(--muted); }
.pp-footer { text-align: center; font-size: 0.9rem; color: var(--muted); padding: 24px 0 8px; }
.pp-footer a { color: var(--ink); }

@media (max-width: 768px) {
  .gradio-container { padding: 8px !important; font-size: 17px; }
  .pp-key textarea, .pp-key input[type="text"] { font-size: 3.4rem !important; }
  .pp-bpm textarea, .pp-bpm input[type="text"] { font-size: 2rem !important; }
  .chord-palette, .note-palette, .mod-palette { flex-wrap: wrap !important; gap: 6px !important; }
  .chord-palette button, .note-palette button, .mod-palette button { flex: 1 1 auto !important; }
  button { min-height: 48px; }
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation: none !important; transition: none !important; }
}
"""
