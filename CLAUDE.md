# Worship Key Tool

## 專案簡介
一個音樂 Key 辨別與移調工具，主要給敬拜帶領者使用。
上傳音頻 → 偵測原曲 Key → 移調到目標 Key → 下載。

## 技術棧
- Python + Gradio（介面）
- librosa（Key 偵測 + 移調）
- soundfile（音頻輸出）

## 執行方式
```bash
pip install -r requirements.txt
python app.py
```

打包成 Windows 獨立 EXE：Windows 上執行 `build_exe.bat`（詳見 README.md）。

## 專案結構
```
pitchpal/
├── app.py          # Gradio UI 與事件處理（上傳/移調/YouTube/回報）
├── analysis.py     # 調性與 BPM 偵測（不依賴 Gradio，有測試）
├── bpm_model_data.py  # BPM 樹模型（自動產生，勿手改）
├── synth.py        # 簡譜/和弦合成、音色
├── transcribe.py   # 音頻轉譜（實驗）
├── keys.py         # 音名與調性常數
├── tmpfiles.py     # 暫存檔登記與清理
├── keyboard.py     # 琴鍵音階圖（含五線譜）
├── notation.py     # 五線譜、調號 SVG（Bravura 輪廓）
├── fretboard.py    # Capo 指板圖
├── theme.py        # 視覺：Gradio 主題、CSS、字標（見 DESIGN.md）
├── tests/test_analysis.py
├── PRODUCT.md / DESIGN.md
└── CLAUDE.md
```

## 核心邏輯
- `analysis.detect_key` / `detect_bpm` — 調性：和聲成分 → 調音校正（偏差 ≥1/6 半音才套用）→ 中頻、低音、高音三組色度 → 學出來的 24 調打分模型（`_W`/`_B`，由 `tools/train_key_model.py` 以 GiantSteps 與 GiantSteps-MTG 訓練）；把握度為最高機率，並回報其餘兩個候選。BPM：四種節奏訊號的自相關 → 候選速度 → 訓練好的樹模型（`bpm_model_data.py`，由 `tools/train_bpm_model.py` 產生；純數字、網站不需 scikit-learn）挑最像拍子的那個，並列出機率夠高的其他候選。
- `app.analyze_audio` — 組成介面顯示文字（調性、可信度、BPM）。
- 調性文字格式（如「C#/Db 大調」）被移調與 Capo 邏輯解析，不可改。

## 開發原則
- 保持簡單，不要過度設計
- 介面語言：繁體中文
- 本機執行為主，未來考慮部署到 Hugging Face Spaces
