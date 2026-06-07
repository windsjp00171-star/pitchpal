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

  return (
    <div className="space-y-4">
      {/* YouTube 提示 */}
      <div className="rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 text-xs text-amber-800">
        YouTube 音檔？先到 <a href="https://cobalt.tools" target="_blank" rel="noopener noreferrer" className="underline font-medium">cobalt.tools</a> 下載成 mp3，再上傳。
      </div>

      {/* 上傳區 */}
      <div>
        <label className="block text-sm font-semibold text-gray-700 mb-1">上傳音檔（mp3 / wav / m4a）</label>
        <div
          onClick={() => !detecting && !transposing && inputRef.current?.click()}
          onDragOver={e => e.preventDefault()}
          onDrop={e => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) handleFile(f) }}
          className="border-2 border-dashed border-gray-300 rounded-lg p-4 text-center cursor-pointer hover:border-purple-400 hover:bg-purple-50 transition-colors"
        >
          <input ref={inputRef} type="file" accept="audio/*" className="hidden"
            onChange={e => { const f = e.target.files?.[0]; if (f) handleFile(f) }} />
          {file
            ? <p className="text-sm text-gray-700 truncate">📄 {file.name}</p>
            : <p className="text-sm text-gray-400">點擊或拖曳上傳</p>
          }
        </div>
      </div>

      {/* 偵測中 */}
      {detecting && <p className="text-sm text-purple-500 animate-pulse">⏳ 偵測中，請稍候…</p>}

      {/* 偵測結果 */}
      {detectedKey && (
        <div className="rounded-lg bg-purple-50 border border-purple-200 px-4 py-3 flex items-center justify-between">
          <div>
            <p className="text-xs text-purple-400 mb-0.5">偵測到的 Key</p>
            <p className="text-3xl font-bold text-purple-700">{detectedKey}</p>
          </div>
          <div className="text-right">
            <p className="text-xs text-purple-400 mb-0.5">信心度</p>
            <p className="text-2xl font-semibold text-purple-600">{confidence}%</p>
          </div>
        </div>
      )}

      {/* 目標 Key */}
      {detectedKey && (
        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-1">目標 Key（選擇後移調）</label>
          <select
            value={targetKey}
            onChange={e => { setTargetKey(e.target.value); setDownloadUrl('') }}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-purple-400"
          >
            {ALL_KEYS.map(k => <option key={k} value={k}>{k}{k === detectedKey ? '（原調）' : ''}</option>)}
          </select>
        </div>
      )}

      {/* 移調按鈕 */}
      {detectedKey && targetKey !== detectedKey && !downloadUrl && (
        <button onClick={handleTranspose} disabled={transposing}
          className="w-full rounded-lg bg-purple-600 text-white py-2.5 text-sm font-semibold hover:bg-purple-700 active:scale-95 transition disabled:opacity-50">
          {transposing ? '移調中…' : '開始移調'}
        </button>
      )}

      {/* 同 Key 提示 */}
      {detectedKey && targetKey === detectedKey && (
        <p className="text-sm text-gray-400">已是目標 Key，無需移調。</p>
      )}

      {/* 下載 */}
      {downloadUrl && (
        <a href={downloadUrl} download="transposed.wav"
          className="block w-full rounded-lg bg-green-600 text-white py-2.5 text-sm font-semibold text-center hover:bg-green-700 active:scale-95 transition">
          ⬇ 下載移調音檔
        </a>
      )}

      {error && <p className="text-sm text-red-500">{error}</p>}

      {(detectedKey || error) && (
        <button onClick={reset} className="text-xs text-gray-400 hover:text-gray-600">重新上傳</button>
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

  const btnBase = "px-3 py-1.5 rounded-md text-sm font-medium active:scale-95 transition"

  return (
    <div className="space-y-4">
      {/* 說明 */}
      <p className="text-xs text-gray-500">輸入數字簡譜與和弦進行，合成音頻試聽。旋律與和弦皆為選填。</p>

      {/* 參數列 */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs font-semibold text-gray-600 mb-1 block">調性</label>
          <select value={key} onChange={e => setKey(e.target.value)}
            className="w-full rounded-lg border border-gray-300 px-2 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400">
            {MELODY_KEYS.map(k => <option key={k}>{k}</option>)}
          </select>
        </div>
        <div>
          <label className="text-xs font-semibold text-gray-600 mb-1 block">音色</label>
          <select value={timbre} onChange={e => setTimbre(e.target.value)}
            className="w-full rounded-lg border border-gray-300 px-2 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400">
            {TIMBRES.map(t => <option key={t}>{t}</option>)}
          </select>
        </div>
        <div>
          <label className="text-xs font-semibold text-gray-600 mb-1 block">BPM：{bpm}</label>
          <input type="range" min={40} max={200} value={bpm} onChange={e => setBpm(+e.target.value)}
            className="w-full accent-indigo-500" />
        </div>
        <div>
          <label className="text-xs font-semibold text-gray-600 mb-1 block">八度：{octave}</label>
          <input type="range" min={3} max={5} value={octave} onChange={e => setOctave(+e.target.value)}
            className="w-full accent-indigo-500" />
        </div>
      </div>
      <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
        <input type="checkbox" checked={metronome} onChange={e => setMetronome(e.target.checked)} className="accent-indigo-500" />
        加入節拍器
      </label>

      {/* 旋律區 */}
      <div>
        <label className="text-sm font-semibold text-gray-700 mb-2 block">🎵 旋律（數字簡譜）</label>
        <div className="flex flex-wrap gap-1.5 mb-2">
          {['1','2','3','4','5','6','7'].map(n => (
            <button key={n} onClick={() => appendNote(n)}
              className={`${btnBase} bg-indigo-100 text-indigo-700 hover:bg-indigo-200`}>{n}</button>
          ))}
          <button onClick={() => appendNote('0')}
            className={`${btnBase} bg-gray-100 text-gray-600 hover:bg-gray-200`}>0 休</button>
        </div>
        <div className="flex flex-wrap gap-1.5 mb-2">
          {[['#','升#'],["b",'降b'],["'","↑八'"],[',"↓八,'],['_','八分_'],['__','十六__'],['--','延音--'],['|','|小節']].map(([val,label]) => (
            <button key={val} onClick={() => val === '|' ? appendNote('|') : appendMod(val)}
              className={`${btnBase} bg-gray-100 text-gray-500 hover:bg-gray-200 text-xs`}>{label}</button>
          ))}
        </div>
        <textarea value={melody} onChange={e => setMelody(e.target.value)}
          placeholder="例：5 6 7 5 3 - - - | 7 5 6 -"
          rows={3} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-400" />
        <button onClick={() => setMelody('')} className="text-xs text-gray-400 hover:text-gray-600 mt-1">清空</button>
      </div>

      {/* 和弦區 */}
      <div>
        <label className="text-sm font-semibold text-gray-700 mb-2 block">🎸 和弦進行</label>
        {diatonicChords.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mb-2">
            {diatonicChords.map(c => (
              <button key={c} onClick={() => appendChord(c)}
                className={`${btnBase} bg-green-100 text-green-700 hover:bg-green-200`}>{c}</button>
            ))}
            <button onClick={() => appendChord('|')}
              className={`${btnBase} bg-gray-100 text-gray-500 hover:bg-gray-200`}>|</button>
          </div>
        )}
        <textarea value={chords} onChange={e => setChords(e.target.value)}
          placeholder="例：C Em7 | D | G/B | Em7 D"
          rows={2} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-400" />
        <button onClick={() => setChords('')} className="text-xs text-gray-400 hover:text-gray-600 mt-1">清空</button>
      </div>

      {/* 合成按鈕 */}
      <button onClick={handleSynth} disabled={loading}
        className="w-full rounded-lg bg-indigo-600 text-white py-2.5 text-sm font-semibold hover:bg-indigo-700 active:scale-95 transition disabled:opacity-50">
        {loading ? '合成中…' : '▶ 合成試聽'}
      </button>

      {error && <p className="text-sm text-red-500">{error}</p>}

      {audioUrl && (
        <div className="rounded-lg bg-green-50 border border-green-200 p-3 space-y-2">
          <audio controls src={audioUrl} className="w-full" />
          <a href={audioUrl} download="preview.wav" className="text-xs text-green-600 hover:underline block text-center">⬇ 下載音檔</a>
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
    <div className="space-y-4">
      <p className="text-xs text-gray-500">上傳詩歌音檔，自動辨識主旋律，輸出 PDF 樂譜。適合旋律清晰的錄音。</p>

      {/* 上傳 */}
      <div>
        <label className="text-sm font-semibold text-gray-700 mb-1 block">上傳音檔（mp3 / wav / m4a）</label>
        <div
          onClick={() => !loading && inputRef.current?.click()}
          onDragOver={e => e.preventDefault()}
          onDrop={e => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f && !loading) setFile(f) }}
          className="border-2 border-dashed border-gray-300 rounded-lg p-4 text-center cursor-pointer hover:border-blue-400 hover:bg-blue-50 transition-colors"
        >
          <input ref={inputRef} type="file" accept="audio/*" className="hidden"
            onChange={e => { const f = e.target.files?.[0]; if (f) setFile(f) }} />
          {file
            ? <p className="text-sm text-gray-700 truncate">📄 {file.name}</p>
            : <p className="text-sm text-gray-400">點擊或拖曳上傳</p>
          }
        </div>
      </div>

      {/* 標題 / 作曲者 */}
      <div>
        <label className="text-sm font-semibold text-gray-700 mb-1 block">樂譜標題（選填）</label>
        <input type="text" value={title} onChange={e => setTitle(e.target.value)}
          placeholder="例：Amazing Grace"
          className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
      </div>
      <div>
        <label className="text-sm font-semibold text-gray-700 mb-1 block">作曲者（選填）</label>
        <input type="text" value={composer} onChange={e => setComposer(e.target.value)}
          placeholder="例：John Newton"
          className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
      </div>

      {/* 轉譜按鈕 */}
      <button onClick={handleTranscribe} disabled={!file || loading}
        className="w-full rounded-lg bg-blue-600 text-white py-2.5 text-sm font-semibold hover:bg-blue-700 active:scale-95 transition disabled:opacity-50">
        {loading ? '轉譜中，約 30 秒…' : '開始轉譜'}
      </button>

      {downloadUrl && (
        <a href={downloadUrl} download="score.pdf"
          className="block w-full rounded-lg bg-green-600 text-white py-2.5 text-sm font-semibold text-center hover:bg-green-700 active:scale-95 transition">
          ⬇ 下載 PDF 樂譜
        </a>
      )}

      {error && <p className="text-sm text-red-500">{error}</p>}

      {(file || error) && (
        <button onClick={reset} className="text-xs text-gray-400 hover:text-gray-600">重新上傳</button>
      )}
    </div>
  )
}

// ─── App ──────────────────────────────────────────────────────────────────────

export default function App() {
  const [tab, setTab] = useState<Tab>('detect')

  return (
    <div className="min-h-screen bg-gray-100">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-4 py-3 flex items-center gap-2">
        <span className="text-xl">🎵</span>
        <div>
          <h1 className="text-base font-bold text-gray-800 leading-none">PitchPal</h1>
          <p className="text-xs text-gray-400 mt-0.5">敬拜調性工具</p>
        </div>
      </div>

      {/* Tab bar */}
      <div className="bg-white border-b border-gray-200 flex">
        {([
          ['detect', '辨識 Key / 移調', 'purple'],
          ['jianpu', '旋律試聽', 'indigo'],
          ['transcribe', '音檔轉譜', 'blue'],
        ] as [Tab, string, string][]).map(([id, label, color]) => (
          <button key={id} onClick={() => setTab(id)}
            className={`flex-1 py-3 text-xs font-semibold border-b-2 transition-colors
              ${tab === id
                ? color === 'purple' ? 'border-purple-600 text-purple-600'
                  : color === 'indigo' ? 'border-indigo-600 text-indigo-600'
                  : 'border-blue-600 text-blue-600'
                : 'border-transparent text-gray-400 hover:text-gray-600'}`}>
            {label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="max-w-lg mx-auto px-4 py-5">
        {tab === 'detect' && <KeyDetectTab />}
        {tab === 'jianpu' && <JianpuTab />}
        {tab === 'transcribe' && <TranscribeTab />}
      </div>
    </div>
  )
}
