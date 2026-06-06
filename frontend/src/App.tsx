import { useState, useRef } from 'react'

const ALL_KEYS = [
  'C 大調','C#/Db 大調','D 大調','D#/Eb 大調','E 大調','F 大調',
  'F#/Gb 大調','G 大調','G#/Ab 大調','A 大調','A#/Bb 大調','B 大調',
  'C 小調','C#/Db 小調','D 小調','D#/Eb 小調','E 小調','F 小調',
  'F#/Gb 小調','G 小調','G#/Ab 小調','A 小調','A#/Bb 小調','B 小調',
]

type Step = 'idle' | 'detecting' | 'detected' | 'transposing' | 'done'

export default function App() {
  const [file, setFile] = useState<File | null>(null)
  const [step, setStep] = useState<Step>('idle')
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

  const isDone = step === 'done'
  const isDetected = step === 'detected' || isDone
  const isBusy = step === 'detecting' || step === 'transposing'

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col items-center px-4 py-8">
      <div className="w-full max-w-md mb-6 text-center">
        <h1 className="text-2xl font-bold text-gray-800 mb-1">🎵 PitchPal</h1>
        <p className="text-sm text-gray-500">敬拜調性工具 · 辨識 Key · 移調</p>
      </div>

      {/* YouTube hint */}
      <div className="w-full max-w-md mb-4 rounded-xl bg-amber-50 border border-amber-200 px-4 py-3 text-sm text-amber-800">
        <span className="font-medium">YouTube 音檔？</span>{' '}
        先到{' '}
        <a href="https://cobalt.tools" target="_blank" rel="noopener noreferrer"
          className="underline font-medium">cobalt.tools</a>{' '}
        下載成 mp3，再上傳這裡。
      </div>

      <div className="w-full max-w-md bg-white rounded-2xl shadow-sm border border-gray-100 p-6 space-y-5">

        {/* Drop zone */}
        <div
          onClick={() => !isBusy && inputRef.current?.click()}
          onDragOver={e => e.preventDefault()}
          onDrop={e => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f && !isBusy) handleFile(f) }}
          className={`border-2 border-dashed rounded-xl p-6 text-center transition-colors
            ${isBusy ? 'border-gray-100 bg-gray-50 cursor-not-allowed' : 'border-gray-200 cursor-pointer hover:border-purple-400 hover:bg-purple-50'}`}
        >
          <input ref={inputRef} type="file" accept="audio/*" className="hidden"
            onChange={e => { const f = e.target.files?.[0]; if (f) handleFile(f) }} />
          {file ? (
            <p className="text-sm text-gray-700 font-medium truncate">{file.name}</p>
          ) : (
            <>
              <p className="text-3xl mb-2">🎵</p>
              <p className="text-sm text-gray-500">點擊或拖曳上傳音檔</p>
              <p className="text-xs text-gray-400 mt-1">mp3 · wav · m4a</p>
            </>
          )}
        </div>

        {/* Detecting spinner */}
        {step === 'detecting' && (
          <div className="flex items-center justify-center gap-2 text-sm text-purple-600">
            <span className="animate-spin inline-block">⏳</span> 偵測中…
          </div>
        )}

        {/* Detected key */}
        {isDetected && (
          <div className="rounded-xl bg-purple-50 border border-purple-100 px-4 py-3 flex items-center justify-between">
            <div>
              <p className="text-xs text-purple-400 mb-0.5">偵測到的 Key</p>
              <p className="text-xl font-bold text-purple-700">{detectedKey}</p>
            </div>
            <div className="text-right">
              <p className="text-xs text-purple-400 mb-0.5">信心度</p>
              <p className="text-lg font-semibold text-purple-600">{confidence}%</p>
            </div>
          </div>
        )}

        {/* Target key selector */}
        {isDetected && (
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">目標 Key</label>
            <select
              value={targetKey}
              onChange={e => { setTargetKey(e.target.value); setDownloadUrl(''); if (step === 'done') setStep('detected') }}
              className="w-full rounded-xl border border-gray-200 px-3 py-2.5 text-sm text-gray-800 bg-white focus:outline-none focus:ring-2 focus:ring-purple-400"
            >
              {ALL_KEYS.map(k => <option key={k} value={k}>{k}</option>)}
            </select>
          </div>
        )}

        {/* Same key notice */}
        {isDetected && targetKey === detectedKey && !downloadUrl && (
          <p className="text-center text-sm text-gray-400">已是目標 Key，無需移調</p>
        )}

        {/* Transpose button */}
        {isDetected && targetKey !== detectedKey && !downloadUrl && (
          <button
            onClick={handleTranspose}
            disabled={isBusy}
            className="w-full rounded-xl bg-purple-600 text-white py-3 text-sm font-semibold hover:bg-purple-700 active:scale-95 transition disabled:opacity-50"
          >
            {isBusy ? '移調中…' : '開始移調'}
          </button>
        )}

        {/* Download */}
        {downloadUrl && (
          <a
            href={downloadUrl}
            download="transposed.wav"
            className="block w-full rounded-xl bg-green-600 text-white py-3 text-sm font-semibold text-center hover:bg-green-700 active:scale-95 transition"
          >
            ⬇ 下載移調音檔
          </a>
        )}

        {/* Error */}
        {error && (
          <p className="text-sm text-red-500 text-center">{error}</p>
        )}

        {/* Reset */}
        {(isDetected || error) && (
          <button onClick={reset} className="w-full text-xs text-gray-400 hover:text-gray-600 py-1">
            重新上傳
          </button>
        )}
      </div>
    </div>
  )
}
