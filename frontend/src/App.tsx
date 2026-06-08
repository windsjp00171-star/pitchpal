import { useState, useRef, useEffect } from 'react'

const ALL_KEYS = [
  'C 大調','C#/Db 大調','D 大調','D#/Eb 大調','E 大調','F 大調',
  'F#/Gb 大調','G 大調','G#/Ab 大調','A 大調','A#/Bb 大調','B 大調',
  'C 小調','C#/Db 小調','D 小調','D#/Eb 小調','E 小調','F 小調',
  'F#/Gb 小調','G 小調','G#/Ab 小調','A 小調','A#/Bb 小調','B 小調',
]

const MELODY_KEYS = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
const TIMBRES = ['鋼琴', '吉他', '長笛', '管風琴', '豎琴', '小提琴']

type Tab = 'detect' | 'jianpu' | 'transcribe'

// ─── 辨識 Key / 移調 ──────────────────────────────────────────────────────────

function shiftKey(k: string, delta: number) {
  const majorKeys = ALL_KEYS.slice(0, 12)
  const minorKeys = ALL_KEYS.slice(12)
  const isMajor = majorKeys.includes(k)
  const arr = isMajor ? majorKeys : minorKeys
  const idx = arr.indexOf(k)
  if (idx === -1) return k
  return arr[(idx + delta + 12) % 12]
}

function KeyDetectTab() {
  const [file, setFile] = useState<File | null>(null)
  const [originalUrl, setOriginalUrl] = useState('')
  const [detecting, setDetecting] = useState(false)
  const [detectedKey, setDetectedKey] = useState('')
  const [manualKey, setManualKey] = useState('')   // override if detection is wrong
  const [confidence, setConfidence] = useState(0)
  const [capo, setCapo] = useState<{capo: number, shape: string}[]>([])
  const [steps, setSteps] = useState(0)            // semitone slider -12~+12
  const [transposing, setTransposing] = useState(false)
  const [downloadUrl, setDownloadUrl] = useState('')
  const [transposedKey, setTransposedKey] = useState('')
  const [error, setError] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const resultAudioRef = useRef<HTMLAudioElement>(null)

  // effective source key: manual override wins
  const effectiveKey = manualKey || detectedKey

  // derived target key from slider steps
  const targetKey = effectiveKey ? shiftKey(effectiveKey, steps) : ''

  // update capo when target key changes
  useEffect(() => {
    if (!targetKey) return
    fetch(`/api/capo/${encodeURIComponent(targetKey)}`)
      .then(r => r.json()).then(d => setCapo(d.capo || [])).catch(() => {})
  }, [targetKey])

  const reset = () => {
    setFile(null); setOriginalUrl(''); setDetecting(false); setDetectedKey(''); setManualKey('')
    setConfidence(0); setCapo([]); setSteps(0); setTransposing(false)
    setDownloadUrl(''); setTransposedKey(''); setError('')
    if (inputRef.current) inputRef.current.value = ''
  }

  const handleFile = async (f: File) => {
    setFile(f)
    setOriginalUrl(URL.createObjectURL(f))
    setDetecting(true); setDetectedKey(''); setManualKey(''); setConfidence(0); setCapo([])
    setDownloadUrl(''); setTransposedKey(''); setSteps(0); setError('')
    const fd = new FormData(); fd.append('file', f)
    try {
      const res = await fetch('/api/detect', { method: 'POST', body: fd })
      if (!res.ok) throw new Error((await res.json()).detail)
      const data = await res.json()
      setDetectedKey(data.key); setConfidence(data.confidence); setCapo(data.capo || [])
    } catch (e: any) {
      setError(e.message || '偵測失敗')
    } finally {
      setDetecting(false)
    }
  }

  const handleTranspose = async () => {
    if (!file || !effectiveKey || steps === 0) return
    setTransposing(true); setError(''); setDownloadUrl(''); setTransposedKey('')
    const fd = new FormData()
    fd.append('file', file); fd.append('detected_key', effectiveKey); fd.append('target_key', targetKey)
    try {
      const res = await fetch('/api/transpose', { method: 'POST', body: fd })
      if (!res.ok) throw new Error((await res.json()).detail)
      setDownloadUrl(URL.createObjectURL(await res.blob()))
      setTransposedKey(targetKey)
    } catch (e: any) {
      setError(e.message || '移調失敗')
    } finally {
      setTransposing(false)
    }
  }

  useEffect(() => {
    if (downloadUrl && resultAudioRef.current) {
      resultAudioRef.current.play().catch(() => {})
    }
  }, [downloadUrl])

  const isBusy = detecting || transposing

  const confColor = confidence >= 70 ? 'text-green-300' : confidence >= 40 ? 'text-yellow-300' : 'text-red-300'

  return (
    <div className="space-y-4">
      {/* YouTube 提示 */}
      <div className="flex items-start gap-2 rounded-xl bg-amber-50 border border-amber-200 px-4 py-3 text-xs text-amber-800">
        <span className="text-base leading-none mt-0.5">💡</span>
        <span>YouTube 音檔？先到 <a href="https://cobalt.tools" target="_blank" rel="noopener noreferrer" className="underline font-semibold">cobalt.tools</a> 下載成 mp3，再上傳。</span>
      </div>

      {/* ① 上傳區 */}
      <div>
        <label className="block text-sm font-semibold text-gray-700 mb-1.5">① 上傳音檔（mp3 / wav / m4a）</label>
        <div
          onClick={() => !isBusy && inputRef.current?.click()}
          onDragOver={e => e.preventDefault()}
          onDrop={e => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f && !isBusy) handleFile(f) }}
          className={`border-2 border-dashed rounded-xl p-5 text-center cursor-pointer transition-all
            ${isBusy ? 'border-purple-200 bg-purple-50 cursor-not-allowed'
              : file ? 'border-purple-400 bg-purple-50'
              : 'border-gray-200 bg-gray-50 hover:border-purple-400 hover:bg-purple-50'}`}
        >
          <input ref={inputRef} type="file" accept="audio/*" className="hidden"
            onChange={e => { const f = e.target.files?.[0]; if (f) handleFile(f) }} />
          {file
            ? <p className="text-sm font-medium text-purple-700 truncate">🎵 {file.name}</p>
            : <><p className="text-sm text-gray-500">點擊或拖曳上傳</p><p className="text-xs text-gray-400 mt-0.5">mp3 · wav · m4a</p></>
          }
        </div>
        {/* 原音播放器 — 上傳後立即顯示 */}
        {originalUrl && <audio controls src={originalUrl} className="w-full mt-2" />}
      </div>

      {/* ② 偵測結果 + 手動修正 */}
      <div>
        <label className="block text-sm font-semibold text-gray-700 mb-1.5">② 偵測到的 Key</label>
        <div className={`rounded-xl px-5 py-4 flex items-center justify-between transition-all
          ${detectedKey ? 'bg-gradient-to-r from-purple-600 to-violet-500 text-white shadow-sm'
            : 'bg-gray-100 text-gray-400'}`}>
          <div>
            <p className={`text-xs mb-1 ${detectedKey ? 'text-purple-200' : 'text-gray-400'}`}>原曲調性</p>
            <p className="text-3xl font-extrabold tracking-tight">
              {detecting ? <span className="text-lg animate-pulse">偵測中…</span> : detectedKey || '—'}
            </p>
          </div>
          {detectedKey && (
            <div className="text-right">
              <p className="text-xs text-purple-200 mb-1">信心度</p>
              <p className={`text-2xl font-bold ${confColor}`}>{confidence}%</p>
            </div>
          )}
        </div>
        {/* 手動修正：偵測不準時可自行選 */}
        {detectedKey && (
          <div className="mt-2 flex items-center gap-2">
            <span className="text-xs text-gray-400 whitespace-nowrap">偵測不準？手動修正：</span>
            <select
              value={manualKey}
              onChange={e => { setManualKey(e.target.value); setDownloadUrl(''); setTransposedKey(''); setSteps(0) }}
              className="flex-1 rounded-lg border border-gray-200 px-2 py-1.5 text-xs bg-white focus:outline-none focus:ring-2 focus:ring-purple-300"
            >
              <option value="">（使用自動偵測：{detectedKey}）</option>
              {ALL_KEYS.map(k => <option key={k} value={k}>{k}</option>)}
            </select>
          </div>
        )}
      </div>

      {/* Capo 建議（根據目標 Key 動態更新） */}
      {capo.length > 0 && (
        <div className="rounded-xl bg-blue-50 border border-blue-100 px-4 py-3">
          <p className="text-xs font-semibold text-blue-500 mb-2">🎸 吉他 Capo 建議（{targetKey || effectiveKey}）</p>
          <div className="flex flex-wrap gap-2">
            {capo.map(c => (
              <span key={c.capo} className="text-xs bg-white border border-blue-200 rounded-lg px-2.5 py-1 text-blue-700 font-medium">
                {c.capo === 0 ? '不夾 Capo' : `Capo ${c.capo}`} · {c.shape} 指型
              </span>
            ))}
          </div>
        </div>
      )}

      {/* ③ 移調半音 Slider */}
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <label className="text-sm font-semibold text-gray-700">③ 移調半音數</label>
          <span className="text-sm font-bold text-purple-600">
            {steps > 0 ? `+${steps}` : steps} 半音
            {targetKey && effectiveKey && targetKey !== effectiveKey && (
              <span className="ml-2 text-xs font-normal text-gray-500">→ {targetKey}</span>
            )}
            {steps === 0 && effectiveKey && (
              <span className="ml-2 text-xs font-normal text-gray-400">（原調）</span>
            )}
          </span>
        </div>
        <input
          type="range" min={-12} max={12} value={steps}
          onChange={e => { setSteps(+e.target.value); setDownloadUrl(''); setTransposedKey('') }}
          disabled={isBusy || !effectiveKey}
          className="w-full accent-purple-500 disabled:opacity-30"
        />
        <div className="flex justify-between text-xs text-gray-400 mt-0.5 px-0.5">
          <span>-12</span><span>0</span><span>+12</span>
        </div>
      </div>

      {/* ④ 移調按鈕 */}
      <button
        onClick={handleTranspose}
        disabled={isBusy || !effectiveKey || steps === 0}
        className="w-full rounded-xl bg-gradient-to-r from-purple-600 to-violet-500 text-white py-3 text-sm font-semibold shadow hover:from-purple-700 hover:to-violet-600 active:scale-95 transition disabled:opacity-40">
        {transposing ? '移調中…' : steps === 0 && effectiveKey ? '已是原調（調整半音後移調）' : '④ 開始移調'}
      </button>

      {/* 移調結果：Key 名 + 播放器 + 下載 */}
      {downloadUrl && transposedKey && (
        <div className="rounded-xl bg-green-50 border border-green-200 p-4 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs text-green-600 font-medium">移調完成</span>
            <span className="text-sm font-bold text-green-700">
              {effectiveKey} → {transposedKey}
              <span className="ml-1 text-xs font-normal text-green-500">
                ({steps > 0 ? '+' : ''}{steps} 半音)
              </span>
            </span>
          </div>
          <audio ref={resultAudioRef} controls src={downloadUrl} className="w-full" />
          <a href={downloadUrl} download="transposed.wav"
            className="flex items-center justify-center gap-2 w-full rounded-xl bg-gradient-to-r from-green-500 to-emerald-500 text-white py-2.5 text-sm font-semibold shadow hover:from-green-600 hover:to-emerald-600 active:scale-95 transition">
            ⬇ 下載移調音檔
          </a>
        </div>
      )}

      {error && (
        <div className="rounded-xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-600">{error}</div>
      )}

      {(file || error) && (
        <button onClick={reset} className="w-full text-xs text-gray-400 hover:text-gray-600 py-1">重置</button>
      )}
    </div>
  )
}

// ─── 旋律試聽 ─────────────────────────────────────────────────────────────────

const LS_MELODY = 'pitchpal_melody'
const LS_CHORDS = 'pitchpal_chords'

const CHORD_QUALITIES = ['基本','m','m7','7','maj7','sus4','sus2','add9','dim']
const QUALITY_SUFFIX: Record<string, string> = {
  '基本':'', 'm':'m', 'm7':'m7', '7':'7', 'maj7':'maj7',
  'sus4':'sus4', 'sus2':'sus2', 'add9':'add9', 'dim':'dim',
}

function JianpuTab() {
  const [melody, setMelody] = useState(() => localStorage.getItem(LS_MELODY) || '')
  const [chords, setChords] = useState(() => localStorage.getItem(LS_CHORDS) || '')
  const [key, setKey] = useState('G')
  const [bpm, setBpm] = useState(80)
  const [octave, setOctave] = useState(4)
  const [timbre, setTimbre] = useState('鋼琴')
  const [metronome, setMetronome] = useState(false)
  const [loading, setLoading] = useState(false)
  const [audioUrl, setAudioUrl] = useState('')
  const [error, setError] = useState('')
  const [diatonicChords, setDiatonicChords] = useState<string[]>([])
  const [previewingChord, setPreviewingChord] = useState('')
  const [noteMode, setNoteMode] = useState<'試音'|'加入'>('加入')
  const [chordQuality, setChordQuality] = useState('基本')
  // sticky modifier toggles
  const [mods, setMods] = useState({ sharp: false, flat: false, high: false, low: false })
  const chordAudioRef = useRef<HTMLAudioElement | null>(null)
  const noteAudioRef = useRef<HTMLAudioElement | null>(null)

  useEffect(() => { localStorage.setItem(LS_MELODY, melody) }, [melody])
  useEffect(() => { localStorage.setItem(LS_CHORDS, chords) }, [chords])
  useEffect(() => {
    fetch(`/api/jianpu/chords/${key}`)
      .then(r => r.json()).then(d => setDiatonicChords(d.chords)).catch(() => {})
  }, [key])

  const toggleMod = (mod: 'sharp'|'flat'|'high'|'low') => setMods(prev => {
    const next = { ...prev, [mod]: !prev[mod] }
    if (mod === 'sharp' && next.sharp) next.flat = false
    if (mod === 'flat'  && next.flat)  next.sharp = false
    if (mod === 'high'  && next.high)  next.low = false
    if (mod === 'low'   && next.low)   next.high = false
    return next
  })

  const buildNoteToken = (n: string) => {
    let tok = n
    if (mods.sharp) tok += '#'
    else if (mods.flat) tok += 'b'
    if (mods.high) tok += "'"
    else if (mods.low) tok += ','
    return tok
  }

  const appendMod = (mod: string) => setMelody(m => {
    const t = m.trimEnd()
    const lastSpace = t.lastIndexOf(' ')
    const last = t.slice(lastSpace + 1)
    if (last && last !== '|') return t.slice(0, lastSpace + 1) + last + mod
    return t + mod
  })

  const handleNoteClick = async (n: string) => {
    // preview
    const tok = n === '0' ? '0' : buildNoteToken(n)
    if (n !== '0') {
      const fd = new FormData()
      fd.append('melody', tok); fd.append('chords', ''); fd.append('key', key)
      fd.append('bpm', '120'); fd.append('octave', String(octave)); fd.append('timbre', timbre)
      fetch('/api/jianpu/synth', { method: 'POST', body: fd })
        .then(r => r.ok ? r.blob() : null)
        .then(b => { if (b) { if (!noteAudioRef.current) noteAudioRef.current = new Audio(); noteAudioRef.current.src = URL.createObjectURL(b); noteAudioRef.current.play().catch(() => {}) } })
        .catch(() => {})
    }
    // append if mode = 加入
    if (noteMode === '加入') setMelody(m => m ? m + ' ' + tok : tok)
  }

  const previewChord = async (c: string) => {
    setPreviewingChord(c)
    const fd = new FormData()
    fd.append('melody', ''); fd.append('chords', c); fd.append('key', key)
    fd.append('bpm', String(bpm)); fd.append('octave', String(octave)); fd.append('timbre', timbre)
    try {
      const res = await fetch('/api/jianpu/synth', { method: 'POST', body: fd })
      if (!res.ok) return
      const url = URL.createObjectURL(await res.blob())
      if (!chordAudioRef.current) chordAudioRef.current = new Audio()
      chordAudioRef.current.src = url; chordAudioRef.current.play().catch(() => {})
    } finally { setPreviewingChord('') }
  }

  const handleChordClick = (base: string) => {
    const suffix = QUALITY_SUFFIX[chordQuality] || ''
    // strip existing quality if base already has one, then apply selected quality
    const rootMatch = base.match(/^([A-G][#b]?)(.*)$/)
    const root = rootMatch ? rootMatch[1] : base
    const c = root + suffix
    previewChord(c)
    setChords(ch => ch ? ch + ' ' + c : c)
  }

  const handleSynth = async () => {
    if (!melody.trim() && !chords.trim()) { setError('請輸入旋律或和弦。'); return }
    setLoading(true); setError(''); setAudioUrl('')
    const fd = new FormData()
    fd.append('melody', melody); fd.append('chords', chords); fd.append('key', key)
    fd.append('bpm', String(bpm)); fd.append('octave', String(octave))
    fd.append('timbre', timbre); fd.append('metronome', String(metronome))
    try {
      const res = await fetch('/api/jianpu/synth', { method: 'POST', body: fd })
      if (!res.ok) throw new Error((await res.json()).detail)
      setAudioUrl(URL.createObjectURL(await res.blob()))
    } catch (e: any) {
      setError(e.message || '合成失敗')
    } finally { setLoading(false) }
  }

  const btnBase = "px-3 py-1.5 rounded-lg text-sm font-medium active:scale-95 transition shadow-sm"
  const modBtn = (active: boolean) => `${btnBase} ${active ? 'bg-indigo-500 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`

  return (
    <div className="space-y-5">
      <p className="text-xs text-gray-500">輸入數字簡譜與和弦進行，合成音頻試聽。旋律與和弦皆為選填。</p>

      {/* 參數列 */}
      <div className="bg-gray-50 rounded-2xl p-4 space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs font-semibold text-gray-500 mb-1 block">調性（1=?）</label>
            <select value={key} onChange={e => setKey(e.target.value)}
              className="w-full rounded-xl border border-gray-200 px-2 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-400">
              {MELODY_KEYS.map(k => <option key={k}>{k}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs font-semibold text-gray-500 mb-1 block">音色</label>
            <select value={timbre} onChange={e => setTimbre(e.target.value)}
              className="w-full rounded-xl border border-gray-200 px-2 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-400">
              {TIMBRES.map(t => <option key={t}>{t}</option>)}
            </select>
          </div>
        </div>
        <div>
          <label className="text-xs font-semibold text-gray-500 mb-1 block">BPM：<span className="text-indigo-600 font-bold">{bpm}</span></label>
          <input type="range" min={40} max={200} value={bpm} onChange={e => setBpm(+e.target.value)} className="w-full accent-indigo-500" />
        </div>
        <div>
          <label className="text-xs font-semibold text-gray-500 mb-1 block">八度：<span className="text-indigo-600 font-bold">{octave}</span></label>
          <input type="range" min={3} max={5} value={octave} onChange={e => setOctave(+e.target.value)} className="w-full accent-indigo-500" />
        </div>
        <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
          <input type="checkbox" checked={metronome} onChange={e => setMetronome(e.target.checked)} className="accent-indigo-500" />
          加入節拍器
        </label>
      </div>

      {/* 旋律區 */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <label className="text-sm font-semibold text-gray-700">🎵 旋律（數字簡譜）</label>
          <div className="flex rounded-lg overflow-hidden border border-gray-200 text-xs">
            {(['加入','試音'] as const).map(m => (
              <button key={m} onClick={() => setNoteMode(m)}
                className={`px-2.5 py-1 font-medium transition ${noteMode === m ? 'bg-indigo-500 text-white' : 'bg-white text-gray-500 hover:bg-gray-50'}`}>
                {m}
              </button>
            ))}
          </div>
        </div>

        {/* 音符按鈕 */}
        <div className="flex flex-wrap gap-1.5">
          {['1','2','3','4','5','6','7'].map(n => (
            <button key={n} onClick={() => handleNoteClick(n)}
              className={`${btnBase} bg-indigo-100 text-indigo-700 hover:bg-indigo-200 w-9`}>{n}</button>
          ))}
          <button onClick={() => handleNoteClick('0')}
            className={`${btnBase} bg-gray-100 text-gray-600 hover:bg-gray-200`}>休止</button>
        </div>

        {/* Toggle 修飾符 */}
        <div className="flex flex-wrap gap-1.5">
          <span className="text-xs text-gray-400 self-center">半音：</span>
          <button onClick={() => toggleMod('sharp')} className={modBtn(mods.sharp)}># 升</button>
          <button onClick={() => toggleMod('flat')}  className={modBtn(mods.flat)}>b 降</button>
          <span className="text-xs text-gray-400 self-center ml-1">八度：</span>
          <button onClick={() => toggleMod('high')} className={modBtn(mods.high)}>↑ 高八</button>
          <button onClick={() => toggleMod('low')}  className={modBtn(mods.low)}>↓ 低八</button>
        </div>

        {/* 時值修飾符（直接 append） */}
        <div className="flex flex-wrap gap-1.5">
          <span className="text-xs text-gray-400 self-center">時值：</span>
          {[['_','⅛八分'],['__','⅟₁₆十六'],['-','延音'],['|','小節|']].map(([val,label]) => (
            <button key={val} onClick={() => val === '|' ? setMelody(m => m ? m + ' |' : '|') : appendMod(val)}
              className={`${btnBase} bg-gray-100 text-gray-500 hover:bg-gray-200 text-xs`}>{label}</button>
          ))}
        </div>

        <textarea value={melody} onChange={e => setMelody(e.target.value)}
          placeholder="例：5 6 7 5 3 - - - | 7 5 6 -"
          rows={3} className="w-full rounded-xl border border-gray-200 px-3 py-2 text-sm font-mono bg-gray-50 focus:outline-none focus:ring-2 focus:ring-indigo-400" />
        {melody && <button onClick={() => setMelody('')} className="text-xs text-gray-400 hover:text-red-400">清空旋律</button>}
      </div>

      {/* 和弦區 */}
      <div className="space-y-2">
        <label className="text-sm font-semibold text-gray-700 block">🎸 和弦進行</label>

        {/* 和弦色彩 */}
        <div className="flex flex-wrap gap-1.5">
          <span className="text-xs text-gray-400 self-center">色彩：</span>
          {CHORD_QUALITIES.map(q => (
            <button key={q} onClick={() => setChordQuality(q)}
              className={`${btnBase} text-xs ${chordQuality === q ? 'bg-violet-500 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}>
              {q}
            </button>
          ))}
        </div>

        {diatonicChords.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {diatonicChords.map(c => (
              <button key={c} onClick={() => handleChordClick(c)}
                disabled={previewingChord !== ''}
                className={`${btnBase} bg-emerald-100 text-emerald-700 hover:bg-emerald-200 disabled:opacity-50`}>
                {c}
              </button>
            ))}
            <button onClick={() => setChords(ch => ch ? ch + ' |' : '|')}
              className={`${btnBase} bg-gray-100 text-gray-500 hover:bg-gray-200`}>|</button>
          </div>
        )}
        <textarea value={chords} onChange={e => setChords(e.target.value)}
          placeholder="例：C Em7 | D | G/B | Em7 D"
          rows={2} className="w-full rounded-xl border border-gray-200 px-3 py-2 text-sm font-mono bg-gray-50 focus:outline-none focus:ring-2 focus:ring-indigo-400" />
        {chords && <button onClick={() => setChords('')} className="text-xs text-gray-400 hover:text-red-400">清空和弦</button>}
      </div>

      {/* 合成按鈕 */}
      <button onClick={handleSynth} disabled={loading}
        className="w-full rounded-xl bg-gradient-to-r from-indigo-600 to-violet-500 text-white py-3 text-sm font-semibold shadow hover:from-indigo-700 hover:to-violet-600 active:scale-95 transition disabled:opacity-50">
        {loading ? '合成中…' : '▶ 合成試聽'}
      </button>

      {error && <div className="rounded-xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-600">{error}</div>}

      {audioUrl && (
        <div className="rounded-2xl bg-emerald-50 border border-emerald-200 p-4 space-y-3">
          <audio controls src={audioUrl} className="w-full" />
          <a href={audioUrl} download="preview.wav"
            className="flex items-center justify-center gap-1 text-xs text-emerald-700 hover:text-emerald-900 font-medium">
            ⬇ 下載音檔
          </a>
        </div>
      )}
    </div>
  )
}

// ─── 音檔轉譜 ─────────────────────────────────────────────────────────────────

function TranscribeTab() {
  const [file, setFile] = useState<File | null>(null)
  const [key, setKey] = useState('C')
  const [bpm, setBpm] = useState(80)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<{melody: string, chords: string} | null>(null)
  const [error, setError] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const reset = () => {
    setFile(null); setResult(null); setError('')
    if (inputRef.current) inputRef.current.value = ''
  }

  const handleTranscribe = async () => {
    if (!file) return
    setLoading(true); setError(''); setResult(null)
    const fd = new FormData()
    fd.append('file', file); fd.append('key', key); fd.append('bpm', String(bpm))
    try {
      const res = await fetch('/api/transcribe', { method: 'POST', body: fd })
      if (!res.ok) throw new Error((await res.json()).detail)
      const data = await res.json()
      setResult({ melody: data.melody, chords: data.chords })
    } catch (e: any) {
      setError(e.message || '轉譜失敗')
    } finally {
      setLoading(false)
    }
  }

  const copyToJianpu = () => {
    if (!result) return
    localStorage.setItem(LS_MELODY, result.melody)
    localStorage.setItem(LS_CHORDS, result.chords)
  }

  return (
    <div className="space-y-5">
      <p className="text-xs text-gray-500">上傳詩歌音檔，自動辨識主旋律與和弦，輸出數字簡譜粗稿。適合旋律清晰的錄音。</p>

      {/* 上傳 */}
      <div
        onClick={() => !loading && inputRef.current?.click()}
        onDragOver={e => e.preventDefault()}
        onDrop={e => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f && !loading) setFile(f) }}
        className={`border-2 border-dashed rounded-2xl p-8 text-center cursor-pointer transition-all
          ${loading ? 'border-blue-200 bg-blue-50 cursor-not-allowed'
            : file ? 'border-blue-400 bg-blue-50'
            : 'border-gray-200 bg-gray-50 hover:border-blue-400 hover:bg-blue-50'}`}
      >
        <input ref={inputRef} type="file" accept="audio/*" className="hidden"
          onChange={e => { const f = e.target.files?.[0]; if (f) setFile(f) }} />
        {file ? (
          <>
            <div className="text-4xl mb-2">📄</div>
            <p className="text-sm font-semibold text-blue-700 truncate px-4">{file.name}</p>
          </>
        ) : (
          <>
            <div className="text-5xl mb-3 opacity-30">🎼</div>
            <p className="text-sm font-semibold text-gray-600">點擊或拖曳上傳音檔</p>
            <p className="text-xs text-gray-400 mt-1">支援 mp3 · wav · m4a</p>
          </>
        )}
      </div>

      {/* 調性 / BPM */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs font-semibold text-gray-500 mb-1 block">調性（1=?）</label>
          <select value={key} onChange={e => setKey(e.target.value)}
            className="w-full rounded-xl border border-gray-200 px-2 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-400">
            {MELODY_KEYS.map(k => <option key={k}>{k}</option>)}
          </select>
        </div>
        <div>
          <label className="text-xs font-semibold text-gray-500 mb-1 block">BPM：<span className="text-blue-600 font-bold">{bpm}</span></label>
          <input type="range" min={40} max={200} value={bpm} onChange={e => setBpm(+e.target.value)} className="w-full accent-blue-500 mt-2" />
        </div>
      </div>

      {/* 轉譜按鈕 */}
      <button onClick={handleTranscribe} disabled={!file || loading}
        className="w-full rounded-xl bg-gradient-to-r from-blue-600 to-cyan-500 text-white py-3 text-sm font-semibold shadow hover:from-blue-700 hover:to-cyan-600 active:scale-95 transition disabled:opacity-50">
        {loading ? '⏳ 轉譜中，約 30 秒…' : '🎼 開始轉譜'}
      </button>

      {result && (
        <div className="rounded-2xl bg-blue-50 border border-blue-200 p-4 space-y-3">
          <p className="text-xs font-semibold text-blue-500">轉譜粗稿（可複製到旋律試聽編輯）</p>
          <div>
            <label className="text-xs text-gray-500 font-medium block mb-1">旋律</label>
            <textarea readOnly value={result.melody} rows={4}
              className="w-full rounded-xl border border-gray-200 px-3 py-2 text-sm font-mono bg-white focus:outline-none" />
          </div>
          <div>
            <label className="text-xs text-gray-500 font-medium block mb-1">和弦</label>
            <textarea readOnly value={result.chords} rows={2}
              className="w-full rounded-xl border border-gray-200 px-3 py-2 text-sm font-mono bg-white focus:outline-none" />
          </div>
          <button onClick={copyToJianpu}
            className="w-full rounded-xl bg-gradient-to-r from-indigo-500 to-violet-500 text-white py-2.5 text-sm font-semibold shadow hover:from-indigo-600 hover:to-violet-600 active:scale-95 transition">
            → 送到旋律試聽 Tab
          </button>
        </div>
      )}

      {error && <div className="rounded-xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-600">{error}</div>}

      {(file || error) && (
        <button onClick={reset} className="w-full text-xs text-gray-400 hover:text-gray-600 py-1">重新上傳</button>
      )}
    </div>
  )
}

// ─── App ──────────────────────────────────────────────────────────────────────

export default function App() {
  const [tab, setTab] = useState<Tab>('detect')

  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-50 via-white to-indigo-50">
      {/* Header */}
      <div className="bg-gradient-to-r from-purple-700 to-violet-600 px-4 py-4 flex items-center gap-3 shadow-md">
        <div className="w-9 h-9 rounded-xl bg-white/20 flex items-center justify-center text-xl">🎵</div>
        <div>
          <h1 className="text-lg font-extrabold text-white leading-none tracking-tight">PitchPal</h1>
          <p className="text-xs text-purple-200 mt-0.5">敬拜調性工具</p>
        </div>
      </div>

      {/* Tab bar */}
      <div className="bg-white border-b border-gray-100 flex shadow-sm">
        {([
          ['detect', '辨識 Key / 移調', 'purple'],
          ['jianpu', '旋律試聽', 'indigo'],
          ['transcribe', '音檔轉譜', 'blue'],
        ] as [Tab, string, string][]).map(([id, label, color]) => (
          <button key={id} onClick={() => setTab(id)}
            className={`flex-1 py-3.5 text-xs font-bold border-b-2 transition-colors
              ${tab === id
                ? color === 'purple' ? 'border-purple-600 text-purple-600 bg-purple-50/50'
                  : color === 'indigo' ? 'border-indigo-600 text-indigo-600 bg-indigo-50/50'
                  : 'border-blue-600 text-blue-600 bg-blue-50/50'
                : 'border-transparent text-gray-400 hover:text-gray-600 hover:bg-gray-50'}`}>
            {label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="max-w-lg mx-auto px-4 py-6">
        {tab === 'detect' && <KeyDetectTab />}
        {tab === 'jianpu' && <JianpuTab />}
        {tab === 'transcribe' && <TranscribeTab />}
      </div>
    </div>
  )
}
