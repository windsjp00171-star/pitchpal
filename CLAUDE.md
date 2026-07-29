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

## 專案結構
```
pitchpal/
├── app.py          # 主程式（Gradio UI + 邏輯）
├── requirements.txt
└── CLAUDE.md
```

## 核心邏輯（app.py）
- `detect_key(audio_path)` — 用 Krumhansl–Schmuckler 音調輪廓法偵測調性
- `transpose_audio(audio_path, detected_key, target_key)` — 計算半音差並呼叫 librosa pitch_shift
- Gradio Blocks UI，上傳後自動觸發 detect_key，按鈕觸發 transpose_audio

## 開發原則
- 保持簡單，不要過度設計
- 介面語言：繁體中文
- 本機執行為主，未來考慮部署到 Hugging Face Spaces

## 跨專案總覽

12 個專案的清冊（用途、部署平台、正式網址、共通地雷）在 **CLAUDE-DESIGN** repo 的
`PROJECTS.md`：https://github.com/windsjp00171-star/CLAUDE-DESIGN/blob/main/PROJECTS.md

需要「其他專案跑在哪、網址是什麼」時去查那份，不要憑印象。
換部署平台或網址時記得回去更新它。
