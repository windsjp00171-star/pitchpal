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
├── synth.py        # 簡譜/和弦合成、音色
├── transcribe.py   # 音頻轉譜（實驗）
├── keys.py         # 音名與調性常數
├── tmpfiles.py     # 暫存檔登記與清理
├── theme.py        # 視覺：Gradio 主題、CSS、字標（見 DESIGN.md）
├── tests/test_analysis.py
├── PRODUCT.md / DESIGN.md
└── CLAUDE.md
```

## 核心邏輯
- `analysis.detect_key` / `detect_bpm` — 和聲成分 + 調音校正（偏差 ≥1/6 半音才套用）+ Krumhansl–Schmuckler 輪廓（色度圖從 C2 起）；信心度為第一名與第二名的差距，並回報「也可能是」候選。BPM 以打擊成分自相關並列出半速/倍速。
- `app.analyze_audio` — 組成介面顯示文字（調性、可信度、BPM）。
- 調性文字格式（如「C#/Db 大調」）被移調與 Capo 邏輯解析，不可改。

## 開發原則
- 保持簡單，不要過度設計
- 介面語言：繁體中文
- 本機執行為主，未來考慮部署到 Hugging Face Spaces
