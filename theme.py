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

# Gradio 會依系統設定加上 .dark；現場多半在明亮空間，固定亮色。
FORCE_LIGHT_JS = """() => {
  const light = () => {
    document.documentElement.classList.remove('dark');
    document.body.classList.remove('dark');
  };
  const zh = { 'Drop Audio Here': '把音檔拖到這裡', 'Click to Upload': '點一下選檔', '- or -': '或' };
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
}"""

MASTHEAD = """
<div class="pp-masthead">
  <h1>PitchPal</h1>
  <p>辨調、調 KEY、Capo 建議、旋律試聽</p>
</div>
"""

CSS = """
:root { --ink: #16130f; --muted: #57514a; --accent: #C8321A; --line: #16130f; }
.gradio-container { max-width: 1040px !important; margin: auto; font-size: 17px; color: var(--ink); }
footer { display: none !important; }

/* 字標 */
.pp-masthead { display: flex; align-items: baseline; gap: 16px; flex-wrap: wrap;
  border-bottom: 3px solid var(--line); padding: 10px 0 10px; margin-bottom: 4px; }
.pp-masthead h1 { margin: 0; font-size: 1.5rem; font-weight: 900; line-height: 1.1; }
.pp-masthead p { margin: 0; color: var(--muted); font-size: 1rem; }

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
#pp-upload { border: 2px dashed var(--line) !important; border-radius: 8px !important; min-height: 140px; }

/* 結果欄：大字、無外框，像譜上的標題列 */
.pp-big label > span, .pp-big .label-wrap span { font-size: 0.95rem !important; font-weight: 700 !important;
  color: var(--muted) !important; }
.pp-big textarea, .pp-big input[type="text"] { background: transparent !important; box-shadow: none !important;
  border: 0 !important; border-bottom: 2px solid var(--line) !important; border-radius: 0 !important;
  padding: 4px 0 !important; color: var(--ink) !important; -webkit-text-fill-color: var(--ink); opacity: 1 !important; }
.pp-key textarea, .pp-key input[type="text"] { font-size: 4.2rem !important; font-weight: 900 !important; line-height: 1.2 !important; }
.pp-key-target textarea, .pp-key-target input[type="text"] { color: var(--accent) !important; -webkit-text-fill-color: var(--accent); }
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
#pp-upload { --pp-tap: 44px; }
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
  .chord-palette, .note-palette, .mod-palette { flex-wrap: wrap !important; gap: 6px !important; }
  .chord-palette button, .note-palette button, .mod-palette button { flex: 1 1 auto !important; }
  button { min-height: 48px; }
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation: none !important; transition: none !important; }
}
"""
