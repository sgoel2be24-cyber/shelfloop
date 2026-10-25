import { useCallback, useEffect, useRef, useState } from 'react'

interface SpeechRecognitionLike {
  lang: string
  continuous: boolean
  interimResults: boolean
  start(): void
  stop(): void
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>>; resultIndex: number }) => void) | null
  onerror: ((e: { error?: string }) => void) | null
  onend: (() => void) | null
}

type SpeechRecognitionCtor = new () => SpeechRecognitionLike

/**
 * Free, built-in browser speech input (Web Speech API) — hi-IN or en-IN.
 * Transcripts land in the capture composer and stay proposal-gated, exactly
 * like typed input. Unsupported browsers get a graceful `unsupported` state.
 */
export function useSpeechInput(lang: 'en' | 'hi') {
  const [listening, setListening] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const recRef = useRef<SpeechRecognitionLike | null>(null)
  const [supported] = useState(() => {
    const w = window as unknown as { SpeechRecognition?: SpeechRecognitionCtor; webkitSpeechRecognition?: SpeechRecognitionCtor }
    return Boolean(w.SpeechRecognition ?? w.webkitSpeechRecognition)
  })

  useEffect(() => {
    return () => {
      try {
        recRef.current?.stop()
      } catch {
        /* already stopped */
      }
    }
  }, [])

  const stop = useCallback(() => {
    try {
      recRef.current?.stop()
    } catch {
      /* ignore */
    }
    setListening(false)
  }, [])

  const start = useCallback(
    (onText: (text: string, isFinal: boolean) => void) => {
      setError(null)
      const w = window as unknown as { SpeechRecognition?: SpeechRecognitionCtor; webkitSpeechRecognition?: SpeechRecognitionCtor }
      const Ctor = w.SpeechRecognition ?? w.webkitSpeechRecognition
      if (!Ctor) {
        setError('unsupported')
        return
      }
      try {
        const rec = new Ctor()
        rec.lang = lang === 'hi' ? 'hi-IN' : 'en-IN'
        rec.continuous = true
        rec.interimResults = true
        rec.onresult = (e) => {
          let final = ''
          let interim = ''
          for (let i = 0; i < e.results.length; i++) {
            const res = e.results[i]
            const text = res[0]?.transcript ?? ''
            if (resIsFinal(res)) final += `${text} `
            else interim += text
          }
          onText(`${final}${interim}`.trim(), interim === '')
        }
        rec.onerror = (e) => {
          if (e.error && e.error !== 'aborted' && e.error !== 'no-speech') setError(e.error)
          setListening(false)
        }
        rec.onend = () => setListening(false)
        recRef.current = rec
        rec.start()
        setListening(true)
      } catch {
        setError('unsupported')
        setListening(false)
      }
    },
    [lang],
  )

  return { supported, listening, error, start, stop }
}

function resIsFinal(res: { length: number; isFinal?: boolean }): boolean {
  return Boolean((res as { isFinal?: boolean }).isFinal)
}
