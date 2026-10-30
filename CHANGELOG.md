# Changelog

格式參考 [Keep a Changelog](https://keepachangelog.com/zh-TW/)，版本遵循 Semantic Versioning。

## [Unreleased]

### 新增
- 畫面改版（「和弦譜表頭」）：白底墨黑粗線、單一朱紅；原曲調性與 BPM 改成最大字，左右兩欄對照「原曲」與「今天要唱」；固定亮色，適合明亮場地；字級與點擊區放大；新增「降／升 1 個半音」按鈕。
- 介面全面中文化（含上傳區提示），移除 emoji 圖示。

### 變更
- 分頁整理為「調 KEY」「旋律試聽」「更多工具」，音頻轉譜（實驗）收進「更多工具」。
- 信心度改以「高／中／低」文字顯示，BPM 與調性的候選提示移到可信度欄。
- 程式拆分：`app.py` 拆出 `synth.py`、`transcribe.py`、`keys.py`、`tmpfiles.py`、`theme.py`。
- 移除已停用的 React 版 `frontend/`、FastAPI 版 `backend/` 與失效的 `tests/test_bdd.py`（正式部署一直是 Gradio 的 `app.py`）。
- 新增 `PRODUCT.md`（使用者與產品原則）與 `DESIGN.md`（改版前的視覺現況基準），作為畫面改版的依據。

### 修正
- 信心度不再永遠顯示 100%：舊公式把 4 段相關係數加總後除以固定值，幾乎一定爆表。改為「第一名與第二名候選的差距」，真的難分時會顯示偏低並列出「也可能是」的調性。
- BPM 不再偏向 120：舊版直接用 `librosa.beat.beat_track`，慢歌常被抓成倍速（例如 68 BPM 顯示 136）。改為從打擊成分的節奏自相關找拍子，並以敬拜曲常見速度當先驗，同時列出半速/倍速的可能值。
- 調性偵測會先校正整首歌的調音偏差；錄音或 YouTube 音檔稍微偏高/偏低時，不再整個差一個半音。
- 調性偵測改取和聲成分（去掉鼓聲干擾），並依響度加權，不再讓靜音雜訊影響結果。

### 變更
- 調性/BPM 偵測抽成獨立模組 `analysis.py`，並新增 `tests/test_analysis.py`。
- 長度超過 3 分鐘的音檔只分析中段 3 分鐘，加快偵測速度。
- Dockerfile 一併複製 `analysis.py`。
