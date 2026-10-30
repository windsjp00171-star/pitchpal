---
name: PitchPal
description: 敬拜帶領者的辨調與調 KEY 工具：白紙、墨黑粗線、單一朱紅，結果像和弦譜的表頭。
colors:
  ink: "#16130f"
  paper: "#ffffff"
  vermilion: "#C8321A"
  vermilion-deep: "#b02d17"
  muted-ink: "#57514a"
  placeholder: "#6b645c"
  selection: "#f4b8aa"
typography:
  display-key:
    fontFamily: "Noto Sans TC, PingFang TC, Microsoft JhengHei, ui-sans-serif, system-ui, sans-serif"
    fontSize: "4.2rem"
    fontWeight: 900
    lineHeight: 1.2
  display-bpm:
    fontFamily: "Noto Sans TC, PingFang TC, Microsoft JhengHei, ui-sans-serif, system-ui, sans-serif"
    fontSize: "2.4rem"
    fontWeight: 800
  masthead:
    fontFamily: "Noto Sans TC, PingFang TC, Microsoft JhengHei, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 900
    lineHeight: 1.1
  section:
    fontFamily: "Noto Sans TC, PingFang TC, Microsoft JhengHei, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.1rem"
    fontWeight: 800
  body:
    fontFamily: "Noto Sans TC, PingFang TC, Microsoft JhengHei, ui-sans-serif, system-ui, sans-serif"
    fontSize: "17px"
    fontWeight: 400
  label:
    fontFamily: "Noto Sans TC, PingFang TC, Microsoft JhengHei, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.95rem"
    fontWeight: 700
  hint:
    fontFamily: "Noto Sans TC, PingFang TC, Microsoft JhengHei, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.9rem"
    fontWeight: 400
rounded:
  control: "8px"
spacing:
  container-max: "1040px"
  tap-min: "44px"
  tap-primary: "56px"
components:
  button-primary:
    backgroundColor: "{colors.vermilion}"
    textColor: "{colors.paper}"
    rounded: "{rounded.control}"
    height: "56px"
  button-primary-hover:
    backgroundColor: "{colors.vermilion-deep}"
  button-secondary:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    height: "44px"
---

# Design System: PitchPal

## Overview

**Creative North Star: "The Chart Header"**

結果就是和弦譜最上方的標題列：原曲調性與 BPM 是整頁最大的字，目標調性是唯一的紅。白紙、墨黑、粗黑線，沒有卡片、沒有漸層、沒有圖示字元。一頁只有一個主角（KEY），其餘資訊用粗線分段排在它旁邊。

工具在兩種場合被使用：電腦上備課，手機上現場臨時查。所以字大、點擊區大、對比高，固定亮色（不跟系統暗色），適合明亮的教會場地。

**Key Characteristics:**
- 墨黑 2–3px 粗線當分隔，取代卡片與陰影。
- 單一朱紅，只給「移調後調性」與主要按鈕。
- 結果格（原曲調性、速度、移調後調性）是 3px 墨黑框的大字格，像譜表頭的格子；目標調性格改朱紅框、淡朱紅底。
- 字標旁有朱紅圓角徽章（繪製的四分音符），下方是五線譜細線與 3px 粗線；速度格左側有繪製的「♩=」速度記號（SVG，非字元）。
- 沒有 emoji 當圖示；狀態用字說明（高／中／低）。
- 固定亮色，忽略系統暗色模式。

## Colors

墨與紙，加一個紅。

### Primary
- **Vermilion** (#C8321A)：移調後調性、主要按鈕、滑桿與選取、鍵盤焦點環。對白底對比約 5.3:1。

### Neutral
- **Ink** (#16130f)：所有主要文字與粗分隔線。
- **Paper** (#ffffff)：全部背景。
- **Muted Ink** (#57514a)：欄位標籤與說明小字。
- **Placeholder** (#6b645c)：未填的佔位文字，對白底約 5.8:1。

### Named Rules
**The One Red Rule.** 朱紅只出現在「今天要唱」的結果與動作上；原曲側一律墨黑。紅色的稀少就是它的意義。

## Typography

**Font:** Noto Sans TC，後備 PingFang TC、微軟正黑體、系統無襯線字。單一字族，靠粗細與大小分層。

### Hierarchy
- **Display Key** (900, 4.2rem（手機 3.4rem）, 1.2)：原曲與目標調性。
- **Display BPM** (800, 2.4rem)：速度。
- **Masthead** (900, 1.5rem)：字標 PitchPal。
- **Section** (800, 1.1rem)：「音源」「原曲」「今天要唱」。
- **Body** (400, 17px)：一般文字、按鈕外的所有說明。
- **Label** (700, 0.95rem, 中灰)：欄位標籤。
- **Hint** (400, 0.9rem)：次要說明，不再小於 14px。

### Named Rules
**The No-Tiny-Type Rule.** 任何可讀文字不小於 14px；核心結果（調性、BPM）不小於 2.4rem。

## Layout

單欄容器，最大寬 1040px。上方「音源」全寬；下方左右兩欄：左「原曲」、右「今天要唱」。768px 以下堆疊，左欄先、右欄後。欄與欄、區與區都用 2px 墨黑底線分隔，不用留白當唯一分隔。兩欄之間（桌面）是一條粗細雙線，像小節線。結果列要在上傳後第一屏看得到：YouTube 與格式說明收在結果下方。

## Elevation & Depth

扁平。沒有陰影；層次靠粗線與字級。只有鍵盤焦點會出現 3px 朱紅外框。

## Shapes

直角為主：結果欄與標題無圓角；按鈕與上傳區 8px；上傳區用 2px 虛線墨框標出可放置範圍。

## Components

### Buttons
- **Primary (開始移調):** 朱紅底白字，高 56px，全寬，字 1.15rem、800。懸停加深。
- **Secondary (降／升 1 個半音、分析、回報修正):** 白底 2px 墨框，字 700，最小高 44px（手機 48px）。
- **半音步進:** 滑桿旁另有「降 1 個半音／升 1 個半音」大按鈕，單手也能精準操作。

### Result Fields
- 3px 墨黑框的格子、大字、字重 900；目標調性格為朱紅框 + 淡朱紅底與朱紅字。速度格左側有速度記號。可信度與提示用 1.05rem、600 的單行。

### Accordions
- 上下各 2px 墨黑線、最小高 48px，右側是繪製的箭頭（開啟時翻轉），不用預設三角形。

### Keyboard Scale
- 一個八度的琴鍵 SVG：音階內的音塗色（原曲墨黑淡色、目標朱紅淡色），主音實心，黑鍵上以白點標示音階音；標題寫出調號。音樂本身就是介面的圖形語言，不是裝飾。

### Radios / Selects
- 單選為橫向排列的 2px 墨框按鈕，選中變墨黑底白字；下拉為單層 2px 墨框。

### Inputs
- 上傳區：2px 墨黑虛線框，最小高 140px，提示文字已中文化。
- 其餘輸入（下拉、滑桿、文字）沿用 Gradio 元件，但套用朱紅選取色與焦點環。

### Navigation
- 三個分頁：調 KEY、旋律試聽、更多工具（音頻轉譜為實驗功能放此）。選中以 4px 墨黑底線與墨黑字表示，未選中為中灰。

## Do's and Don'ts

### Do:
- **Do** 讓 KEY 與 BPM 是畫面最大的字。
- **Do** 不確定時直接寫「也可能是 X」，並提供一步改正的下拉選單。
- **Do** 保持所有可點元素至少 44px 高；主要動作 56px。
- **Do** 保留 `prefers-reduced-motion: reduce` 時關閉所有動畫與轉場。

### Don't:
- **Don't** 用卡片堆疊、漸層、陰影或側邊色條來分區。
- **Don't** 用 emoji 或符號字元當圖示。
- **Don't** 把朱紅用在原曲側或裝飾上。
- **Don't** 跟隨系統暗色模式；現場多在明亮空間。
- **Don't** 用動畫擋住操作或延遲可點擊。
