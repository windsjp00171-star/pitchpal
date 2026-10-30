---
name: PitchPal
description: 敬拜帶領者用的辨調、調 KEY、Capo 建議與旋律試聽工具（改版前基準）
colors:
  night-navy: "#1a1a2e"
  deep-blue: "#16213e"
  ocean-blue: "#0f3460"
  banner-gold: "#f0c040"
  banner-mist: "#a8c5e8"
  amber-accent: "#e6a817"
  amber-text: "#b07d1a"
  tab-border: "#d1d5db"
  tab-hover-bg: "#f9f6f0"
  white: "#ffffff"
typography:
  body:
    fontFamily: "Gradio default (Source Sans Pro, ui-sans-serif, system-ui)"
    fontSize: "16px"
    fontWeight: 400
  banner-title:
    fontFamily: "Gradio default"
    fontSize: "1.8em"
    fontWeight: 700
    letterSpacing: "0.04em"
  section-label:
    fontFamily: "Gradio default"
    fontSize: "0.68em"
    fontWeight: 800
    letterSpacing: "0.12em"
rounded:
  banner: "12px"
  tab: "8px"
spacing:
  container-max: "980px"
---

<!-- BASELINE: 改版前的現況紀錄（2026-10-30）。視覺方向將由 /impeccable 流程重新決定，此檔屆時會被取代。描述用語為觀察所得，未經使用者確認。 -->

# Design System: PitchPal

## Overview

現況是「Gradio 預設主題 + 一條深藍漸層橫幅 + 琥珀色點綴」。介面幾乎沒有自訂的設計系統：元件全是 Gradio 內建，自訂的只有橫幅、分頁標籤、區塊小標與按鈕陰影。密度偏高，一個分頁塞進音源、分析結果、移調滑桿、Capo、回報表單。

**Key Characteristics:**
- 單欄寬度上限 980px，置中。
- 深藍橫幅 + 金色標題，是全站唯一有個性的地方。
- 琥珀色（#e6a817）用於分頁選中線與區塊小標，其餘維持 Gradio 灰白。
- 大量 emoji 當圖示（🎵 🎚️ 🎼 🔍 📂）。
- 行動版只做換行與加大觸控高度（按鈕 min-height 40px）。

## Colors

橫幅是深海軍藍到鈷藍的漸層，其餘是 Gradio 預設的中性灰白。

### Primary
- **Night-to-Ocean Gradient** (#1a1a2e → #16213e → #0f3460, 135°)：只用在頂部橫幅背景。
- **Banner Gold** (#f0c040)：橫幅標題。

### Secondary
- **Amber Accent** (#e6a817)：選中分頁的上緣線、區塊小標左邊線。
- **Amber Text** (#b07d1a)：區塊小標文字。

### Neutral
- **Banner Mist** (#a8c5e8)：橫幅副標。
- **Tab Border** (#d1d5db)、**Tab Hover Paper** (#f9f6f0)：分頁標籤框線與懸停底色。

### Named Rules
**The Banner-Only Rule.** 深色與漸層只出現在橫幅，內容區是 Gradio 預設亮色；兩者之間沒有過渡。

## Typography

**Display / Body Font:** Gradio 預設字體（Source Sans Pro，後備 ui-sans-serif、system-ui），中文由系統字體補。
**Character:** 沒有自訂字體，階層主要靠粗細與 emoji。

### Hierarchy
- **Banner title** (700, 1.8em, 字距 0.04em)：只在橫幅。
- **Section label** (800, 0.68em, 字距 0.12em, 大寫)：區塊小標，字級偏小，是目前最難讀的文字。
- **Body** (400, Gradio 預設 16px)：其餘全部。
- **Mono** (0.9em)：Capo 建議框。

## Layout

單一容器，最大寬 980px。主要分頁用兩欄 Row（左：音源，右：分析結果），768px 以下改為堆疊。和弦／音符調色盤是一排排小按鈕，行動版換行。三個分頁（調 KEY 工具、旋律試聽、音頻轉譜）共用同一容器。

## Elevation & Depth

按鈕有明顯的雙層陰影（`0 3px 8px rgba(0,0,0,0.18), 0 1px 3px rgba(0,0,0,0.12)`），懸停上移 1px、按下下移 1px；分頁標籤有淡上緣陰影。其餘表面扁平。

### Named Rules
**The Lifted-Button Rule.** 只有按鈕與分頁會「浮起」，輸入框與結果框保持扁平。

## Shapes

橫幅圓角 12px，分頁標籤上緣圓角 8px，其餘沿用 Gradio 預設圓角。

## Components

### Buttons
- **Primary / Large:** Gradio 內建樣式 + 上述雙層陰影與 1px 位移回饋。
- **Palette buttons:** 和弦 58px、音符 42px、變音 50px 的最小寬，字級 0.78–0.9em，內距緊（5–6px），觸控區偏小。

### Navigation
- 三個分頁標籤，圓角上緣，選中時加 2px 琥珀上線與淡琥珀光暈，字重加粗。

### Inputs / Fields
- Gradio 預設：Audio 上傳區、Textbox（唯讀結果框）、Dropdown、Slider、Radio。

### 結果顯示
- 原曲調性、信心度（🟢🟡🔴 + 百分比）、BPM、目標調性、Capo 建議各一個唯讀 Textbox。

## Do's and Don'ts

### Do:
- **Do** 保留原有互動結構：分頁、元件順序對應的事件綁定、`elem_classes` 與 `elem_id`（改版時不可破壞）。

### Don't:
- **Don't** 把此檔視為改版目標；這只是改版前的現況快照。
