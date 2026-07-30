---
title: PitchPal
emoji: 🎵
colorFrom: blue
colorTo: purple
sdk: docker
pinned: false
license: mit
---

# PitchPal — 敬拜調性工具

上傳音頻 → 自動偵測 Key → 選目標 Key → 下載移調後音頻。

**支援格式：** mp3、wav、m4a  
**YouTube 音檔？** 先到 [cobalt.tools](https://cobalt.tools) 下載成 mp3 再上傳。

## 本機執行

不想用 Hugging Face Spaces？可以直接在自己電腦上跑：

1. 安裝 [Python 3.11](https://www.python.org/downloads/)
2. 安裝 [ffmpeg](https://ffmpeg.org/download.html) 並加進系統 PATH
3. 在專案資料夾執行：
   ```
   pip install -r requirements.txt
   python app.py
   ```
4. 瀏覽器打開 `http://127.0.0.1:7860` 即可使用

## 打包成 Windows EXE（免裝 Python）

在 Windows 上雙擊 `build_exe.bat`，會自動安裝打包工具並產生獨立執行檔：

- 產出位置：`dist\PitchPal\PitchPal.exe`
- **需另外下載 [ffmpeg.exe](https://www.gyan.dev/ffmpeg/builds/)**（essentials build 裡的 `bin\ffmpeg.exe`），放到 `dist\PitchPal\` 資料夾（跟 `PitchPal.exe` 同一層）——沒有 ffmpeg 一樣能辨調、移調，但無法處理影片或輸出 MP3
- 整個 `dist\PitchPal\` 資料夾可以直接複製給其他人使用，不需要對方安裝 Python
- 執行後一樣是打開瀏覽器連到 `http://127.0.0.1:7860`
