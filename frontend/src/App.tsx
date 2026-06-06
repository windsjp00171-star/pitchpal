import { useState, useRef } from 'react'

const ALL_KEYS = [
  'C 大調','C#/Db 大調','D 大調','D#/Eb 大調','E 大調','F 大調',
  'F#/Gb 大調','G 大調','G#/Ab 大調','A 大調','A#/Bb 大調','B 大調',
  'C 小調','C#/Db 小調','D 小調','D#/Eb 小調','E 小調','F 小調',
  'F#/Gb 小調','G 小調','G#/Ab 小調','A 小調','A#/Bb 小調','B 小調',
]

type DetectStep = 'idle' | 'detecting' | 'detected' | 'transposing' | 'done'
type TranscribeStep = 'idle' | 'processing' | 'done'
type Tab = 'detect' | 'transcribe'

function KeyDetectTab() {
  const [file, setFile] = useState<File | null>(null)
  const [step, setStep] = useState<DetectStep>('idle')
  const [detectedKey, setDetectedKey] = useState('')
  const [confidence, setConfidence] = useState(0)
  const [targetKey, setTargetKey] = useState('')
  const [downloadUrl, setDownloadUrl] = useState('')
  const [error, setError] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const reset = () => {
    setFile(null); setStep('idle'); setDetectedKey(''); setConfidence(0)
    setTargetKey(''); setDownloadUrl(''); setError('')
    if (inputRef.current) inputRef.current.value = ''
  }

  const handleFile = async (f: File) => {
    setFile(f); setError(''); setDownloadUrl(''); setStep('detecting')
    const fd = new FormData(); fd.append('file', f)
    try {
      const res = await fetch('/api/detect', { method: 'POST', body: fd })
      if (!res.ok) throw new Error((await res.json()).detail)
      const data = await res.json()
      setDetectedKey(data.key); setConfidence(data.confidence)
      setTargetKey(data.key); setStep('detected')
    } catch (e: any) {
      setError(e.message || '偵測失敗'); setStep('idle')
    }
  }

  const handleTranspose = async () => {
    if (!file || !detectedKey || !targetKey) return
    setStep('transposing'); setError('')
    const fd = new FormData()
    fd.append('file', file)
    fd.append('detected_key', detectedKey)
    fd.append('target_key', targetKey)
    try {
      const res = await fetch('/api/transpose', { method: 'POST', body: fd })
      if (!res.ok) throw new Error((await res.json()).detail)
      const blob = await res.blob()
      setDownloadUrl(URL.createObjectURL(blob)); setStep('done')
    } catch (e: any) {
      setError(e.message || '移調失敗'); setStep('detected')
    }
  }

  const isDetected = step === 'detected' || step === 'transposing' || step === 'done'
  const isBusy = step === 'detecting' || step === 'transposing'

  return (
    <div className="space-y-4">
      {/* YouTube hint */}
      <div className="rounded-xl bg-amber-50 border border-amber-200 px-4 py-3 text-sm text-amber-800">
        <span className="font-medium">YouTube 音檔？</span>{' '}
        先到{' '}
        <a href="https://cobalt.tools" target="_blank" rel="noopener noreferrer"
          className="underline font-medium">cobalt.tools</a>{' '}
        下載成 mp3，再上傳這裡。
      </div>

      {/* Step 1: Upload */}
      <div className="rounded-2xl border border-gray-100 bg-white p-5 shadow-sm">
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">① 上傳音檔</p>
        <div
          onClick={() => !isBusy && inputRef.current?.click()}
          onDragOver={e => e.preventDefault()}
          onDrop={e => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f && !isBusy) handleFile(f) }}
          className={`border-2 border-dashed rounded-xl p-5 text-center transition-colors
            ${isBusy ? 'border-gray-100 bg-gray-50 cursor-not-allowed'
              : 'border-gray-200 cursor-pointer hover:border-purple-400 hover:bg-purple-50'}`}
        >
          <input ref={inputRef} type="file" accept="audio/*" className="hidden"
            onChange={e => { const f = e.target.files?.[0]; if (f) handleFile(f) }} />
          {file ? (
            <p className="text-sm text-gray-700 font-medium truncate">📄 {file.name}</p>
          ) : (
            <>
              <p className="text-2xl mb-1">🎵</p>
              <p className="text-sm text-gray-500">點擊或拖曳上傳</p>
              <p className="text-xs text-gray-400 mt-1">mp3 · wav · m4a</p>
            </>
          )}
        </div>
        {step === 'detecting' && (
          <p className="text-center text-sm text-purple-500 mt-3 animate-pulse">偵測中，請稍候…</p>
        )}
      </div>

      {/* Step 2: Key result */}
      {isDetected && (
        <div className="rounded-2xl border border-purple-100 bg-purple-50 p-5 shadow-sm">
          <p className="text-xs font-semibold text-purple-400 uppercase tracking-wide mb-3">② 偵測結果</p>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-3xl font-bold text-purple-700">{detectedKey}</p>
              <p className="text-xs text-purple-400 mt-1">信心度 {confidence}%</p>
            </div>
            <div className="text-4xl">🎼</div>
          </div>
        </div>
      )}

      {/* Step 3: Transpose (optional) */}
      {isDetected && (
        <div className="rounded-2xl border border-gray-100 bg-white p-5 shadow-sm">
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">
            ③ 移調（選用）
          </p>
          <label className="block text-sm text-gray-600 mb-2">選擇目標 Key</label>
          <select
            value={targetKey}
            onChange={e => { setTargetKey(e.target.value); setDownloadUrl(''); if (step === 'done') setStep('detected') }}
            disabled={isBusy}
            className="w-full rounded-xl border border-gray-200 px-3 py-2.5 text-sm text-gray-800 bg-white focus:outline-none focus:ring-2 focus:ring-purple-400 mb-3 disabled:opacity-50"
          >
            {ALL_KEYS.map(k => <option key={k} value={k}>{k}</option>)}
          </select>

          {targetKey === detectedKey ? (
            <p className="text-sm text-gray-400 text-center">已是目標 Key，無需移調</p>
          ) : downloadUrl ? (
            <a
              href={downloadUrl}
              download="transposed.wav"
              className="block w-full rounded-xl bg-green-600 text-white py-3 text-sm font-semibold text-center hover:bg-green-700 active:scale-95 transition"
            >
              ⬇ 下載移調音檔
            </a>
          ) : (
            <button
              onClick={handleTranspose}
              disabled={isBusy}
              className="w-full rounded-xl bg-purple-600 text-white py-3 text-sm font-semibold hover:bg-purple-700 active:scale-95 transition disabled:opacity-50"
            >
              {step === 'transposing' ? '移調中…' : '開始移調'}
            </button>
          )}
        </div>
      )}

      {error && <p className="text-sm text-red-500 text-center">{error}</p>}

      {isDetected && (
        <button onClick={reset} className="w-full text-xs text-gray-400 hover:text-gray-600 py-1">
          重新上傳
        </button>
      )}
    </div>
  )
}

function TranscribeTab() {
  const [file, setFile] = useState<File | null>(null)
  const [step, setStep] = useState<TranscribeStep>('idle')
  const [title, setTitle] = useState('')
  const [composer, setComposer] = useState('')
  const [downloadUrl, setDownloadUrl] = useState('')
  const [error, setError] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const reset = () => {
    setFile(null); setStep('idle'); setDownloadUrl(''); setError('')
    if (inputRef.current) inputRef.current.value = ''
  }

  const handleTranscribe = async () => {
    if (!file) return
    setStep('processing'); setError('')
    const fd = new FormData()
    fd.append('file', file)
    fd.append('title', title)
    fd.append('composer', composer)
    try {
      const res = await fetch('/api/transcribe', { method: 'POST', body: fd })
      if (!res.ok) throw new Error((await res.json()).detail)
      const blob = await res.blob()
      setDownloadUrl(URL.createObjectURL(blob)); setStep('done')
    } catch (e: any) {
      setError(e.message || '轉譜失敗'); setStep('idle')
    }
  }

  const isBusy = step === 'processing'

  return (
    <div className="space-y-4">
      <div className="rounded-xl bg-blue-50 border border-blue-200 px-4 py-3 text-sm text-blue-800">
        上傳詩歌音檔，自動辨識旋律，輸出 PDF 樂譜。適合主旋律清晰的錄音。
      </div>

      {/* Upload */}
      <div className="rounded-2xl border border-gray-100 bg-white p-5 shadow-sm">
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">① 上傳音檔</p>
        <div
          onClick={() => !isBusy && inputRef.current?.click()}
          onDragOver={e => e.preventDefault()}
          onDrop={e => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f && !isBusy) setFile(f) }}
          className={`border-2 border-dashed rounded-xl p-5 text-center transition-colors
            ${isBusy ? 'border-gray-100 bg-gray-50 cursor-not-allowed'
              : 'border-gray-200 cursor-pointer hover:border-blue-400 hover:bg-blue-50'}`}
        >
          <input ref={inputRef} type="file" accept="audio/*" className="hidden"
            onChange={e => { const f = e.target.files?.[0]; if (f) setFile(f) }} />
          {file ? (
            <p className="text-sm text-gray-700 font-medium truncate">📄 {file.name}</p>
          ) : (
            <>
              <p className="text-2xl mb-1">🎼</p>
              <p className="text-sm text-gray-500">點擊或拖曳上傳</p>
              <p className="text-xs text-gray-400 mt-1">mp3 · wav · m4a</p>
            </>
          )}
        </div>
      </div>

      {/* Metadata */}
      {file && (
        <div className="rounded-2xl border border-gray-100 bg-white p-5 shadow-sm space-y-3">
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide">② 樂譜資訊（選填）</p>
          <input
            type="text" placeholder="樂譜標題，例：Amazing Grace"
            value={title} onChange={e => setTitle(e.target.value)}
            className="w-full rounded-xl border border-gray-200 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
          />
          <input
            type="text" placeholder="作曲者"
            value={composer} onChange={e => setComposer(e.target.value)}
            className="w-full rounded-xl border border-gray-200 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
          />
        </div>
      )}

      {/* Action */}
      {file && !downloadUrl && (
        <button
          onClick={handleTranscribe}
          disabled={isBusy}
          className="w-full rounded-xl bg-blue-600 text-white py-3 text-sm font-semibold hover:bg-blue-700 active:scale-95 transition disabled:opacity-50"
        >
          {isBusy ? '轉譜中，請稍候（約 30 秒）…' : '開始轉譜'}
        </button>
      )}

      {downloadUrl && (
        <a
          href={downloadUrl}
          download="score.pdf"
          className="block w-full rounded-xl bg-green-600 text-white py-3 text-sm font-semibold text-center hover:bg-green-700 active:scale-95 transition"
        >
          ⬇ 下載 PDF 樂譜
        </a>
      )}

      {error && <p className="text-sm text-red-500 text-center">{error}</p>}

      {(file || error) && (
        <button onClick={reset} className="w-full text-xs text-gray-400 hover:text-gray-600 py-1">
          重新上傳
        </button>
      )}
    </div>
  )
}

export default function App() {
  const [tab, setTab] = useState<Tab>('detect')

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col items-center px-4 py-8">
      {/* Header */}
      <div className="w-full max-w-md mb-6 text-center">
        <h1 className="text-2xl font-bold text-gray-800 mb-1">🎵 PitchPal</h1>
        <p className="text-sm text-gray-500">敬拜調性工具</p>
      </div>

      {/* Tabs */}
      <div className="w-full max-w-md mb-4 flex rounded-xl bg-white border border-gray-100 shadow-sm overflow-hidden">
        <button
          onClick={() => setTab('detect')}
          className={`flex-1 py-2.5 text-sm font-medium transition-colors
            ${tab === 'detect' ? 'bg-purple-600 text-white' : 'text-gray-500 hover:text-gray-700'}`}
        >
          辨識 Key / 移調
        </button>
        <button
          onClick={() => setTab('transcribe')}
          className={`flex-1 py-2.5 text-sm font-medium transition-colors
            ${tab === 'transcribe' ? 'bg-blue-600 text-white' : 'text-gray-500 hover:text-gray-700'}`}
        >
          音檔轉譜 PDF
        </button>
      </div>

      {/* Content */}
      <div className="w-full max-w-md">
        {tab === 'detect' ? <KeyDetectTab /> : <TranscribeTab />}
      </div>
    </div>
  )
}
