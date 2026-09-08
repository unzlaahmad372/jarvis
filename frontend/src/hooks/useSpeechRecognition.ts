/**
 * useSpeechRecognition — push-to-talk STT using the browser Web Speech API.
 * Works in Chrome/Edge. Returns `supported=false` in Firefox/Safari.
 *
 * Mic-busy retry: if Chrome fires onend immediately (no onaudiostart), the mic
 * is still held by the previous SpeechRecognition instance. We retry up to
 * MAX_RETRIES times with RETRY_MS delay — no fixed upfront delay needed.
 */

import { useCallback, useRef, useState } from 'react'

const MAX_RETRIES = 6
const RETRY_MS = 200

interface UseSpeechRecognitionReturn {
  supported: boolean
  listening: boolean
  transcript: string
  start: () => void
  stop: () => void
  reset: () => void
}

declare global {
  interface Window {
    SpeechRecognition?: new () => SpeechRecognitionInstance
    webkitSpeechRecognition?: new () => SpeechRecognitionInstance
  }
}

export type SpeechRecognitionInstance = {
  continuous: boolean
  interimResults: boolean
  lang: string
  maxAlternatives: number
  onresult: ((e: { results: { [i: number]: { [j: number]: { transcript: string } }; length: number } }) => void) | null
  onend: (() => void) | null
  onerror: ((e: unknown) => void) | null
  start: () => void
  stop: () => void
  abort: () => void
}

export function useSpeechRecognition(): UseSpeechRecognitionReturn {
  const ctorRef = useRef(
    typeof window !== 'undefined'
      ? window.SpeechRecognition ?? window.webkitSpeechRecognition
      : undefined
  )

  const supported = ctorRef.current != null
  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null)
  const cancelledRef = useRef(false)
  const [listening, setListening] = useState(false)
  const [transcript, setTranscript] = useState('')

  const start = useCallback((attempt = 0) => {
    if (!ctorRef.current || recognitionRef.current) return
    cancelledRef.current = false
    console.log('[stt] start attempt', attempt)

    const rec = new ctorRef.current() as SpeechRecognitionInstance
    rec.continuous = false
    rec.interimResults = false
    rec.lang = 'en-US'
    rec.maxAlternatives = 1

    let micOpened = false

    ;(rec as unknown as { onaudiostart: () => void }).onaudiostart = () => {
      console.log('[stt] onaudiostart — mic live')
      micOpened = true
      setListening(true)
    }

    rec.onresult = (e) => {
      const texts: string[] = []
      for (let i = 0; i < e.results.length; i++) texts.push(e.results[i][0].transcript)
      const final = texts.join(' ').trim()
      console.log('[stt] transcript:', JSON.stringify(final))
      setTranscript(final)
    }

    rec.onend = () => {
      console.log('[stt] onend — micOpened=', micOpened, 'attempt=', attempt)
      recognitionRef.current = null
      if (!micOpened && !cancelledRef.current && attempt < MAX_RETRIES) {
        console.log('[stt] mic busy, retrying in', RETRY_MS, 'ms')
        setTimeout(() => start(attempt + 1), RETRY_MS)
      } else {
        setListening(false)
      }
    }

    rec.onerror = (e: unknown) => {
      const err = (e as { error?: string }).error
      console.log('[stt] onerror:', err, 'attempt=', attempt)
      recognitionRef.current = null
      if (!micOpened && err !== 'aborted' && !cancelledRef.current && attempt < MAX_RETRIES) {
        setTimeout(() => start(attempt + 1), RETRY_MS)
      } else {
        setListening(false)
      }
    }

    recognitionRef.current = rec
    setTranscript('')
    rec.start()
  }, [])

  const stop = useCallback(() => {
    cancelledRef.current = true
    recognitionRef.current?.stop()
    recognitionRef.current = null
    setListening(false)
  }, [])

  const reset = useCallback(() => setTranscript(''), [])

  return { supported, listening, transcript, start, stop, reset }
}
