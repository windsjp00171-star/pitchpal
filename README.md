---
title: PitchPal 敬拜移調工具
emoji: 🎵
colorFrom: yellow
colorTo: orange
sdk: gradio
sdk_version: "5.9.1"
app_file: app.py
pinned: false
license: mit
---

# PitchPal — 敬拜移調 × 旋律試聽工具

專為敬拜帶領者設計：上傳音頻 → 偵測 Key → 移調下載，或直接用數字簡譜 + 和弦試聽編排。

## 功能

**🎼 移調工具**
- 上傳音頻（MP3、WAV、M4A 等），自動偵測原曲 Key
- 選目標 Key，一鍵移調並下載（WAV / MP3 / MP4）
- 同步顯示各把位 Capo 建議

**🎵 旋律試聽**
- 數字簡譜輸入（1–7），支援升降音、高低八度、延音、小節線
- 和弦進行輸入，支援 7、maj7、sus4、add9 延伸音
- 鋼琴 / 吉他音色，可調 BPM、八度、調性、拍號

## 使用方式

1. **移調**：上傳檔案 → 自動分析 → 設定目標 Key → 生成下載
2. **試聽**：點擊音符和弦按鈕組合 → 設定參數 → 生成試聽

## 免責聲明

YouTube 連結功能僅供個人學習與敬拜預備使用，請遵守著作權法規，使用者自行承擔相關責任。

## 技術棧

Python · Gradio 5.9.1 · librosa · soundfile · pydub · yt-dlp
