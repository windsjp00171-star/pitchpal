import { useState, useRef, useEffect } from 'react'

const ALL_KEYS = [
  'C 大調','C#/Db 大調','D 大調','D#/Eb 大調','E 大調','F 大調',
  'F#/Gb 大調','G 大調','G#/Ab 大調','A 大調','A#/Bb 大調','B 大調',
  'C 小調','C#/Db 小調','D 小調','D#/Eb 小調','E 小調','F 小調',
  'F#/Gb 小調','G 小調','G#/Ab 小調','A 小調','A#/Bb 小調','B 小調',
]

const MELODY_KEYS = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
const TIMBRES = ['鋼琴', '吉他', '管風琴']

type Tab = 'detect' | 'jianpu' | 'transcribe'

// ─── 辨識 Key / 移調 ──────────────────────────────────────────────────────────

function KeyDetectTab() {
  const [file, setFile] = useState<File | null>(null)
  const [detecting, setDetecting] = useState(false)
  const [detectedKey, setDetectedKey] = useState('')
  const [confidence, setConfidence] = useState(0)
  const [targetKey, setTargetKey] = useState('')
  const [transposing, setTransposing] = useState(false)
  const [downloadUrl, setDownloadUrl] = useState('')
  const [error, setError] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const reset = () => {
    setFile(null); setDetecting(false); setDetectedKey(''); setConfidence(0)
    setTargetKey(''); setTransposing(false); setDownloadUrl(''); setError('')
    if (inputRef.current) inputRef.current.value = ''
  }

  const handleFile = async (f: File) => {
    reset(); setFile(f); setDetecting(true)
    const fd = new FormData(); fd.append('file', f)
    try {
      const res = await fetch('/api/detect', { method: 'POST', body: fd })
      if (!res.ok) throw new Error((await res.json()).detail)
      const data = await res.json()
      setDetectedKey(data.key); setConfidence(data.confidence); setTargetKey(data.key)
    } catch (e: any) {
      setError(e.message || '偵測失敗')
    } finally {
      setDetecting(false)
    }
  }

  const handleTranspose = async () => {
    if (!file || !detectedKey || !targetKey) return
    setTransposing(true); setError(''); setDownloadUrl('')
    const fd = new FormData()
    fd.append('file', file); fd.append('detected_key', detectedKey); fd.append('target_key', targetKey)
    try {
      const res = await fetch('/api/transpose', { method: 'POST', body: fd })
      if (!res.ok) throw new Error((await res.json()).detail)
      setDownloadUrl(URL.createObjectURL(await res.blob()))
    } catch (e: any) {
      setError(e.message || '移調失敗')
    } finally {
      setTransposing(false)
    }
  }

  const isBusy = detecting || transposing

  return (
    <div className="space-y-5">
      {/* YouTube 提示 */}
      <div className="flex items-start gap-2 rounded-xl bg-amber-50 border border-amber-200 px-4 py-3 text-xs text-amber-800">
        <span className="text-base leading-none mt-0.5">💡</span>
        <span>YouTube 音檔？先到 <a href="https://cobalt.tools" target="_blank" rel="noopener noreferrer" className="underline font-semibold">cobalt.tools</a> 下載成 mp3，再上傳。</span>
      </div>

      {/* 上傳區 */}
      <div
        onClick={() => !isBusy && inputRef.current?.click()}
        onDragOver={e => e.preventDefault()}
        onDrop={e => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f && !isBusy) handleFile(f) }}
        className={`relative border-2 border-dashed rounded-2xl p-8 text-center cursor-pointer transition-all
          ${isBusy ? 'border-purple-200 bg-purple-50 cursor-not-allowed'
            : file ? 'border-purple-400 bg-purple-50'
            : 'border-gray-200 bg-gray-50 hover:border-purple-400 hover:bg-purple-50'}`}
      >
        <input ref={inputRef} type="file" accept="audio/*" className="hidden"
          onChange={e => { const f = e.target.files?.[0]; if (f) handleFile(f) }} />
        {file ? (
          <>
            <div className="text-4xl mb-2">🎵</div>
            <p className="text-sm font-semibold text-purple-700 truncate px-4">{file.name}</p>
            {!isBusy && <p className="text-xs text-purple-400 mt-1">點擊換一個檔案</p>}
          </>
        ) : (
          <>
            <div className="text-5xl mb-3 opacity-30">🎵</div>
            <p className="text-sm font-semibold text-gray-600">點擊或拖曳上傳音檔</p>
            <p className="text-xs text-gray-400 mt-1">支援 mp3 · wav · m4a</p>
          </>
        )}
      </div>

      {/* 偵測中 */}
      {detecting && (
        <div className="flex items-center justify-center gap-2 py-2 text-sm text-purple-600 font-medium">
          <span className="inline-block animate-spin">⏳</span> 偵測 Key 中，請稍候…
        </div>
      )}

      {/* 偵測結果 */}
      {detectedKey && (
        <div className="rounded-2xl overflow-hidden shadow-sm">
          <div className="bg-gradient-to-r from-purple-600 to-violet-500 px-5 py-4 flex items-center justify-between text-white">
            <div>
              <p className="text-xs opacity-75 mb-1">偵測到的 Key</p>
              <p className="text-4xl font-extrabold tracking-tight">{detectedKey}</p>
            </div>
            <div className="text-right">
              <p className="text-xs opacity-75 mb-1">信心度</p>
              <p className="text-3xl font-bold">{confidence}%</p>
            </div>
          </div>
        </div>
      )}

      {/* 目標 Key */}
      {detectedKey && (
        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-1.5">移調目標 Key</label>
          <select
            value={targetKey}
            onChange={e => { setTargetKey(e.target.value); setDownloadUrl('') }}
            className="w-full rounded-xl border border-gray-200 px-3 py-2.5 text-sm bg-white shadow-sm focus:outline-none focus:ring-2 focus:ring-purple-400"
          >
            {ALL_KEYS.map(k => <option key={k} value={k}>{k}{k === detectedKey ? '（原調）' : ''}</option>)}
          </select>
        </div>
      )}

      {/* 同 Key 提示 */}
      {detectedKey && targetKey === detectedKey && !downloadUrl && (
        <p className="text-center text-sm text-gray-400">已是目標 Key，無需移調。</p>
      )}

      {/* 移調按鈕 */}
      {detectedKey && targetKey !== detectedKey && !downloadUrl && (
        <button onClick={handleTranspose} disabled={transposing}
          className="w-full rounded-xl bg-gradient-to-r from-purple-600 to-violet-500 text-white py-3 text-sm font-semibold shadow hover:from-purple-700 hover:to-violet-600 active:scale-95 transition disabled:opacity-50">
          {transposing ? '移調中…' : '🎚 開始移調'}
        </button>
      )}

      {/* 下載 */}
      {downloadUrl && (
        <a href={downloadUrl} download="transposed.wav"
          className="flex items-center justify-center gap-2 w-full rounded-xl bg-gradient-to-r from-green-500 to-emerald-500 text-white py-3 text-sm font-semibold shadow hover:from-green-600 hover:to-emerald-600 active:scale-95 transition">
          ⬇ 下載移調音檔
        </a>
      )}

      {error && (
        <div className="rounded-xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-600">{error}</div>
      )}

      {(detectedKey || error) && (
        <button onClick={reset} className="w-full text-xs text-gray-400 hover:text-gray-600 py-1">重新上傳</button>
      )}
    </div>
  )
}

// ─── 旋律試聽 ─────────────────────────────────────────────────────────────────

function JianpuTab() {
  const [melody, setMelody] = useState('')
  const [chords, setChords] = useState('')
  const [key, setKey] = useState('G')
  const [bpm, setBpm] = useState(80)
  const [octave, setOctave] = useState(4)
  const [timbre, setTimbre] = useState('鋼琴')
  const [metronome, setMetronome] = useState(false)
  const [loading, setLoading] = useState(false)
  const [audioUrl, setAudioUrl] = useState('')
  const [error, setError] = useState('')
  const [diatonicChords, setDiatonicChords] = useState<string[]>([])

  useEffect(() => {
    fetch(`/api/jianpu/chords/${key}`)
      .then(r => r.json()).then(d => setDiatonicChords(d.chords)).catch(() => {})
  }, [key])

  const appendNote = (n: string) => setMelody(m => m ? m + ' ' + n : n)
  const appendMod = (mod: string) => setMelody(m => {
    const t = m.trimEnd()
    const last = t.slice(t.lastIndexOf(' ') + 1)
    if (last && !'|'.includes(last)) return t.slice(0, t.length - last.length) + last + mod
    return m + mod
  })
  const appendChord = (c: string) => setChords(ch => ch ? ch + ' ' + c : c)

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
    } finally {
      setLoading(false)
    }
  }

  const btnBase = "px-3 py-1.5 rounded-lg text-sm font-medium active:scale-95 transition shadow-sm"

  return (
    <div className="space-y-5">
      <p className="text-xs text-gray-500">輸入數字簡譜與和弦進行，合成音頻試聽。旋律與和弦皆為選填。</p>

      {/* 參數列 */}
      <div className="bg-gray-50 rounded-2xl p-4 space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs font-semibold text-gray-500 mb-1 block">調性</label>
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
          <input type="range" min={40} max={200} value={bpm} onChange={e => setBpm(+e.target.value)}
            className="w-full accent-indigo-500" />
        </div>
        <div>
          <label className="text-xs font-semibold text-gray-500 mb-1 block">八度：<span className="text-indigo-600 font-bold">{octave}</span></label>
          <input type="range" min={3} max={5} value={octave} onChange={e => setOctave(+e.target.value)}
            className="w-full accent-indigo-500" />
        </div>
        <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
          <input type="checkbox" checked={metronome} onChange={e => setMetronome(e.target.checked)} className="accent-indigo-500" />
          加入節拍器
        </label>
      </div>

      {/* 旋律區 */}
      <div className="space-y-2">
        <label className="text-sm font-semibold text-gray-700 block">🎵 旋律（數字簡譜）</label>
        <div className="flex flex-wrap gap-1.5">
          {['1','2','3','4','5','6','7'].map(n => (
            <button key={n} onClick={() => appendNote(n)}
              className={`${btnBase} bg-indigo-100 text-indigo-700 hover:bg-indigo-200 w-9`}>{n}</button>
          ))}
          <button onClick={() => appendNote('0')}
            className={`${btnBase} bg-gray-100 text-gray-600 hover:bg-gray-200`}>休止</button>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {[['#','#升'],["b",'b降'],["'","↑八"],[',"↓八'],['_','⅛'],['__','⅟₁₆'],['--','延音'],['|','小節|']].map(([val,label]) => (
            <button key={val} onClick={() => val === '|' ? appendNote('|') : appendMod(val)}
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
        {diatonicChords.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {diatonicChords.map(c => (
              <button key={c} onClick={() => appendChord(c)}
                className={`${btnBase} bg-emerald-100 text-emerald-700 hover:bg-emerald-200`}>{c}</button>
            ))}
            <button onClick={() => appendChord('|')}
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
  const [title, setTitle] = useState('')
  const [composer, setComposer] = useState('')
  const [loading, setLoading] = useState(false)
  const [downloadUrl, setDownloadUrl] = useState('')
  const [error, setError] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const reset = () => {
    setFile(null); setDownloadUrl(''); setError('')
    if (inputRef.current) inputRef.current.value = ''
  }

  const handleTranscribe = async () => {
    if (!file) return
    setLoading(true); setError(''); setDownloadUrl('')
    const fd = new FormData()
    fd.append('file', file); fd.append('title', title); fd.append('composer', composer)
    try {
      const res = await fetch('/api/transcribe', { method: 'POST', body: fd })
      if (!res.ok) throw new Error((await res.json()).detail)
      setDownloadUrl(URL.createObjectURL(await res.blob()))
    } catch (e: any) {
      setError(e.message || '轉譜失敗')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-5">
      <p className="text-xs text-gray-500">上傳詩歌音檔，自動辨識主旋律，輸出 PDF 樂譜。適合旋律清晰的錄音。</p>

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

      {/* 標題 / 作曲者 */}
      <div className="space-y-3">
        <div>
          <label className="text-sm font-semibold text-gray-700 mb-1.5 block">樂譜標題（選填）</label>
          <input type="text" value={title} onChange={e => setTitle(e.target.value)}
            placeholder="例：Amazing Grace"
            className="w-full rounded-xl border border-gray-200 px-3 py-2.5 text-sm bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-400" />
        </div>
        <div>
          <label className="text-sm font-semibold text-gray-700 mb-1.5 block">作曲者（選填）</label>
          <input type="text" value={composer} onChange={e => setComposer(e.target.value)}
            placeholder="例：John Newton"
            className="w-full rounded-xl border border-gray-200 px-3 py-2.5 text-sm bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-400" />
        </div>
      </div>

      {/* 轉譜按鈕 */}
      <button onClick={handleTranscribe} disabled={!file || loading}
        className="w-full rounded-xl bg-gradient-to-r from-blue-600 to-cyan-500 text-white py-3 text-sm font-semibold shadow hover:from-blue-700 hover:to-cyan-600 active:scale-95 transition disabled:opacity-50">
        {loading ? '⏳ 轉譜中，約 30 秒…' : '🎼 開始轉譜'}
      </button>

      {downloadUrl && (
        <a href={downloadUrl} download="score.pdf"
          className="flex items-center justify-center gap-2 w-full rounded-xl bg-gradient-to-r from-green-500 to-emerald-500 text-white py-3 text-sm font-semibold shadow hover:from-green-600 hover:to-emerald-600 active:scale-95 transition">
          ⬇ 下載 PDF 樂譜
        </a>
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
