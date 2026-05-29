# PitchPal 專案知識庫

> 此文件紀錄專案從零到現在的完整開發歷程，包含架構設計、技術決策、踩過的坑，供 AI 輔助工具作為知識庫使用。

---

## 1. 專案概述

**名稱**：PitchPal  
**定位**：敬拜帶領者的一站式調 Key 工具  
**部署**：Hugging Face Spaces（Gradio SDK）  
**Repo**：windsjp00171-star/pitchpal  

### 核心使用場景
敬拜帶領者拿到一首歌的音頻或 YouTube 連結，需要知道原曲是什麼 Key、轉成適合會眾音域的 Key、並且能試聽旋律和弦看看感覺對不對，最後下載移調後的音頻帶去現場。

### 目標用戶
教會敬拜團，技術背景不一，介面以繁體中文為主，操作門檻要低。

---

## 2. 技術棧

| 層次 | 技術 |
|---|---|
| 介面 | Python + Gradio 5.9.1 |
| 調性偵測 | librosa（chroma_cens + Krumhansl–Schmuckler） |
| 移調 | librosa.effects.pitch_shift（phase vocoder） |
| 旋律偵測 | librosa.pyin（基頻偵測） |
| 和弦偵測 | librosa.feature.chroma_cqt + 模板比對 |
| 音色合成 | NumPy 加法合成 + Karplus-Strong（scipy.signal.lfilter） |
| 音頻濾波 | scipy.signal.butter / sosfilt |
| 音頻 I/O | soundfile |
| 格式轉換 | ffmpeg（subprocess 呼叫）|
| YouTube 下載 | yt-dlp |
| 雲端資料庫 | Supabase（用於收集調性偵測反饋，選用） |

---

## 3. 專案檔案結構

```
pitchpal/
├── app.py              # 主程式（全部邏輯 + Gradio UI，約 1900 行）
├── requirements.txt    # 依賴套件
├── README.md           # 公開說明文件（HF Spaces 首頁顯示）
├── KNOWLEDGE_BASE.md   # 本文件（開發知識庫）
├── CLAUDE.md           # AI 工具的專案指引
└── .gitignore
```

### 為什麼全部放在一個 app.py？

Hugging Face Spaces 的 Gradio SDK 預設單一入口檔。專案規模在可維護範圍內，拆模組反而增加 import 複雜度，且 HF 環境下路徑管理麻煩。目前維持單檔，未來如超過 3000 行再考慮拆分。

---

## 4. app.py 架構分層

```
app.py
├── [imports & 全域初始化]
│   ├── gradio_client patch（修 5.9.x boolean schema bug）
│   ├── 暫存檔管理系統（_reg_tmp / _sweep_tmp / atexit cleanup）
│   └── Supabase 連線（lazy init，讀環境變數）
│
├── [常數與對照表]
│   ├── MAJOR_KEYS / MINOR_KEYS / ALL_KEYS
│   ├── KEY_DISPLAY（enharmonic 顯示用：C# → C#/Db）
│   ├── NOTE_MAP（音名 → 半音數，含異名同音）
│   ├── JIANPU_INTERVALS（數字 → 音程）
│   ├── MELODY_KEY_ROOTS（調性 → MIDI 根音）
│   ├── _CHORD_ROOTS（根音解析，長串優先避免 C 吃掉 C#）
│   ├── _CHORD_QUALITIES（和弦音程表）
│   └── FFMPEG_CONVERT_EXTS / VIDEO_EXTS（格式分類）
│
├── [調性偵測模組]
│   ├── _KS_MAJOR / _KS_MINOR（Krumhansl–Schmuckler 輪廓）
│   ├── _ks_scores()
│   ├── detect_key()
│   └── result_key() / capo_suggestions()
│
├── [音頻處理模組]
│   ├── _prepare_audio()（格式判斷 + ffmpeg 預轉換）
│   ├── _extract_audio_from_video()
│   ├── transpose_audio()（主移調函數）
│   ├── _write_wav() / _convert_to_mp3()
│   └── _safe_stem()（檔名清理）
│
├── [音色合成模組]
│   ├── _tone_piano() — 加法合成，諧波差異衰減
│   ├── _tone_guitar() — Karplus-Strong + 鋸齒激勵
│   ├── _tone_flute() — 基音主導 + 顫音 + 呼吸雜訊
│   ├── _tone_organ() — Drawbar 風格持音
│   ├── _tone_harp() — Karplus-Strong + 短回聲
│   ├── _tone_violin() — 弓擦雜訊 + 漸增顫音
│   ├── _tone()（dispatch 函數）
│   └── _lowpass() / TIMBRE_CUTOFF（各音色截止頻率）
│
├── [簡譜合成模組]
│   ├── parse_and_synth()（主入口）
│   ├── _synth_chord_sequence()
│   ├── _synth_chord_block()
│   ├── _parse_chord_token()
│   ├── _click_track()（節拍器）
│   └── _rest()
│
├── [音頻轉譜模組]
│   ├── transcribe_audio()
│   ├── _midi_to_jianpu()
│   └── _build_chord_templates()
│
├── [UI 互動輔助]
│   ├── _apply_quality_mod()（和弦色彩調整）
│   ├── _make_cq_handler() / _make_note_handler()（閉包工廠）
│   ├── toggle_sharp/flat/high/low()
│   ├── append_melody_modifier()
│   ├── get_diatonic_chords()
│   ├── play_chord_audio()
│   └── on_chord_palette_btn()
│
├── [YouTube 下載]
│   └── download_youtube()（多策略重試 + timeout）
│
└── [Gradio UI 定義]
    ├── Tab 1：調 KEY 工具
    ├── Tab 2：旋律試聽
    └── Tab 3：音頻轉譜（實驗）
```

---

## 5. 核心演算法說明

### 5.1 調性偵測（Krumhansl–Schmuckler）

1. 載入音頻，裁掉首尾靜音（`librosa.effects.trim`）
2. 跳過前後各 10%，取中間 80%（避免前奏/尾奏干擾）
3. 切成 4 段，各自計算 `chroma_cens`（比 chroma_cqt 更抗雜訊）
4. 對每段的 chroma 均值，與 12 個移位的 KS 大調/小調輪廓做 Pearson 相關係數
5. 加總 4 段分數，取最大值決定調性
6. 信心度 = `(最佳分數 - 其餘平均) / (0.35 × 4) × 100`，clamp 到 0–100

**設計取捨**：chroma_cens 對音高有一定容錯，在有混響或多軌混音時比 CQT 穩定，但對快速轉調的曲子準確度會下降。

### 5.2 移調（Phase Vocoder）

```python
librosa.effects.pitch_shift(y, sr=sr, n_steps=steps, bins_per_octave=12)
```

`bins_per_octave=12` 表示 `n_steps=1` = 1 個半音。`n_fft` 使用 librosa 預設（2048），平衡時間與頻率解析度。

**重要**：不傳入 `n_fft` 或傳 2048；傳 8192 會造成時間解析度過差，音頻聽起來悶濁（相位聲碼器 temporal smearing）。

### 5.3 Karplus-Strong 弦樂合成

吉他與豎琴使用 Karplus-Strong 演算法：
1. 以噪訊（或噪訊+鋸齒）填充一個音高週期的緩衝區作為激勵
2. 通過 IIR 低通迴授濾波器循環：`y[n] = x[n] + coeff×0.5×y[n-period] + coeff×0.5×y[n-period-1]`
3. `coeff` 接近 1.0（0.994–0.999），控制衰減速度
4. 低通特性使高頻先衰減，模擬真實撥弦

### 5.4 和弦解析優先順序

`_CHORD_ROOTS` 列表把多字元根音（C#、Db、D#…）排在單字元（C、D、E…）之前，避免 `C#m7` 被解析成根音 `C` + quality `#m7`（無效）。

```python
# 錯誤示範（單字元在前）: "C#m7" → root=C, quality="#m7" ← 找不到
# 正確（多字元在前）:       "C#m7" → root=C#, quality="m7" ✓
```

---

## 6. 踩過的坑（Bug 歷程）

### 🐛 坑 1：git history 有 binary 檔案，HF Spaces push 失敗

**症狀**：`git push huggingface` 卡住或拒絕，顯示 LFS 相關錯誤  
**原因**：`PRODUCT.pdf` 被 commit 進 git history  
**修法**：在使用者本機執行 `python -m git_filter_repo --path PRODUCT.pdf --invert-paths --force` 重寫 history，再 force push  
**學到**：`.gitignore` 要在第一次 commit 前設好；binary 檔一旦進 history，只能用 filter-repo 清除

---

### 🐛 坑 2：Gradio 4.x 在 Python 3.13 崩潰（distutils 移除）

**症狀**：HF Spaces build 失敗，`ModuleNotFoundError: No module named 'distutils'`  
**原因**：Gradio 4.0.0 依賴 distutils，Python 3.13 已移除  
**修法**：`README.md` 的 `sdk_version` 從 `"4.0.0"` 改成 `"5.9.1"`，`requirements.txt` 加 `setuptools`  
**學到**：HF Spaces 的 Python 版本由 `sdk_version` 間接決定，不可忽略

---

### 🐛 坑 3：所有音色聽起來一模一樣

**症狀**：切換鋼琴/吉他/長笛，聲音幾乎沒差異  
**原因（雙重）**：
1. `_synth_chord_block` 硬寫 `_tone_piano()`，完全忽略傳入的 `timbre` 參數
2. 全域低通濾波器截止頻率 3500Hz，把所有音色的特徵頻段都削掉了

**修法**：
1. `_synth_chord_block` 改用 `_tone(freq, duration, sr, timbre, rng)`
2. 各音色獨立截止頻率（`TIMBRE_CUTOFF` dict），最高到 10000Hz（豎琴）

---

### 🐛 坑 4：和弦 CQ 按鈕標籤對應錯誤

**症狀**：點「7 藍調」實際作用的是 maj7，點「sus4」作用的是 sus2，依此類推全部位移  
**原因**：`_CQ_LABELS` 列表有 9 個標籤，但 `_cq_btns` 列表漏掉了「m7 小七」按鈕，只有 8 個元素，`zip()` 配對從第三個開始全部錯位  
**修法**：補齊所有 9 個按鈕，確保 `len(_CQ_LABELS) == len(_cq_btns)`

---

### 🐛 坑 5：`.opus` 音頻移調音高錯誤

**症狀**：上傳 opus 格式，移調後音高偏移，與預期不符  
**原因**：`.opus` 不在 `VIDEO_EXTS` 集合內，直接被 `librosa.load(sr=None)` 讀取。librosa 底層用 soundfile 讀 opus，取得的 sample rate 可能與實際播放 sample rate 不符  
**修法**：新增 `FFMPEG_CONVERT_EXTS = {".opus", ".ogg", ".webm", ".aac", ".wma", ".flac"}`，這些格式先用 ffmpeg 轉成 44100Hz WAV 再讓 librosa 處理

---

### 🐛 坑 6：移調音高全部偏差（最嚴重）

**症狀**：F 調移到 G（+2 半音）出來是 F#，+3 也是 F#，-3 是 D# 而非 D  
**原因**：`bins_per_octave=24` 導致 `n_steps=1` 實際只移半個半音（四分音）。完整公式：`rate = 2^(-n_steps / bins_per_octave)`，bins_per_octave=24 時 n_steps=2 才等於 1 個半音  
**修法**：`bins_per_octave=24` → `bins_per_octave=12`（librosa 預設，n_steps=1 就是 1 個半音）  
**為什麼當初有 24**：配合更精細的頻率解析度加入，但這個設定改變了 n_steps 的語意，根本是錯的

---

### 🐛 坑 7：`_ 八分` `__ 十六` `. 附點` 按鈕無效

**症狀**：在旋律試聽頁面，輸入 `6` 再點 `_ 八分`，文字框變成 `6 _`，生成出來的音符時值沒有改變  
**原因**：`append_melody_modifier()` 對非 `-` 的字元都加空格前綴。`6 _` 被 tokenizer 分割成 `["6", "_"]`，`_` 不是合法音符 token，被 `continue` 跳過  
**修法**：`-`、`_`、`__`、`.` 都走 no-space 路徑（直接貼附），只有 `|` 保留空格

---

### 🐛 坑 8：移調後音頻聽起來悶濁

**症狀**：移調輸出的音頻比原音悶，高頻細節消失  
**原因**：`n_fft=8192` 讓 phase vocoder 使用超大時間窗，頻率解析度高但時間解析度差，造成瞬態（人聲子音、鼓擊）模糊，整體聽感悶  
**修法**：移除 `n_fft=8192`，使用 librosa 預設值（2048）

---

### 🐛 坑 9：移調後播放器空白

**症狀**：進度條跑完，播放器沒有出現音頻  
**原因**：`show_progress="full"` 在伺服器函數執行時清空輸出元件，函數返回後伺服器端處理完畢，但瀏覽器還在下載音頻檔。這段時間播放器是空的，視覺上像是「完成了但什麼都沒有」  
**修法**：改為 `show_progress="minimal"`，讓播放器自身顯示 loading 狀態而不被清空

---

## 7. 設計決策記錄

### 為什麼用半音滑桿而不是「選目標 Key」下拉選單？

下拉選單需要使用者知道目標 Key 是什麼，敬拜帶領者有時只知道「升一個 Key」或「降兩個 Key」而不知道具體音名。半音數滑桿更直觀，且移調後調性會即時顯示，兩種需求都滿足。

### 為什麼保留手動修正原 Key？

自動偵測在人聲主導、有混響、多次轉調的詩歌（敬拜音樂常見）準確率會下降。提供 override 讓使用者不需要重新上傳，只需修正 Key 再移調。override 只影響顯示標籤和 Capo 建議，不影響實際移調半音數（使用者自己設定）。

### 為什麼音色合成用加法合成而不用 sample？

HF Spaces 無法打包音頻樣本，加法合成完全在 NumPy 中執行，無需外部檔案，且效果對試聽用途已足夠。Karplus-Strong 對吉他/豎琴有明顯的撥弦質感。

### 為什麼有暫存檔管理系統（_reg_tmp）？

HF Spaces 是無狀態服務，每次移調/合成都產生暫存 WAV 檔。如果不清理，磁碟會慢慢被佔滿。採用 atexit 確保程式結束時清除，另加背景 thread 每小時清除超過 2 小時的舊檔。

### YouTube 下載為何標記「實驗性」？

雲端伺服器 IP 常被 YouTube 列入封鎖名單，成功率不穩定。程式實作了 5 種 player_client 策略（tv_embedded、mweb、ios、android、web）依序嘗試，並設 90 秒整體 timeout，但本質上穩定性受 YouTube 政策影響，非程式端可控。

### 節拍器為何分強拍/弱拍兩種頻率？

強拍（每小節第一拍）用 1000Hz，弱拍用 800Hz，讓使用者聽音就能感受拍子結構，不只是等間隔的 tick。音量獨立調整（0.05–0.6）讓旋律不被蓋過。

---

## 8. 已知限制與未來方向

### 已知限制
- **調性偵測**：多次轉調、純人聲、高混響的曲目準確率較低（60–70% 估計）
- **音色合成**：加法合成離真實樂器仍有差距；豎琴目前偏乾，小提琴偏假
- **音頻轉譜**：pyin 對多聲部、有和聲的音頻效果差，定位為粗稿工具
- **YouTube 下載**：雲端環境成功率約 40–60%

### 潛在改進方向
- 導入 CREPE 或 PYIN 以外的 F0 估計模型提升轉譜準確度
- 音色加入 reverb/chorus 效果讓試聽更真實
- 調性偵測加入 Essentia 或 key_krumhansl_poly 比對多音軌

---

## 9. 部署資訊

**平台**：Hugging Face Spaces  
**Branch 策略**：在 `claude/fix-push-error-peiu0` 開發，本機用以下指令部署：

```bash
git pull origin claude/fix-push-error-peiu0
git push huggingface HEAD:main --force
```

**環境變數**（HF Spaces Secrets）：
- `SUPABASE_URL`：Supabase 專案 URL（可選，用於調性反饋收集）
- `SUPABASE_KEY`：Supabase anon key（可選）

ffmpeg 在 HF Spaces 環境預設已安裝，yt-dlp 透過 `requirements.txt` 安裝。
