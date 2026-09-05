/**
 * useSpeechRecognition — wraps the browser Web Speech API for push-to-talk STT.
 * Works in Chrome/Edge. Returns `supported=false` in Firefox/Safari.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

interface UseSpeechRecognitionReturn {
  supported: boolean
  listening: boolean
  transcript: string
  start: () => void
  stop: () => void
  reset: () => void
}

// Augment window for vendor-prefixed API
declare global {
  interface Window {
    SpeechRecognition?: new () => SpeechRecognition
    webkitSpeechRecognition?: new () => SpeechRecognition
  }
}

export function useSpeechRecognition(): UseSpeechRecognitionReturn {
  const SpeechRecognitionCtor =
    typeof window !== 'undefined'
      ? window.SpeechRecognition ?? window.webkitSpeechRecognition
      : undefined

  const supported = SpeechRecognitionCtor != null
  const recognitionRef = useRef<SpeechRecognition | null>(null)
  const [listening, setListening] = useState(false)
  const [transcript, setTranscript] = useState('')

  useEffect(() => {
    if (!SpeechRecognitionCtor) return
    const rec = new SpeechRecognitionCtor()
    rec.continuous = false
    rec.interimResults = false
    rec.lang = 'en-US'

    rec.onresult = (e: SpeechRecognitionEvent) => {
      const text = Array.from(e.results)
        .map((r) => r[0].transcript)
        .join(' ')
        .trim()
      setTranscript(text)
    }
    rec.onend = () => setListening(false)
    rec.onerror = () => setListening(false)

    recognitionRef.current = rec
    return () => {
      rec.abort()
    }
  }, [SpeechRecognitionCtor])

  const start = useCallback(() => {
    if (!recognitionRef.current || listening) return
    setTranscript('')
    setListening(true)
    recognitionRef.current.start()
  }, [listening])

  const stop = useCallback(() => {
    recognitionRef.current?.stop()
    setListening(false)
  }, [])

  const reset = useCallback(() => setTranscript(''), [])

  return { supported, listening, transcript, start, stop, reset }
}
